"""Mechanical axiom generation (Stage 3.5).

Generates axioms for obligation cells whose content is fully determined
by the signature structure, requiring no domain knowledge.

Covers three cell tiers:
  - SELECTOR_EXTRACT: sel(ctor(x₁,...,xₙ)) = xᵢ
  - KEY_DISPATCH MISS: ¬eq(k,k2) → obs(ctor(s,k,...),k2,...) = obs(s,k2,...)
  - PRESERVATION: obs(ctor(s,...),k2,...) = obs(s,k2,...)

Formal basis: THEORY.md §§8-9, CASL Reference Manual §2.3.4.
These axioms are theorems of the free type semantics (selectors)
or logical consequences of the frame axiom principle (MISS, PRESERVATION).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from .helpers import app, eq, forall, iff, implication, negation, pred_app, var
from .obligation import (
    CellDispatch,
    CellTier,
    ObligationCell,
    ObligationTable,
)
from .signature import FnSymbol, PredSymbol, Signature, SortRef
from .spec import Axiom
from .terms import Formula, Var

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MechanicalAxiomReport:
    """Result of mechanical axiom generation."""

    axioms: tuple[Axiom, ...]
    cells_covered: tuple[ObligationCell, ...]  # which cells these axioms fill
    cells_skipped: tuple[
        ObligationCell, ...
    ]  # mechanical cells we couldn't generate (errors)


# ---------------------------------------------------------------------------
# Shared helper: variable construction for MISS/PRESERVATION
# ---------------------------------------------------------------------------


def _build_cell_variables(
    cell: ObligationCell,
    sig: Signature,
) -> tuple[
    list[Var],  # all variables (for forall binding)
    list[Var],  # constructor param variables
    list[Var],  # observer lookup param variables (renamed)
    Var | None,  # state variable (first ctor param of generated sort)
    Var | None,  # constructor key variable (for MISS guard)
    Var | None,  # observer key variable (for MISS guard, renamed)
]:
    """Build variable sets for a cell's axiom.

    Follows the renaming convention from ``_structural_hint_parts``
    in ``obligation_render.py``: observer lookup parameters whose name
    collides with a constructor parameter get ``2`` appended.
    """
    ctor = sig.functions[cell.constructor_name]

    if cell.observer_is_predicate:
        obs: FnSymbol | PredSymbol = sig.predicates[cell.observer_name]
    else:
        obs = sig.functions[cell.observer_name]

    gen_sort: SortRef = cell.generated_sort

    # Build ctor param variables
    ctor_vars: list[Var] = [var(p.name, p.sort) for p in ctor.params]
    ctor_param_name_set: set[str] = {p.name for p in ctor.params}

    # Observer lookup params (skip first param which is the state/generated sort)
    obs_lookup_params = list(obs.params[1:])

    # Rename observer lookup params that collide with ctor param names
    obs_vars: list[Var] = []
    for p in obs_lookup_params:
        if p.name in ctor_param_name_set:
            obs_vars.append(var(p.name + "2", p.sort))
        else:
            obs_vars.append(var(p.name, p.sort))

    # All variables for forall binding (ctor first, then obs)
    all_vars: list[Var] = ctor_vars + obs_vars

    # State variable: first ctor param whose sort is the generated sort
    state_var: Var | None = None
    for v in ctor_vars:
        if v.sort == gen_sort:
            state_var = v
            break

    # Key variables (for MISS guard)
    ctor_key_var: Var | None = None
    obs_key_var: Var | None = None

    if cell.key_sort is not None:
        # Find the ctor param with the key sort (skip state param)
        for v in ctor_vars:
            if v.sort == cell.key_sort and v.sort != gen_sort:
                ctor_key_var = v
                break

        # Find the observer lookup param with the key sort (renamed)
        for v in obs_vars:
            if v.sort == cell.key_sort:
                obs_key_var = v
                break

    return all_vars, ctor_vars, obs_vars, state_var, ctor_key_var, obs_key_var


# ---------------------------------------------------------------------------
# Tier generators
# ---------------------------------------------------------------------------


def _generate_selector_extract(
    cell: ObligationCell,
    sig: Signature,
) -> Axiom:
    """Generate sel(ctor(x₁,...,xₙ)) = xᵢ for a SELECTOR_EXTRACT cell.

    Finds which constructor parameter the selector extracts by matching
    the selector's result sort against the constructor's parameter sorts.
    Uses the declared selector info from generated_sorts to resolve
    ambiguity when multiple parameters share the same sort.
    """
    sel = sig.functions[cell.observer_name]
    ctor = sig.functions[cell.constructor_name]
    gen_sort = cell.generated_sort

    # The extracts_sort from the cell tells us which sort this selector extracts.
    # The selector declaration in generated_sorts maps sel_name -> result_sort.
    extracts_sort = cell.extracts_sort
    if extracts_sort is None:
        # Fall back to the selector's result sort
        extracts_sort = sel.result

    # Build variables for all constructor parameters
    ctor_vars: list[Var] = [var(p.name, p.sort) for p in ctor.params]
    ctor_var_terms = ctor_vars  # Var is a Term

    # Find the constructor parameter that this selector extracts.
    # Use the selector map from generated_sorts for precise identification.\n    # Look up the generated sort info to determine which param the selector extracts.

    # The selector map tells us the result sort; we need to find WHICH param.
    # The extracts_sort should match one ctor param's sort.
    # When multiple params have the same sort, the selector declaration
    # in generated_sorts disambiguates by result sort. But if the extracts_sort
    # matches multiple params, we pick the right one by convention:
    # - if extracts_sort == gen_sort, the selector extracts the state param
    # - otherwise, the first non-state param matching extracts_sort

    extracted_var: Var | None = None

    if extracts_sort == gen_sort:
        # Selector extracts the state component (like pop extracting Stack from push)
        for v in ctor_vars:
            if v.sort == gen_sort:
                extracted_var = v
                break
    else:
        # Selector extracts a non-state component
        # Find first ctor param whose sort matches extracts_sort AND is NOT the gen sort
        for v in ctor_vars:
            if v.sort == extracts_sort and v.sort != gen_sort:
                extracted_var = v
                break

    if extracted_var is None:
        raise ValueError(
            f"Cannot determine which parameter selector '{sel.name}' extracts "
            f"from constructor '{ctor.name}'. Expected a param of sort '{extracts_sort}' "
            f"but found params: {[(p.name, p.sort) for p in ctor.params]}"
        )

    # Build the axiom: forall(vars, eq(sel(ctor(vars)), extracted_var))
    ctor_app = app(ctor.name, *ctor_var_terms)
    sel_app = app(sel.name, ctor_app)

    formula: Formula = eq(sel_app, extracted_var)

    # Only wrap in forall if there are variables to bind
    if ctor_vars:
        formula = forall(ctor_vars, formula)

    label = f"{sel.name}_{ctor.name}_extract"
    return Axiom(label=label, formula=formula)


def _generate_miss(
    cell: ObligationCell,
    sig: Signature,
) -> Axiom:
    """Generate ¬eq(k,k2) → obs(ctor(s,...),k2,...) = obs(s,k2,...) for a MISS cell.

    The frame axiom: when keys don't match, the observation delegates
    to the pre-state.
    """
    all_vars, ctor_vars, obs_vars, state_var, ctor_key_var, obs_key_var = (
        _build_cell_variables(cell, sig)
    )

    if state_var is None:
        raise ValueError(
            f"Cannot find state variable for MISS cell "
            f"({cell.observer_name}, {cell.constructor_name}): "
            f"no constructor parameter has sort '{cell.generated_sort}'"
        )

    if ctor_key_var is None or obs_key_var is None:
        raise ValueError(
            f"Cannot find key variables for MISS cell "
            f"({cell.observer_name}, {cell.constructor_name}): "
            f"key_sort='{cell.key_sort}', eq_pred='{cell.eq_pred}'"
        )

    if cell.eq_pred is None:
        raise ValueError(
            f"MISS cell ({cell.observer_name}, {cell.constructor_name}) "
            f"has no eq_pred set"
        )

    ctor = sig.functions[cell.constructor_name]

    # Build the guard: ¬eq_pred(ctor_key, obs_key)
    guard = negation(pred_app(cell.eq_pred, ctor_key_var, obs_key_var))

    # Build LHS: obs(ctor(all_ctor_params), obs_lookup_params...)
    ctor_app = app(ctor.name, *ctor_vars)

    # Build RHS (delegation): obs(state_var, obs_lookup_params...)
    if cell.observer_is_predicate:
        lhs_pred = pred_app(cell.observer_name, ctor_app, *obs_vars)
        rhs_pred = pred_app(cell.observer_name, state_var, *obs_vars)
        consequent: Formula = iff(lhs_pred, rhs_pred)
    else:
        lhs_app = app(cell.observer_name, ctor_app, *obs_vars)
        rhs_app = app(cell.observer_name, state_var, *obs_vars)
        consequent = eq(lhs_app, rhs_app)

    formula: Formula = forall(all_vars, implication(guard, consequent))

    label = f"{cell.observer_name}_{cell.constructor_name}_miss"
    return Axiom(label=label, formula=formula)


def _generate_preservation(
    cell: ObligationCell,
    sig: Signature,
) -> Axiom:
    """Generate obs(ctor(s,...),k2,...) = obs(s,k2,...) for a PRESERVATION cell.

    The strongest frame axiom: the constructor doesn't take the observer's
    key sort at all, so the observation unconditionally delegates.
    """
    all_vars, ctor_vars, obs_vars, state_var, _, _ = _build_cell_variables(cell, sig)

    if state_var is None:
        raise ValueError(
            f"Cannot find state variable for PRESERVATION cell "
            f"({cell.observer_name}, {cell.constructor_name}): "
            f"no constructor parameter has sort '{cell.generated_sort}'"
        )

    ctor = sig.functions[cell.constructor_name]

    # Build LHS: obs(ctor(all_ctor_params), obs_lookup_params...)
    ctor_app = app(ctor.name, *ctor_vars)

    # Build RHS (delegation): obs(state_var, obs_lookup_params...)
    if cell.observer_is_predicate:
        lhs_pred = pred_app(cell.observer_name, ctor_app, *obs_vars)
        rhs_pred = pred_app(cell.observer_name, state_var, *obs_vars)
        body: Formula = iff(lhs_pred, rhs_pred)
    else:
        lhs_app = app(cell.observer_name, ctor_app, *obs_vars)
        rhs_app = app(cell.observer_name, state_var, *obs_vars)
        body = eq(lhs_app, rhs_app)

    formula: Formula = forall(all_vars, body)

    label = f"{cell.observer_name}_{cell.constructor_name}_preserve"
    return Axiom(label=label, formula=formula)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

_MECHANICAL_TIERS: frozenset[CellTier] = frozenset(
    {
        CellTier.SELECTOR_EXTRACT,
    }
)

_MECHANICAL_DISPATCHES: frozenset[tuple[CellTier, CellDispatch]] = frozenset(
    {
        (CellTier.KEY_DISPATCH, CellDispatch.MISS),
    }
)

_MECHANICAL_PRESERVATION: frozenset[CellTier] = frozenset(
    {
        CellTier.PRESERVATION,
    }
)


def generate_mechanical_axioms(
    sig: Signature,
    table: ObligationTable,
) -> MechanicalAxiomReport:
    """Generate axioms for all mechanical cells in the obligation table.

    Returns a report containing:
      - axioms: the generated Axiom objects
      - cells_covered: which obligation cells these axioms satisfy
      - cells_skipped: cells that should have been mechanical but failed generation

    Every generated axiom is well-sorted by construction (uses helpers that
    enforce sort constraints). The caller SHOULD still run check_spec on
    the combined spec as a defense-in-depth measure.
    """
    axioms: list[Axiom] = []
    covered: list[ObligationCell] = []
    skipped: list[ObligationCell] = []

    for cell in table.cells:
        generator = _select_generator(cell)
        if generator is None:
            continue

        try:
            axiom = generator(cell, sig)
            axioms.append(axiom)
            covered.append(cell)
        except Exception as exc:
            logger.warning(
                "Failed to generate mechanical axiom for (%s, %s, %s): %s",
                cell.observer_name,
                cell.constructor_name,
                cell.dispatch.value,
                exc,
            )
            skipped.append(cell)

    logger.info(
        "Mechanical axiom generation: %d axioms generated, %d cells covered, %d skipped",
        len(axioms),
        len(covered),
        len(skipped),
    )

    return MechanicalAxiomReport(
        axioms=tuple(axioms),
        cells_covered=tuple(covered),
        cells_skipped=tuple(skipped),
    )


def _select_generator(
    cell: ObligationCell,
) -> (
    type[None]
    | type[
        # Using a callable type alias is verbose; just describe the pattern
        None
    ]
):
    """Determine which generator (if any) handles a cell.

    Returns the generator function or None if the cell is not mechanical.
    """
    # SELECTOR_EXTRACT: any dispatch (always PLAIN for selectors)
    if cell.tier == CellTier.SELECTOR_EXTRACT:
        return _generate_selector_extract  # type: ignore[return-value]

    # KEY_DISPATCH MISS only
    if cell.tier == CellTier.KEY_DISPATCH and cell.dispatch == CellDispatch.MISS:
        return _generate_miss  # type: ignore[return-value]

    # PRESERVATION: any dispatch (always PLAIN for preservation)
    if cell.tier == CellTier.PRESERVATION:
        return _generate_preservation  # type: ignore[return-value]

    return None  # type: ignore[return-value]
