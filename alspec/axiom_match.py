"""Axiom-to-cell matching (Phase 4).

Given a Spec (with axioms) and an ObligationTable, determine which axiom(s)
fill which cell(s), and report uncovered cells and unmatched axioms.

Design principles:
- Fail loud, fail fast — no silent fallbacks.
- Every unrecognized formula shape returns UNMATCHED with a logged warning.
- Type-narrow with match/case throughout; all branches are exhaustive.
- No print statements; all diagnostics go through logging.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum

from .obligation import (
    CellDispatch,
    FnKind,
    FnRole,
    ObligationCell,
    ObligationTable,
    PredKind,
    PredRole,
)
from .signature import Signature
from .spec import Axiom, Spec
from .terms import (
    Biconditional,
    Conjunction,
    Definedness,
    Disjunction,
    Equation,
    ExistentialQuant,
    FieldAccess,
    FnApp,
    Formula,
    Implication,
    Literal,
    Negation,
    PredApp,
    Term,
    UniversalQuant,
    Var,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


class MatchKind(Enum):
    """How an axiom relates to obligation cells."""

    DIRECT = "direct"               # one axiom → one cell (or one PLAIN cell)
    PRESERVATION = "preservation"   # one axiom → HIT+MISS cells (no dispatch guard)
    CONSTRUCTOR_DEF = "constructor_def"  # iff(Definedness(ctor(...)), guard) — not a cell
    BASIS = "basis"                 # eq_pred reflexivity/symmetry/transitivity — not a cell
    UNMATCHED = "unmatched"         # could not determine cell


@dataclass(frozen=True)
class AxiomCellMatch:
    """Result of matching one axiom to obligation cells."""

    axiom_label: str
    cells: tuple[ObligationCell, ...]   # which cells this axiom fills
    kind: MatchKind
    reason: str = ""                     # human-readable explanation (especially for UNMATCHED)


class CoverageStatus(Enum):
    COVERED = "covered"          # exactly one axiom
    MULTI_COVERED = "multi"      # multiple axioms (sub-cases like queue, door-lock)
    UNCOVERED = "uncovered"      # no axiom matches this cell


@dataclass(frozen=True)
class CellCoverage:
    """Coverage status of a single obligation cell."""

    cell: ObligationCell
    axiom_labels: tuple[str, ...]
    status: CoverageStatus


@dataclass(frozen=True)
class MatchReport:
    """Complete matching report for a spec against its obligation table."""

    matches: tuple[AxiomCellMatch, ...]
    coverage: tuple[CellCoverage, ...]
    # Convenience aggregates
    uncovered_cells: tuple[ObligationCell, ...]
    unmatched_axioms: tuple[str, ...]
    non_cell_axioms: tuple[str, ...]   # BASIS + CONSTRUCTOR_DEF labels


# ---------------------------------------------------------------------------
# Top-level API
# ---------------------------------------------------------------------------


async def match_spec(
    spec: Spec,
    table: ObligationTable,
    sig: Signature,
) -> MatchReport:
    """Match all axioms in a spec against the obligation table.

    This is the main entry point. It:
    1. Matches each axiom to zero or more cells
    2. Computes cell coverage
    3. Returns a complete diagnostic report

    Raises AssertionError if the table and signature are inconsistent.
    """
    _validate_table_signature_consistency(table, sig)

    matches: list[AxiomCellMatch] = []
    for axiom in spec.axioms:
        m = await _match_axiom(axiom, table, sig)
        matches.append(m)

        if m.kind == MatchKind.UNMATCHED:
            logger.warning("UNMATCHED axiom %r: %s", axiom.label, m.reason)
        elif m.kind == MatchKind.PRESERVATION:
            logger.debug(
                "PRESERVATION axiom %r covers %d cells: %s",
                axiom.label,
                len(m.cells),
                [
                    (c.observer_name, c.constructor_name, c.dispatch.value)
                    for c in m.cells
                ],
            )

    coverage = _compute_coverage(matches, table)

    uncovered = tuple(cc.cell for cc in coverage if cc.status == CoverageStatus.UNCOVERED)
    unmatched = tuple(m.axiom_label for m in matches if m.kind == MatchKind.UNMATCHED)
    non_cell = tuple(
        m.axiom_label for m in matches
        if m.kind in (MatchKind.CONSTRUCTOR_DEF, MatchKind.BASIS)
    )

    if uncovered:
        logger.warning(
            "%d UNCOVERED cells: %s",
            len(uncovered),
            [
                (c.observer_name, c.constructor_name, c.dispatch.value)
                for c in uncovered
            ],
        )
    if unmatched:
        logger.warning("%d UNMATCHED axioms: %s", len(unmatched), unmatched)

    return MatchReport(
        matches=tuple(matches),
        coverage=coverage,
        uncovered_cells=uncovered,
        unmatched_axioms=unmatched,
        non_cell_axioms=non_cell,
    )


# ---------------------------------------------------------------------------
# Synchronous public helper (wraps the async implementation)
# ---------------------------------------------------------------------------


def match_spec_sync(
    spec: Spec,
    table: ObligationTable,
    sig: Signature,
) -> MatchReport:
    """Synchronous wrapper around match_spec. Use in tests and CLI."""
    import asyncio

    return asyncio.run(match_spec(spec, table, sig))


# ---------------------------------------------------------------------------
# Core matching algorithm
# ---------------------------------------------------------------------------


async def _match_axiom(
    axiom: Axiom,
    table: ObligationTable,
    sig: Signature,
) -> AxiomCellMatch:
    """Match a single axiom to its obligation cell(s)."""
    body = _peel_quantifiers(axiom.formula)

    # 1. Special case: constructor definedness biconditional
    if _is_constructor_def(body, table.fn_roles):
        logger.debug("Axiom %r classified as CONSTRUCTOR_DEF", axiom.label)
        return AxiomCellMatch(axiom.label, (), MatchKind.CONSTRUCTOR_DEF)

    # 2. Special case: eq_pred basis axiom
    if _is_basis_axiom(body, table.pred_roles, table.fn_roles):
        logger.debug("Axiom %r classified as BASIS", axiom.label)
        return AxiomCellMatch(axiom.label, (), MatchKind.BASIS)

    # 3. Peel implications, collecting guards
    guards, conclusion = _peel_implications(body)

    # 4. Find observer(constructor(...)) in the conclusion
    obs_ctor = _find_obs_ctor(conclusion, table.fn_roles, table.pred_roles)
    if obs_ctor is None:
        return AxiomCellMatch(
            axiom.label,
            (),
            MatchKind.UNMATCHED,
            reason=(
                f"Could not find observer(constructor(...)) pattern in conclusion: "
                f"{type(conclusion).__name__}"
            ),
        )

    obs_name, is_pred, ctor_name = obs_ctor
    logger.debug(
        "Axiom %r: extracted (%s, %s, pred=%s)", axiom.label, obs_name, ctor_name, is_pred
    )

    # 5. Look up candidate cells in the table
    candidates = [
        c
        for c in table.cells
        if c.observer_name == obs_name and c.constructor_name == ctor_name
    ]
    if not candidates:
        return AxiomCellMatch(
            axiom.label,
            (),
            MatchKind.UNMATCHED,
            reason=f"No obligation cell for ({obs_name}, {ctor_name})",
        )

    # 6. Determine dispatch based on table structure + guards
    return _resolve_dispatch(axiom.label, candidates, guards)


# ---------------------------------------------------------------------------
# Quantifier and Implication peeling
# ---------------------------------------------------------------------------


def _peel_quantifiers(f: Formula) -> Formula:
    """Strip universal/existential quantifier wrappers."""
    while isinstance(f, (UniversalQuant, ExistentialQuant)):
        f = f.body
    return f


def _peel_implications(f: Formula) -> tuple[list[Formula], Formula]:
    """Collect implication antecedents, returning (guards, conclusion).

    Handles nested implications:
        Implication(A, Implication(B, C)) → guards=[A, B], conclusion=C
    """
    guards: list[Formula] = []
    while isinstance(f, Implication):
        guards.append(f.antecedent)
        f = f.consequent
    return guards, f


# ---------------------------------------------------------------------------
# Special-case classifiers
# ---------------------------------------------------------------------------


def _is_constructor_def(f: Formula, fn_roles: dict[str, FnRole]) -> bool:
    """Detect constructor definedness biconditional (Group K).

    Pattern: iff(Definedness(ctor_app), guard) where ctor is a constructor.
    These are NOT obligation cells — they define when a partial constructor is valid.
    """
    if not isinstance(f, Biconditional):
        return False
    for side in (f.lhs, f.rhs):
        if isinstance(side, Definedness) and isinstance(side.term, FnApp):
            role = fn_roles.get(side.term.fn_name)
            if role is not None and role.kind == FnKind.CONSTRUCTOR:
                return True
    return False


def _is_basis_axiom(
    f: Formula,
    pred_roles: dict[str, PredRole],
    fn_roles: dict[str, FnRole] | None = None,
) -> bool:
    """Detect eq_pred basis axioms (Group L).

    Heuristic: the formula's only predicate references are equality predicates,
    at least one eq_pred is used, and no observer/constructor/selector function
    applications appear anywhere in the formula.

    The third condition is critical: axioms like `get_state_lock_hit` use eq_pred
    ONLY as a guard, not as the conclusion. They must not be classified as basis.
    """
    eq_pred_names = frozenset(
        n for n, r in pred_roles.items() if r.kind == PredKind.EQUALITY
    )
    if not eq_pred_names:
        return False

    preds_used = _collect_pred_names(f)

    # Must actually use an eq_pred (not just an empty formula)
    if not preds_used:
        return False

    # All predicates used must be eq_preds
    if not preds_used.issubset(eq_pred_names):
        return False

    # No observer/constructor/selector function applications may appear.
    # Basis axioms (reflexivity, symmetry, transitivity) only involve variables
    # and the eq_pred itself — never obs(ctor(...)) patterns.
    if fn_roles is not None:
        fn_names_used = _collect_fn_names(f)
        distinguished_kinds = (FnKind.OBSERVER, FnKind.CONSTRUCTOR, FnKind.SELECTOR)
        for fn_name in fn_names_used:
            role = fn_roles.get(fn_name)
            if role is not None and role.kind in distinguished_kinds:
                return False

    return True


# ---------------------------------------------------------------------------
# Core pattern extraction
# ---------------------------------------------------------------------------


def _find_obs_ctor(
    f: Formula,
    fn_roles: dict[str, FnRole],
    pred_roles: dict[str, PredRole],
) -> tuple[str, bool, str] | None:
    """Find (observer_name, is_predicate, constructor_name) in a formula.

    Searches for the pattern: observer applied to a constructor-rooted first argument.
    Returns None if no pattern found.
    """
    match f:
        case Equation(lhs, rhs):
            result = _extract_from_term(lhs, fn_roles)
            if result is not None:
                return result
            result = _extract_from_term(rhs, fn_roles)
            if result is not None:
                logger.debug("Found obs(ctor(...)) on RHS of equation — unusual but valid")
                return result
            return None

        case PredApp(pred_name, args) if args:
            role = pred_roles.get(pred_name)
            if role is not None and role.kind == PredKind.OBSERVER:
                ctor = _ctor_root(args[0], fn_roles)
                if ctor is not None:
                    return (pred_name, True, ctor)
            return None

        case Negation(inner):
            return _find_obs_ctor(inner, fn_roles, pred_roles)

        case Biconditional(lhs, rhs):
            result = _find_obs_ctor(lhs, fn_roles, pred_roles)
            if result is not None:
                return result
            result = _find_obs_ctor(rhs, fn_roles, pred_roles)
            if result is not None:
                logger.debug("Found obs(ctor(...)) on RHS of biconditional")
                return result
            return None

        case Definedness(term):
            return _extract_from_term(term, fn_roles)

        case Conjunction(conjuncts):
            for c in conjuncts:
                result = _find_obs_ctor(c, fn_roles, pred_roles)
                if result is not None:
                    return result
            return None

        case Disjunction(disjuncts):
            for d in disjuncts:
                result = _find_obs_ctor(d, fn_roles, pred_roles)
                if result is not None:
                    return result
            return None

        case Implication(_, consequent):
            # Shouldn't happen (already peeled), but handle defensively
            logger.debug(
                "_find_obs_ctor: unexpected Implication — peeling missed one?"
            )
            return _find_obs_ctor(consequent, fn_roles, pred_roles)

        case PredApp(_, _):
            # PredApp with no args, or not an observer — no match
            return None

        case _:
            logger.debug(
                "_find_obs_ctor: unhandled formula type %s", type(f).__name__
            )
            return None


def _extract_from_term(
    term: Term,
    fn_roles: dict[str, FnRole],
) -> tuple[str, bool, str] | None:
    """Check if term is observer(constructor(...), ...).

    The observer must be classified as OBSERVER or SELECTOR.
    The first argument must be a constructor-rooted term.
    """
    match term:
        case FnApp(fn_name, args) if args:
            role = fn_roles.get(fn_name)
            if role is not None and role.kind in (FnKind.OBSERVER, FnKind.SELECTOR):
                ctor = _ctor_root(args[0], fn_roles)
                if ctor is not None:
                    return (fn_name, False, ctor)
        case _:
            pass
    return None


def _ctor_root(term: Term, fn_roles: dict[str, FnRole]) -> str | None:
    """If the term's outermost function application is a constructor, return its name.

    Only checks the outermost level — does not recurse into arguments.
    In `obs(ctor(inner_ctor(...)))`, we want the outer `ctor`, not the inner one.
    """
    match term:
        case FnApp(fn_name, _):
            role = fn_roles.get(fn_name)
            if role is not None and role.kind == FnKind.CONSTRUCTOR:
                return fn_name
        case _:
            pass
    return None


# ---------------------------------------------------------------------------
# Dispatch resolution
# ---------------------------------------------------------------------------


def _resolve_dispatch(
    label: str,
    candidates: list[ObligationCell],
    guards: list[Formula],
) -> AxiomCellMatch:
    """Resolve which candidate cells an axiom matches, using guards for disambiguation.

    Rules:
    1. If all candidates are PLAIN → always DIRECT, ignore guards entirely.
    2. If candidates include HIT+MISS → check guards for the specific eq_pred
       declared in those cells:
       a. eq_pred positive in guard → HIT
       b. eq_pred negated in guard → MISS
       c. No eq_pred guard found → PRESERVATION (covers both HIT+MISS)
    3. Ambiguous guard (multiple eq_preds) → UNMATCHED with warning.
    """
    dispatches = {c.dispatch for c in candidates}

    # Case 1: All PLAIN — ignore guards entirely
    if dispatches == {CellDispatch.PLAIN}:
        return AxiomCellMatch(label, tuple(candidates), MatchKind.DIRECT)

    # Case 2: HIT + MISS present
    if CellDispatch.HIT in dispatches and CellDispatch.MISS in dispatches:
        cell_eq_preds: set[str] = {
            c.eq_pred for c in candidates if c.eq_pred is not None
        }

        if len(cell_eq_preds) > 1:
            logger.warning(
                "Axiom %r: multiple eq_preds %s for candidates — cannot disambiguate",
                label,
                cell_eq_preds,
            )
            return AxiomCellMatch(
                label,
                (),
                MatchKind.UNMATCHED,
                reason=f"Multiple eq_preds in candidate cells: {cell_eq_preds}",
            )

        dispatch = _classify_guard(guards, cell_eq_preds)

        if dispatch is None:
            # No eq_pred guard → preservation axiom covering all keys
            logger.debug(
                "Axiom %r: no eq_pred guard in %d guards — classifying as PRESERVATION",
                label,
                len(guards),
            )
            return AxiomCellMatch(label, tuple(candidates), MatchKind.PRESERVATION)

        matched = [c for c in candidates if c.dispatch == dispatch]
        assert matched, (
            f"dispatch={dispatch} but no candidates match — table is inconsistent"
        )
        return AxiomCellMatch(label, tuple(matched), MatchKind.DIRECT)

    # Case 3: Only HIT or only MISS (shouldn't happen — table always emits pairs)
    logger.warning(
        "Axiom %r: unexpected dispatch set %s — expected PLAIN or HIT+MISS",
        label,
        dispatches,
    )
    return AxiomCellMatch(
        label,
        tuple(candidates),
        MatchKind.DIRECT,
        reason=f"Unexpected dispatch set: {dispatches}",
    )


def _classify_guard(
    guards: list[Formula],
    cell_eq_preds: set[str],
) -> CellDispatch | None:
    """Check if any guard contains a cell's eq_pred, returning HIT, MISS, or None.

    Only looks for the SPECIFIC eq_preds from the obligation table cells.
    This prevents false matching on domain-level eq_pred guards (like door-lock's
    eq_code in a state transition guard for a PLAIN cell).

    Returns on first match. If no guard references any cell eq_pred, returns None
    (preservation case).
    """
    for guard in guards:
        match guard:
            case PredApp(pred_name, _) if pred_name in cell_eq_preds:
                return CellDispatch.HIT

            case Negation(PredApp(pred_name, _)) if pred_name in cell_eq_preds:
                return CellDispatch.MISS

            case Conjunction(conjuncts):
                for c in conjuncts:
                    if isinstance(c, PredApp) and c.pred_name in cell_eq_preds:
                        return CellDispatch.HIT

            case Negation(Conjunction(conjuncts)):
                for c in conjuncts:
                    if isinstance(c, PredApp) and c.pred_name in cell_eq_preds:
                        return CellDispatch.MISS

            case _:
                continue

    return None


# ---------------------------------------------------------------------------
# Coverage computation
# ---------------------------------------------------------------------------


def _compute_coverage(
    matches: list[AxiomCellMatch],
    table: ObligationTable,
) -> tuple[CellCoverage, ...]:
    """Compute per-cell coverage from match results."""
    cell_to_labels: dict[ObligationCell, list[str]] = {c: [] for c in table.cells}

    for m in matches:
        for cell in m.cells:
            if cell in cell_to_labels:
                cell_to_labels[cell].append(m.axiom_label)
            else:
                logger.error(
                    "Axiom %r matched cell (%s, %s, %s) not in obligation table",
                    m.axiom_label,
                    cell.observer_name,
                    cell.constructor_name,
                    cell.dispatch.value,
                )

    result: list[CellCoverage] = []
    for cell, labels in cell_to_labels.items():
        if not labels:
            status = CoverageStatus.UNCOVERED
        elif len(labels) == 1:
            status = CoverageStatus.COVERED
        else:
            status = CoverageStatus.MULTI_COVERED
        result.append(CellCoverage(cell, tuple(labels), status))

    return tuple(result)


# ---------------------------------------------------------------------------
# Precondition validation
# ---------------------------------------------------------------------------


def _validate_table_signature_consistency(
    table: ObligationTable,
    sig: Signature,
) -> None:
    """Assert that the obligation table is consistent with the signature.

    Raises AssertionError on inconsistency. This is a programming error,
    not a user error — it means the table was built from a different signature.
    """
    for cell in table.cells:
        assert (
            cell.observer_name in sig.functions
            or cell.observer_name in sig.predicates
        ), f"Cell observer {cell.observer_name!r} not in signature"
        assert cell.constructor_name in sig.functions, (
            f"Cell constructor {cell.constructor_name!r} not in signature functions"
        )


# ---------------------------------------------------------------------------
# AST traversal helpers
# ---------------------------------------------------------------------------


def _collect_pred_names(f: Formula) -> set[str]:
    """Collect all predicate names used anywhere in a formula.

    Exhaustive over Formula union. Raises TypeError on unknown node types.
    """
    result: set[str] = set()
    _walk_formula_preds(f, result)
    return result


def _walk_formula_preds(f: Formula, acc: set[str]) -> None:
    match f:
        case PredApp(pred_name, args):
            acc.add(pred_name)
            for a in args:
                _walk_term_preds(a, acc)
        case Equation(lhs, rhs):
            _walk_term_preds(lhs, acc)
            _walk_term_preds(rhs, acc)
        case Negation(inner):
            _walk_formula_preds(inner, acc)
        case Conjunction(conjuncts):
            for c in conjuncts:
                _walk_formula_preds(c, acc)
        case Disjunction(disjuncts):
            for d in disjuncts:
                _walk_formula_preds(d, acc)
        case Implication(ant, con):
            _walk_formula_preds(ant, acc)
            _walk_formula_preds(con, acc)
        case Biconditional(lhs, rhs):
            _walk_formula_preds(lhs, acc)
            _walk_formula_preds(rhs, acc)
        case UniversalQuant(_, body):
            _walk_formula_preds(body, acc)
        case ExistentialQuant(_, body):
            _walk_formula_preds(body, acc)
        case Definedness(term):
            _walk_term_preds(term, acc)
        case _:
            raise TypeError(
                f"_walk_formula_preds: unexpected node type {type(f).__name__}"
            )


def _walk_term_preds(t: Term, acc: set[str]) -> None:
    """Terms don't contain predicates, but walk for completeness."""
    match t:
        case Var(_, _):
            pass
        case FnApp(_, args):
            for a in args:
                _walk_term_preds(a, acc)
        case FieldAccess(inner, _):
            _walk_term_preds(inner, acc)
        case Literal(_, _):
            pass
        case _:
            raise TypeError(
                f"_walk_term_preds: unexpected node type {type(t).__name__}"
            )


