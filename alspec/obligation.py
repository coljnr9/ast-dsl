"""Obligation table generation from a Signature.

Given a Signature with generated_sorts annotated (mapping each generated sort
to its constructor list and selector info), deterministically produce the
obligation table: which (observer, constructor) pairs require axioms.

This follows CASL's approach: constructors are explicitly declared per
generated sort, not inferred from signature shape. Selectors are also
declared per constructor and have mechanically derivable axiom tiers.

References:
  - CASL Language Summary, "generated type" declarations
  - Sannella & Tarlecki (2012), Ch. 2-4

This is Stage 3 (OBLIGATION) of the pipeline:
    Stage 1 (ANALYSIS):   Domain → Structured domain analysis (LLM)
    Stage 2 (SIGNATURE):  Domain → Signature with generated_sorts (LLM)
    Stage 3 (OBLIGATION): Signature → ObligationTable (deterministic, this module)
    Stage 4 (AXIOMS):     ObligationTable → Spec (LLM fills cells)
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .signature import FnSymbol, GeneratedSortInfo, PredSymbol, Signature, SortRef


class ObligationTableError(Exception):
    """Stage 1 signature is missing infrastructure required for Stage 2."""
    pass


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------


class FnKind(Enum):
    CONSTRUCTOR = "constructor"
    SELECTOR = "selector"       # declared component of a constructor
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
    Selectors are taken from the selectors map in GeneratedSortInfo.
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
    for sort_name, info in gen.items():
        for ctor_name in info.constructors:
            constructor_set.add(ctor_name)
            roles[ctor_name] = FnRole(ctor_name, FnKind.CONSTRUCTOR, sort_name)

    # Second: register all declared selectors
    for sort_name, info in gen.items():
        for _ctor_name, sel_map in info.selectors.items():
            for sel_name, _result_sort in sel_map.items():
                if sel_name not in roles:
                    roles[sel_name] = FnRole(sel_name, FnKind.SELECTOR, sort_name)

    # Third: classify everything else
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
      - p has exactly 2 params of the same sort AND name
        starts with 'eq_' → equality predicate
      - p.params[0].sort is a generated sort → observer of that sort
      - otherwise → other
    """
    gen_sort_names = frozenset(sig.generated_sorts.keys())
    roles: dict[str, PredRole] = {}

    for name, p in sig.predicates.items():
        if (
            len(p.params) == 2
            and p.params[0].sort == p.params[1].sort
            and name.startswith("eq_")
        ):
            roles[name] = PredRole(name, PredKind.EQUALITY, p.params[0].sort)
        elif p.params and p.params[0].sort in gen_sort_names:
            roles[name] = PredRole(name, PredKind.OBSERVER, p.params[0].sort)
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


class CellTier(Enum):
    """How deterministic the fill for this cell is.

    SELECTOR_EXTRACT: Selector applied to its home constructor.
        Axiom is mechanically derivable: selector(ctor(..., x, ...)) = x
        where x is the component this selector extracts.
        Formal basis: CASL datatype declaration semantics (CASL Ref Manual §2.3.4).

    SELECTOR_FOREIGN: Selector applied to a constructor it doesn't belong to.
        Under free-type convention: ¬def(selector(foreign_ctor(...)))
        Formal basis: CASL free type expansion generates these mechanically.
        Under loose semantics, this is a strong default that the LLM can override
        if the domain requires definedness here (rare).

    KEY_DISPATCH: Observer and constructor share a key sort with `eq_*`.
        Axiom must be split into HIT (eq_k holds) and MISS (¬eq_k).
        Mechanical if MISS delegates to inner state; domain reasoning for HIT.

    PRESERVATION: Informational hint — observer has key sorts the constructor
        does not take. This SUGGESTS preservation but is NOT mechanically
        justified. The constructor may affect all keys through domain logic
        (e.g., clear_faults resets all fault types despite having no FaultType
        parameter). The LLM must confirm preservation via domain reasoning.
        axiom_gen does NOT generate axioms for this tier.

    BASE_CASE: Constructor is the base constructor (no recursive self-referential parameter).
        Typically results in base values: ¬def for partial, false for predicates.

    DOMAIN: General observer or non-selector function.
        Fill depends on domain semantics. LLM must determine the axiom.
    """

    SELECTOR_EXTRACT = "selector_extract"
    SELECTOR_FOREIGN = "selector_foreign"
    KEY_DISPATCH = "key_dispatch"
    PRESERVATION = "preservation"
    BASE_CASE = "base_case"
    DOMAIN = "domain"


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
    tier: CellTier = CellTier.DOMAIN
    key_sort: SortRef | None = None  # set when dispatch is HIT or MISS
    eq_pred: str | None = None  # the equality predicate name
    home_constructor: str | None = None  # if SELECTOR, which ctor owns it
    extracts_param: str | None = None  # if SELECTOR_EXTRACT, the constructor param name


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


