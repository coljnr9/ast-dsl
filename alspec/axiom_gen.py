"""Mechanical axiom generation (Stage 3.5).

Generates axioms for obligation cells whose content is fully determined
by the signature structure, requiring no domain knowledge.

Covers two mechanical patterns:
  - SELECTOR_EXTRACT (PLAIN or HIT dispatch):
      PLAIN: sel(ctor(x₁,...,xₙ)) = xᵢ
      HIT:   eq_k(k, k2) → sel(ctor(...,k,...), k2) = xᵢ
  - Any MISS dispatch: ¬eq(k,k2) → obs(ctor(s,k,...),k2,...) = obs(s,k2,...)

Dispatch is checked BEFORE tier. A SELECTOR_EXTRACT cell with MISS dispatch
routes to _generate_miss (the locality/frame axiom), not _generate_selector_extract.
This is correct: MISS dispatch is a structural consequence of key dispatch
decomposition, independent of the obs↔ctor tier classification.

For a keyed selector (SELECTOR_EXTRACT + HIT), the axiom is:
    ∀ ctor_vars, obs_vars . eq_k(ctor_key, obs_key) →
        sel(ctor(ctor_vars...), obs_vars...) = extracted_param

For an unkeyed selector (SELECTOR_EXTRACT + PLAIN), no guard or obs vars:
    ∀ ctor_vars . sel(ctor(ctor_vars...)) = extracted_param

Formal basis: CASL Reference Manual §2.3.4 (selector axioms from free type
declarations), §5.2.2 (conditional axioms), and the McCarthy store axiom
(select/store with equality). See also CASL standard library Map spec
and Sannella & Tarlecki (2012) §2.4.

PRESERVATION is NOT generated mechanically. The absence of a shared key sort
does not imply non-interference — the constructor may affect all keys through
domain logic. PRESERVATION remains as an informational tier hint in the
obligation table, but axiom content is determined by the LLM.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from .helpers import (
    app,
    conjunction,
    definedness,
    disjunction,
    eq,
    exists,
    field_access,
    forall,
    iff,
    implication,
    negation,
    pred_app,
    var,
)
from .obligation import (
    CellDispatch,
    CellTier,
    ObligationCell,
    ObligationTable,
)
from .signature import FnSymbol, PredSymbol, Signature, SortRef
from .spec import Axiom
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
    """Generate the extraction axiom for a SELECTOR_EXTRACT cell.

    For PLAIN dispatch (no shared key sort), the unguarded form:
        ∀ ctor_vars . sel(ctor(ctor_vars...)) = extracted_param

    For HIT dispatch (selector shares a key sort with its home constructor),
    the guarded form with the observer's key lookup parameter:
        ∀ ctor_vars, obs_vars . eq_k(ctor_key, obs_key) →
            sel(ctor(ctor_vars...), obs_vars...) = extracted_param

    Uses _build_cell_variables for consistent variable naming (observer lookup
    params whose names collide with constructor params get '2' appended).

    Note: MISS dispatch cells are never passed here — _select_generator checks
    MISS BEFORE SELECTOR_EXTRACT, routing them to _generate_miss instead.
    """
    ctor = sig.functions[cell.constructor_name]

    # The selector map gives us the param name directly.
    param_name = cell.extracts_param
    if param_name is None:
        raise ValueError(
            f"Selector '{cell.observer_name}' has no param mapping for "
            f"constructor '{cell.constructor_name}' (extracts_param is None)"
        )

    # Use _build_cell_variables for consistent naming (handles collision renaming)
    all_vars, ctor_vars, obs_vars, _state_var, ctor_key_var, obs_key_var = (
        _build_cell_variables(cell, sig)
    )

    # Find the extracted variable by param name in ctor_vars
    extracted_var: Var | None = None
    for v in ctor_vars:
        if v.name == param_name:
            extracted_var = v
            break

    if extracted_var is None:
        raise ValueError(
            f"Selector '{cell.observer_name}' maps to param '{param_name}' "
            f"but constructor '{cell.constructor_name}' has no such param. "
            f"Params: {[(p.name, p.sort) for p in ctor.params]}"
        )

    # Build: sel(ctor(ctor_vars...), obs_vars...) = extracted_var
    ctor_app = app(ctor.name, *ctor_vars)
    sel_app = app(cell.observer_name, ctor_app, *obs_vars)
    body: Formula = eq(sel_app, extracted_var)

    # For HIT dispatch, wrap in the equality guard
    if cell.dispatch == CellDispatch.HIT and ctor_key_var is not None and obs_key_var is not None:
        if cell.eq_pred is None:
            raise ValueError(
                f"SELECTOR_EXTRACT HIT cell ({cell.observer_name}, {cell.constructor_name}) "
                f"has no eq_pred set"
            )
        guard = pred_app(cell.eq_pred, ctor_key_var, obs_key_var)
        body = implication(guard, body)

    formula: Formula = forall(all_vars, body) if all_vars else body

    label = f"{cell.observer_name}_{ctor.name}_extract"
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

    NOTE: This function is NOT called by generate_mechanical_axioms().
    PRESERVATION is not mechanically justified — the absence of a shared key
    sort does not imply non-interference. This function is retained as a
    utility for potential future opt-in use (e.g., user-confirmed preservation).

    If called, it generates the unconditional delegation axiom.
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

# Any MISS dispatch cell is mechanical — the locality/frame axiom applies
# regardless of tier. This replaces the old (CellTier.KEY_DISPATCH, MISS)
# pair because tier and dispatch are independent classification axes.
_MECHANICAL_DISPATCHES: frozenset[CellDispatch] = frozenset(
    {
        CellDispatch.MISS,
    }
)

# PRESERVATION is NOT mechanical. The absence of a shared key sort between
# observer and constructor does not imply the observation is preserved —
# the constructor may affect all keys through domain logic (e.g., clear_faults
# in thermocouple, cycle with fault latching). The MISS locality axiom has
# a genuine frame-axiom justification (provably different keys via ¬eq_K),
# but PRESERVATION lacks the eq_K guard and is therefore domain reasoning.
# PRESERVATION remains as an informational tier hint for the LLM prompt,
# but axiom_gen does not generate axioms for it.
_MECHANICAL_PRESERVATION: frozenset[CellTier] = frozenset()


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

    Dispatch is checked BEFORE tier — MISS is always a frame/locality axiom
    regardless of tier. Checking tier first would incorrectly route a
    SELECTOR_EXTRACT + MISS cell to _generate_selector_extract, producing
    a duplicate extraction axiom instead of the delegation axiom.

    Three mechanical cases by priority:
      1. MISS dispatch — frame axiom, tier-independent. The McCarthy store
         axiom's negative branch: ¬eq(k,k2) → delegate. Applies to any
         observer (selector, domain, predicate) against any constructor.
      2. SELECTOR_EXTRACT + PLAIN — unguarded extraction: sel(ctor(...)) = xᵢ
      3. SELECTOR_EXTRACT + HIT — guarded extraction: eq_k(k,k2) → sel(ctor(...),k2) = xᵢ
    """
    # MISS dispatch FIRST — locality/frame axiom, tier-independent.
    # A SELECTOR_EXTRACT MISS cell must generate the delegation axiom, not
    # the extraction axiom. Only after ruling out MISS do we check for
    # SELECTOR_EXTRACT (which covers PLAIN and HIT dispatch).
    if cell.dispatch == CellDispatch.MISS:
        return _generate_miss  # type: ignore[return-value]

    # SELECTOR_EXTRACT: PLAIN (unguarded) or HIT (guarded) dispatch.
    # MISS cells for SELECTOR_EXTRACT observers are handled above.
    if cell.tier == CellTier.SELECTOR_EXTRACT:
        return _generate_selector_extract  # type: ignore[return-value]

    return None  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Python renderer (inverse of the DSL)