def _collect_fn_names(f: Formula) -> set[str]:
    """Collect all function names used anywhere in a formula."""
    result: set[str] = set()
    _walk_formula_fns(f, result)
    return result


def _walk_formula_fns(f: Formula, acc: set[str]) -> None:
    match f:
        case PredApp(_, args):
            for a in args:
                _walk_term_fns(a, acc)
        case Equation(lhs, rhs):
            _walk_term_fns(lhs, acc)
            _walk_term_fns(rhs, acc)
        case Negation(inner):
            _walk_formula_fns(inner, acc)
        case Conjunction(conjuncts):
            for c in conjuncts:
                _walk_formula_fns(c, acc)
        case Disjunction(disjuncts):
            for d in disjuncts:
                _walk_formula_fns(d, acc)
        case Implication(ant, con):
            _walk_formula_fns(ant, acc)
            _walk_formula_fns(con, acc)
        case Biconditional(lhs, rhs):
            _walk_formula_fns(lhs, acc)
            _walk_formula_fns(rhs, acc)
        case UniversalQuant(_, body):
            _walk_formula_fns(body, acc)
        case ExistentialQuant(_, body):
            _walk_formula_fns(body, acc)
        case Definedness(term):
            _walk_term_fns(term, acc)
        case _:
            raise TypeError(
                f"_walk_formula_fns: unexpected node type {type(f).__name__}"
            )


def _walk_term_fns(t: Term, acc: set[str]) -> None:
    match t:
        case Var(_, _):
            pass
        case FnApp(fn_name, args):
            acc.add(fn_name)
            for a in args:
                _walk_term_fns(a, acc)
        case FieldAccess(inner, _):
            _walk_term_fns(inner, acc)
        case Literal(_, _):
            pass
        case _:
            raise TypeError(
                f"_walk_term_fns: unexpected node type {type(t).__name__}"
            )