def _compute_tier(
    obs: FnSymbol | PredSymbol,
    ctor: FnSymbol,
    gen_sort: SortRef,
    fn_roles: dict[str, FnRole],
    sig: Signature,
    equality_preds: dict[SortRef, str],
) -> tuple[CellTier, str | None, str | None]:
    """Compute the tier for a cell. Returns (tier, home_ctor, extracts_param)."""
    # 1. Selectors take precedence
    if not isinstance(obs, PredSymbol):
        role = fn_roles.get(obs.name)
        if role and role.kind == FnKind.SELECTOR:
            info = sig.generated_sorts[gen_sort]
            for ctor_name, sel_map in info.selectors.items():
                if obs.name in sel_map:
                    if ctor_name == ctor.name:
                        return (
                            CellTier.SELECTOR_EXTRACT,
                            ctor_name,
                            sel_map[obs.name],  # param_name
                        )
                    else:
                        return CellTier.SELECTOR_FOREIGN, ctor_name, None

    # 2. Key dispatch (share a key sort with an eq_* pred)
    obs_key_sorts = {p.sort for p in obs.params[1:]}
    ctor_non_state_sorts = {
        p.sort for p in ctor.params if p.sort != gen_sort
    }
    shared = obs_key_sorts & ctor_non_state_sorts

    if any(s in equality_preds for s in shared):
        return CellTier.KEY_DISPATCH, None, None

    # 3. Base case (constructor with no recursive self-referential parameter)
    # Must be checked before PRESERVATION: nullary/base constructors like
    # `empty` should be BASE_CASE, not PRESERVATION, even when the observer
    # has key sorts that the constructor obviously doesn't take.
    if all(p.sort != gen_sort for p in ctor.params):
        return CellTier.BASE_CASE, None, None

    # 4. Preservation hint (observer has keys, constructor doesn't take them)
    # This is an INFORMATIONAL hint only — axiom_gen does NOT generate axioms
    # for this tier. The absence of a shared key sort suggests preservation
    # is likely, but it requires domain confirmation by the LLM.
    if obs_key_sorts and not (obs_key_sorts & ctor_non_state_sorts):
        return CellTier.PRESERVATION, None, None

    return CellTier.DOMAIN, None, None