# ---------------------------------------------------------------------------


def collect_variables(axiom: Axiom) -> list[tuple[str, str]]:
    """Collect all unique (name, sort) variable pairs from an axiom's formula.

    Returns them in a stable order: forall-binding order first, then any
    additional variables found elsewhere in the body (alphabetical fallback).
    """
    # Walk the formula to collect all Var nodes
    seen: set[tuple[str, str]] = set()
    ordered: list[tuple[str, str]] = []

    def _walk_term(t: Term) -> None:
        if isinstance(t, Var):
            key = (t.name, str(t.sort))
            if key not in seen:
                seen.add(key)
                ordered.append(key)
        elif isinstance(t, FnApp):
            for arg in t.args:
                _walk_term(arg)
        elif isinstance(t, FieldAccess):
            _walk_term(t.term)

    def _walk_formula(f: Formula) -> None:
        if isinstance(f, Equation):
            _walk_term(f.lhs)
            _walk_term(f.rhs)
        elif isinstance(f, PredApp):
            for a in f.args:
                _walk_term(a)
        elif isinstance(f, Negation):
            _walk_formula(f.formula)
        elif isinstance(f, Conjunction):
            for c in f.conjuncts:
                _walk_formula(c)
        elif isinstance(f, Disjunction):
            for d in f.disjuncts:
                _walk_formula(d)
        elif isinstance(f, Implication):
            _walk_formula(f.antecedent)
            _walk_formula(f.consequent)
        elif isinstance(f, Biconditional):
            _walk_formula(f.lhs)
            _walk_formula(f.rhs)
        elif isinstance(f, UniversalQuant):
            # Binding order first
            for v in f.variables:
                key = (v.name, str(v.sort))
                if key not in seen:
                    seen.add(key)
                    ordered.append(key)
            _walk_formula(f.body)
        elif isinstance(f, ExistentialQuant):
            for v in f.variables:
                key = (v.name, str(v.sort))
                if key not in seen:
                    seen.add(key)
                    ordered.append(key)
            _walk_formula(f.body)
        elif isinstance(f, Definedness):
            _walk_term(f.term)

    _walk_formula(axiom.formula)
    return ordered


