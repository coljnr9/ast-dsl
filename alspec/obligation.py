"""Obligation table generation from a Signature.

Given a Signature with generated_sorts annotated (mapping each generated sort
to its constructor list), deterministically produce the obligation table:
which (observer, constructor) pairs require axioms.

This follows CASL's approach: constructors are explicitly declared per
generated sort, not inferred from signature shape.

References:
  - CASL Language Summary, "generated type" declarations
  - Sannella & Tarlecki (2012), Ch. 2-4

This is Stage 2 of the pipeline:
    Stage 1: Domain → Signature with generated_sorts (LLM)
    Stage 2: Signature → ObligationTable (deterministic, this module)
    Stage 3: ObligationTable → Spec (LLM fills cells)
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .signature import FnSymbol, PredSymbol, Signature, SortRef


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------


class FnKind(Enum):
    CONSTRUCTOR = "constructor"
    OBSERVER = "observer"
    CONSTANT = "constant"
    UNINTERPRETED = "uninterpreted"


class PredKind(Enum):
    OBSERVER = "observer"
    EQUALITY = "equality"
    OTHER = "other"


@dataclass(frozen=True)
class FnRole:
    """The role of a function symbol relative to the generated sorts."""

    name: str
    kind: FnKind
    sort: SortRef | None  # which generated sort this relates to


@dataclass(frozen=True)
class PredRole:
    """The role of a predicate symbol relative to the generated sorts."""

    name: str
    kind: PredKind
    sort: SortRef | None


def classify_functions(sig: Signature) -> dict[str, FnRole]:
    """Classify every function symbol in the signature.

    Constructors are taken directly from generated_sorts — no inference.
    Everything else is classified by shape:
      - First param is a generated sort AND not a constructor of that sort
        → observer of that sort
      - Nullary, result not a generated sort → constant
      - Otherwise → uninterpreted
    """
    gen = sig.generated_sorts
    roles: dict[str, FnRole] = {}

    # First: register all declared constructors
    constructor_set: set[str] = set()
    for sort_name, ctor_names in gen.items():
        for ctor_name in ctor_names:
            constructor_set.add(ctor_name)
            roles[ctor_name] = FnRole(ctor_name, FnKind.CONSTRUCTOR, sort_name)

    # Second: classify everything else
    gen_sort_names = frozenset(gen.keys())
    for name, f in sig.functions.items():
        if name in roles:
            continue

        if f.params and f.params[0].sort in gen_sort_names:
            # First param is a generated sort, not declared as constructor → observer
            roles[name] = FnRole(name, FnKind.OBSERVER, f.params[0].sort)
        elif f.is_constant:
            # Nullary, result not a generated sort (constructors already handled)
            roles[name] = FnRole(name, FnKind.CONSTANT, None)
        else:
            # Everything else
            roles[name] = FnRole(name, FnKind.UNINTERPRETED, None)

    return roles


def classify_predicates(sig: Signature) -> dict[str, PredRole]:
    """Classify every predicate symbol in the signature.

    Rules:
      - p.params[0].sort is a generated sort → observer of that sort
      - p has exactly 2 params of the same non-generated sort AND name
        starts with 'eq_' → equality predicate
      - otherwise → other
    """
    gen_sort_names = frozenset(sig.generated_sorts.keys())
    roles: dict[str, PredRole] = {}

    for name, p in sig.predicates.items():
        if p.params and p.params[0].sort in gen_sort_names:
            roles[name] = PredRole(name, PredKind.OBSERVER, p.params[0].sort)
        elif (
            len(p.params) == 2
            and p.params[0].sort == p.params[1].sort
            and p.params[0].sort not in gen_sort_names
            and name.startswith("eq_")
        ):
            roles[name] = PredRole(name, PredKind.EQUALITY, p.params[0].sort)
        else:
            roles[name] = PredRole(name, PredKind.OTHER, None)

    return roles


# ---------------------------------------------------------------------------
# Key dispatch detection
# ---------------------------------------------------------------------------


def _detect_key_dispatch(
    observer: FnSymbol | PredSymbol,
    constructor: FnSymbol,
    equality_preds: dict[SortRef, str],
    generated_sort: SortRef,
) -> tuple[SortRef, str] | None:
    """Detect if (observer, constructor) pair needs key dispatch.

    Key dispatch applies when:
      - Both observer and constructor take a parameter of sort K
      - K is not the generated sort
      - There exists an equality predicate over K

    Returns (key_sort, eq_pred_name) if dispatch needed, else None.
    """
    obs_sorts = {p.sort for p in observer.params[1:]}  # skip first (state) param
    ctor_non_state = {p.sort for p in constructor.params if p.sort != generated_sort}

    shared = obs_sorts & ctor_non_state
    for sort in sorted(shared):  # sorted for determinism
        if sort in equality_preds:
            return (sort, equality_preds[sort])

    return None


# ---------------------------------------------------------------------------
# Obligation table
# ---------------------------------------------------------------------------


class CellDispatch(Enum):
    """How a cell is dispatched."""

    PLAIN = "plain"  # no key dispatch
    HIT = "hit"  # key equality holds
    MISS = "miss"  # key equality does not hold


@dataclass(frozen=True)
class ObligationCell:
    """A single cell in the obligation table.

    Represents: "observer O applied to constructor C needs an axiom."
    If key dispatch applies, the cell splits into hit/miss variants.
    """

    observer_name: str
    observer_is_predicate: bool
    constructor_name: str
    generated_sort: SortRef
    dispatch: CellDispatch
    key_sort: SortRef | None = None  # set when dispatch is HIT or MISS
    eq_pred: str | None = None  # the equality predicate name


@dataclass(frozen=True)
class ObligationTable:
    """The complete obligation table for a signature.

    Every cell represents an axiom that must be written.
    """

    cells: tuple[ObligationCell, ...]
    fn_roles: dict[str, FnRole]
    pred_roles: dict[str, PredRole]

    @property
    def cell_count(self) -> int:
        return len(self.cells)

    def cells_for_observer(self, name: str) -> list[ObligationCell]:
        return [c for c in self.cells if c.observer_name == name]

    def cells_for_constructor(self, name: str) -> list[ObligationCell]:
        return [c for c in self.cells if c.constructor_name == name]


def build_obligation_table(sig: Signature) -> ObligationTable:
    """Build the obligation table from a signature with generated_sorts.

    For each generated sort G:
      - Constructors are taken from generated_sorts[G]
      - Observers are all functions/predicates with first param of sort G
        that are NOT constructors of G
      - For each (observer, constructor) pair:
        - If key dispatch applies: emit HIT + MISS cells
        - Otherwise: emit a PLAIN cell
    """
    fn_roles = classify_functions(sig)
    pred_roles = classify_predicates(sig)

    # Collect equality predicates: sort → pred_name
    equality_preds: dict[SortRef, str] = {}
    for name, role in pred_roles.items():
        if role.kind == PredKind.EQUALITY:
            assert role.sort is not None
            equality_preds[role.sort] = name

    cells: list[ObligationCell] = []

    for gen_sort in sorted(sig.generated_sorts.keys()):
        ctor_names = sig.generated_sorts[gen_sort]

        # Constructors of this sort (in declared order)
        constructors = [sig.functions[name] for name in ctor_names]

        # Function observers of this sort
        fn_observers = sorted(
            [
                sig.functions[name]
                for name, role in fn_roles.items()
                if role.kind == FnKind.OBSERVER and role.sort == gen_sort
            ],
            key=lambda f: f.name,
        )

        # Predicate observers of this sort
        pred_observers = sorted(
            [
                sig.predicates[name]
                for name, role in pred_roles.items()
                if role.kind == PredKind.OBSERVER and role.sort == gen_sort
            ],
            key=lambda p: p.name,
        )

        for ctor in constructors:
            for obs in fn_observers:
                dispatch = _detect_key_dispatch(obs, ctor, equality_preds, gen_sort)
                if dispatch is not None:
                    key_sort, eq_pred = dispatch
                    cells.append(ObligationCell(
                        observer_name=obs.name,
                        observer_is_predicate=False,
                        constructor_name=ctor.name,
                        generated_sort=gen_sort,
                        dispatch=CellDispatch.HIT,
                        key_sort=key_sort,
                        eq_pred=eq_pred,
                    ))
                    cells.append(ObligationCell(
                        observer_name=obs.name,
                        observer_is_predicate=False,
                        constructor_name=ctor.name,
                        generated_sort=gen_sort,
                        dispatch=CellDispatch.MISS,
                        key_sort=key_sort,
                        eq_pred=eq_pred,
                    ))
                else:
                    cells.append(ObligationCell(
                        observer_name=obs.name,
                        observer_is_predicate=False,
                        constructor_name=ctor.name,
                        generated_sort=gen_sort,
                        dispatch=CellDispatch.PLAIN,
                    ))

            for obs in pred_observers:
                dispatch = _detect_key_dispatch(obs, ctor, equality_preds, gen_sort)
                if dispatch is not None:
                    key_sort, eq_pred = dispatch
                    cells.append(ObligationCell(
                        observer_name=obs.name,
                        observer_is_predicate=True,
                        constructor_name=ctor.name,
                        generated_sort=gen_sort,
                        dispatch=CellDispatch.HIT,
                        key_sort=key_sort,
                        eq_pred=eq_pred,
                    ))
                    cells.append(ObligationCell(
                        observer_name=obs.name,
                        observer_is_predicate=True,
                        constructor_name=ctor.name,
                        generated_sort=gen_sort,
                        dispatch=CellDispatch.MISS,
                        key_sort=key_sort,
                        eq_pred=eq_pred,
                    ))
                else:
                    cells.append(ObligationCell(
                        observer_name=obs.name,
                        observer_is_predicate=True,
                        constructor_name=ctor.name,
                        generated_sort=gen_sort,
                        dispatch=CellDispatch.PLAIN,
                    ))

    return ObligationTable(cells=tuple(cells), fn_roles=fn_roles, pred_roles=pred_roles)