def build_obligation_table(sig: Signature) -> ObligationTable:
    """Build the obligation table from a signature with generated_sorts.

    For each generated sort G:
      - Constructors are taken from generated_sorts[G].constructors
      - Observers are all functions/predicates with first param of sort G
        that are NOT constructors of G (but may be selectors)
      - For each (observer, constructor) pair:
        - If key dispatch applies: emit HIT + MISS cells
        - Otherwise: emit a PLAIN cell
      - Each cell is annotated with a CellTier based on selector info
    """
    fn_roles = classify_functions(sig)
    pred_roles = classify_predicates(sig)

    # Collect equality predicates: sort → pred_name
    equality_preds: dict[SortRef, str] = {}
    for name, role in pred_roles.items():
        if role.kind == PredKind.EQUALITY:
            match role.sort:
                case str() as s:
                    equality_preds[s] = name
                case _:
                    pass

    # Check B: Generated sort completeness
    for gen_sort, info in sig.generated_sorts.items():
        if not info.constructors:
            raise ObligationTableError(f"Generated sort '{gen_sort}' has no constructors.")

        has_base = False
        for ctor_name in info.constructors:
            if ctor_name not in sig.functions:
                # Check B1 enhancement: Namespace invariant (CASL RM §2.3.4)
                if ctor_name in sig.predicates:
                    raise ObligationTableError(
                        f"Constructor '{ctor_name}' is a predicate, not a function. "
                        "Constructors must be function symbols per CASL RM §2.3.4."
                    )
                raise ObligationTableError(
                    f"Constructor '{ctor_name}' listed for sort '{gen_sort}' not found in signature."
                )
            # A base constructor is one whose parameters are all non-recursive:
            # none of them are of the generated sort itself.  This admits both
            # nullary constructors (zero params) AND parameterised ones like
            # init(pv: Word) -> Counter, which take only auxiliary data.
            ctor_fn = sig.functions[ctor_name]
            if all(p.sort != gen_sort for p in ctor_fn.params):
                has_base = True

        # Check B2: Selector namespace validation (CASL RM §2.3.4)
        for ctor_name, sel_map in info.selectors.items():
            for sel_name in sel_map:
                if sel_name not in sig.functions:
                    if sel_name in sig.predicates:
                        raise ObligationTableError(
                            f"Selector '{sel_name}' is a predicate, not a function. "
                            "Selectors must be function symbols per CASL RM §2.3.4."
                        )
                    raise ObligationTableError(
                        f"Selector '{sel_name}' for constructor '{ctor_name}' not found in signature."
                    )

        if not has_base:
            raise ObligationTableError(
                f"Generated sort '{gen_sort}' has no base constructor. "
                "At least one constructor must take no parameters of the generated sort itself "
                "(e.g. 'init(pv: Word) -> Counter' or 'new -> Stack'). "
                "A sort with only recursive constructors cannot be initialised."
            )

        # Check C: Generation constraint — non-constructor functions returning
        # a generated sort must be "homed" as observers/selectors of some other
        # generated sort. Constants and uninterpreted functions returning G have
        # no obligation table home and indicate a signature defect (missing
        # constructor or definitional abbreviation without an axiom).
        # Theoretical basis: CASL RM §6.2, generation constraint.
        for name, f in sig.functions.items():
            if f.result == gen_sort and name not in info.constructors:
                role = fn_roles.get(name)
                if role is None:
                    continue  # defensive — should not happen
                if role.kind in (FnKind.OBSERVER, FnKind.SELECTOR, FnKind.CONSTRUCTOR):
                    # Homed in another sort's obligation table, or is a
                    # constructor of another sort. Generation constraint on G
                    # guarantees the range is well-covered.
                    continue
                raise ObligationTableError(
                    f"Function '{name}' returns generated sort '{gen_sort}' "
                    f"but is not a constructor of '{gen_sort}' and has no "
                    f"obligation table home (classified as {role.kind.value}). "
                    f"Either add '{name}' to generated_sorts['{gen_sort}'].constructors "
                    f"or ensure it is an observer of another generated sort."
                )

    cells: list[ObligationCell] = []

    for gen_sort in sorted(sig.generated_sorts.keys()):
        info = sig.generated_sorts[gen_sort]
        ctor_names = info.constructors

        # Constructors of this sort (in declared order)
        constructors = [sig.functions[name] for name in ctor_names]

        # Function observers of this sort (including selectors)
        fn_observers = sorted(
            [
                sig.functions[name]
                for name, role in fn_roles.items()
                if role.kind in (FnKind.OBSERVER, FnKind.SELECTOR)
                and role.sort == gen_sort
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

        all_observers: list[FnSymbol | PredSymbol] = [
            *fn_observers,
            *pred_observers,
        ]

        # Check C: Partial observer coverage (warning only)
        from .signature import Totality
        for obs in fn_observers:
            if obs.totality == Totality.PARTIAL:
                # Partial observers usually should be undefined on the base case
                # This is a weak heuristic, just a warning.
                pass

        for ctor in constructors:
            for obs in all_observers:
                # Check for shared key sorts without equality predicates (Check A)
                obs_key_sorts = {p.sort for p in obs.params[1:]}
                ctor_non_state_sorts = {
                    p.sort for p in ctor.params if p.sort != gen_sort
                }
                shared = obs_key_sorts & ctor_non_state_sorts
                for sort in sorted(shared):
                    if sort not in equality_preds:
                        raise ObligationTableError(
                            f"Observer '{obs.name}' and constructor '{ctor.name}' "
                            f"share key sort '{sort}' but no equality predicate "
                            f"'eq_{sort.lower()}' exists in the signature. "
                            "Stage 1 must declare equality predicates for key dispatch sorts."
                        )

                dispatch = _detect_key_dispatch(obs, ctor, equality_preds, gen_sort)
                tier, home_ctor, extracts_param = _compute_tier(
                    obs, ctor, gen_sort, fn_roles, sig, equality_preds
                )
                is_pred = isinstance(obs, PredSymbol)

                if dispatch is not None:
                    key_sort, eq_pred = dispatch
                    cells.append(
                        ObligationCell(
                            observer_name=obs.name,
                            observer_is_predicate=is_pred,
                            constructor_name=ctor.name,
                            generated_sort=gen_sort,
                            dispatch=CellDispatch.HIT,
                            tier=tier,
                            key_sort=key_sort,
                            eq_pred=eq_pred,
                            home_constructor=home_ctor,
                            extracts_param=extracts_param,
                        )
                    )
                    cells.append(
                        ObligationCell(
                            observer_name=obs.name,
                            observer_is_predicate=is_pred,
                            constructor_name=ctor.name,
                            generated_sort=gen_sort,
                            dispatch=CellDispatch.MISS,
                            tier=tier,
                            key_sort=key_sort,
                            eq_pred=eq_pred,
                            home_constructor=home_ctor,
                            extracts_param=extracts_param,
                        )
                    )
                else:
                    cells.append(
                        ObligationCell(
                            observer_name=obs.name,
                            observer_is_predicate=is_pred,
                            constructor_name=ctor.name,
                            generated_sort=gen_sort,
                            dispatch=CellDispatch.PLAIN,
                            tier=tier,
                            home_constructor=home_ctor,
                            extracts_param=extracts_param,
                        )
                    )

    return ObligationTable(
        cells=tuple(cells), fn_roles=fn_roles, pred_roles=pred_roles
    )