def render_axiom_to_python(
    axiom: Axiom,
    *,
    declarations: bool = True,
    abbreviations: dict[str, str] | None = None,
) -> str:
    """Render an Axiom as a Python DSL source code string.

    If declarations=True (default), includes variable declarations
    as `name = var("name", "Sort")` lines before the Axiom line:

        s = var("s", "Stack")
        e = var("e", "Elem")
        Axiom("pop_push_extract", forall([s, e], eq(app("pop", app("push", s, e)), s)))

    If declarations=False, emits only the Axiom(...) expression using short
    variable names. Caller is responsible for ensuring the variable declarations
    are in scope.

    If abbreviations is provided, it maps expression strings (e.g. 'app("push", s, e)')
    to abbreviation names (e.g. '_stack_push'). These will be used in the output.

    Uses the helper functions (forall, eq, app, var, const, pred_app, implication,
    negation, iff, definedness, field_access, exists, conjunction, etc.)
    — the same vocabulary the LLM uses to construct axioms.
    """
    vars_in_order = collect_variables(axiom)
    short_names: set[str] = {name for name, _sort in vars_in_order}

    body = _render_formula(axiom.formula, short_names, abbreviations)
    axiom_line = f'Axiom("{axiom.label}", {body})'

    if not declarations:
        return axiom_line

    decl_lines = [f'{name} = var("{name}", "{sort}")' for name, sort in vars_in_order]
    if decl_lines:
        return "\n".join(decl_lines) + "\n" + axiom_line
    return axiom_line


def _render_term(
    term: Term,
    short_names: set[str] | None = None,
    abbreviations: dict[str, str] | None = None,
) -> str:
    """Recursive renderer for Terms.

    If short_names is provided, Var nodes whose name is in that set are
    rendered as bare identifiers (e.g. `s`) rather than `var("s", "Sort")`.

    If abbreviations is provided, it maps expression strings to abbreviation names.
    """
    rendered = ""
    if isinstance(term, Var):
        if short_names is not None and term.name in short_names:
            rendered = term.name
        else:
            rendered = f'var("{term.name}", "{term.sort}")'
    elif isinstance(term, FnApp):
        if not term.args:
            rendered = f'const("{term.fn_name}")'
        else:
            args_code = ", ".join(
                _render_term(arg, short_names, abbreviations) for arg in term.args
            )
            rendered = f'app("{term.fn_name}", {args_code})'
    elif isinstance(term, FieldAccess):
        rendered = f'field_access({_render_term(term.term, short_names, abbreviations)}, "{term.field_name}")'
    elif isinstance(term, Literal):
        rendered = f'Literal("{term.value}", SortRef("{term.sort}"))'
    else:
        raise ValueError(f"Unknown Term type: {type(term)}")

    if abbreviations and rendered in abbreviations:
        return abbreviations[rendered]
    return rendered


def _render_formula(
    formula: Formula,
    short_names: set[str] | None = None,
    abbreviations: dict[str, str] | None = None,
) -> str:
    """Recursive renderer for Formulas."""

    def rt(t: Term) -> str:
        return _render_term(t, short_names, abbreviations)

    def rf(f: Formula) -> str:
        return _render_formula(f, short_names, abbreviations)

    if isinstance(formula, Equation):
        return f"eq({rt(formula.lhs)}, {rt(formula.rhs)})"
    elif isinstance(formula, PredApp):
        args_code = ", ".join(rt(a) for a in formula.args)
        return f'pred_app("{formula.pred_name}", {args_code})'
    elif isinstance(formula, Negation):
        return f"negation({rf(formula.formula)})"
    elif isinstance(formula, Conjunction):
        args_code = ", ".join(rf(f) for f in formula.conjuncts)
        return f"conjunction({args_code})"
    elif isinstance(formula, Disjunction):
        args_code = ", ".join(rf(f) for f in formula.disjuncts)
        return f"disjunction({args_code})"
    elif isinstance(formula, Implication):
        return f"implication({rf(formula.antecedent)}, {rf(formula.consequent)})"
    elif isinstance(formula, Biconditional):
        return f"iff({rf(formula.lhs)}, {rf(formula.rhs)})"
    elif isinstance(formula, UniversalQuant):
        if short_names is not None:
            vars_code = ", ".join(
                v.name if v.name in short_names else f'var("{v.name}", "{v.sort}")'
                for v in formula.variables
            )
        else:
            vars_code = ", ".join(
                f'var("{v.name}", "{v.sort}")' for v in formula.variables
            )
        return f"forall([{vars_code}], {rf(formula.body)})"
    elif isinstance(formula, ExistentialQuant):
        if short_names is not None:
            vars_code = ", ".join(
                v.name if v.name in short_names else f'var("{v.name}", "{v.sort}")'
                for v in formula.variables
            )
        else:
            vars_code = ", ".join(
                f'var("{v.name}", "{v.sort}")' for v in formula.variables
            )
        return f"exists([{vars_code}], {rf(formula.body)})"
    elif isinstance(formula, Definedness):
        return f"definedness({rt(formula.term)})"
    else:
        raise ValueError(f"Unknown Formula type: {type(formula)}")
