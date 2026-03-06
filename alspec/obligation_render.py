"""Render an ObligationTable as markdown for inclusion in LLM prompts.

The rendered table tells the LLM exactly which (observer, constructor) pairs
need axioms, whether key dispatch applies, what kind of fill is expected,
and the CellTier annotation that indicates how deterministic the fill is.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .obligation import (
    CellDispatch,
    CellTier,
    FnKind,
    ObligationCell,
    ObligationTable,
    PredKind,
)
from .signature import Signature, Totality

if TYPE_CHECKING:
    from .axiom_gen import MechanicalAxiomReport


def render_obligation_prompt(
    sig: Signature,
    table: ObligationTable,
    mechanical_report: MechanicalAxiomReport,
) -> str:
    """Render the obligation prompt for Stage 4 axiom generation.

    Produces two sections:
    1. Completed mechanical axioms as Python DSL code
    2. Remaining obligation cells as a flat task list grouped by observer

    This replaces the old grid-based obligation table. The rationale:
    - Mechanical axioms serve as in-context examples in the LLM's output format
    - KEY_DISPATCH MISS axioms scaffold the corresponding HIT axioms
    - Flat task list matches the CASL literature's specification format
    - Eliminates the grid-to-code translation cognitive overhead
    """
    from .axiom_gen import render_axiom_to_python

    parts: list[str] = []

    # Get covered cell keys (observer_name, constructor_name, dispatch)
    covered_keys = {
        (c.observer_name, c.constructor_name, c.dispatch)
        for c in mechanical_report.cells_covered
    }

    # Group cells by generated sort
    sort_cells: dict[str, list[ObligationCell]] = {}
    for cell in table.cells:
        sort_cells.setdefault(cell.generated_sort, []).append(cell)

    # Partial functions set for profile rendering
    partial_fns = {
        name for name, f in sig.functions.items() if f.totality == Totality.PARTIAL
    }

    for gen_sort in sorted(sig.generated_sorts.keys()):
        cells = sort_cells.get(gen_sort, [])
        info = sig.generated_sorts[gen_sort]
        ctor_names = list(info.constructors)

        # Header for the sort
        parts.append(f"## Sort: {gen_sort}\n")

        # Role summary
        parts.append(f"**Constructors:** {_fn_list(ctor_names, partial_fns, sig)}")

        fn_observers = sorted(
            n
            for n, r in table.fn_roles.items()
            if r.kind == FnKind.OBSERVER and r.sort == gen_sort
        )
        # Filter profiles to ONLY show the ones for this sort
        parts.append(f"**Observers:** {_fn_list(fn_observers, partial_fns, sig)}")

        fn_selectors = sorted(
            n
            for n, r in table.fn_roles.items()
            if r.kind == FnKind.SELECTOR and r.sort == gen_sort
        )
        if fn_selectors:
            parts.append(f"**Selectors:** {_fn_list(fn_selectors, partial_fns, sig)}")
        else:
            parts.append("**Selectors:** (none)")

        pred_observers = sorted(
            n
            for n, r in table.pred_roles.items()
            if r.kind == PredKind.OBSERVER and r.sort == gen_sort
        )
        if pred_observers:
            parts.append(
                f"**Predicates:** {', '.join(f'`{p}`' for p in pred_observers)}"
            )
        else:
            parts.append("**Predicates:** (none)")

        # Key dispatch info
        key_sorts = set()
        eq_preds_used = set()
        for cell in cells:
            if cell.key_sort is not None:
                key_sorts.add(cell.key_sort)
            if cell.eq_pred is not None:
                eq_preds_used.add(cell.eq_pred)
        if key_sorts:
            ks = ", ".join(f"`{k}`" for k in sorted(key_sorts))
            ep = ", ".join(f"`{e}`" for e in sorted(eq_preds_used))
            parts.append(f"**Key dispatch:** {ep} over {ks}")

        parts.append("")

        # Section 1: Mechanical axioms
        parts.append("### Mechanical axioms (already generated — do not repeat these)\n")
        parts.append("These axioms are included in the final specification automatically.")
        parts.append("They are shown here as context for writing the remaining axioms.\n")

        # Filter mechanical axioms for this sort
        sort_covered_axioms = []
        for ax, cell in zip(mechanical_report.axioms, mechanical_report.cells_covered):
            if cell.generated_sort == gen_sort:
                sort_covered_axioms.append(ax)

        if sort_covered_axioms:
            from .axiom_gen import collect_variables
            # Collect all variables across ALL axioms for this sort,
            # preserving the order they first appear.
            seen_vars: set[tuple[str, str]] = set()
            all_vars: list[tuple[str, str]] = []
            for ax in sort_covered_axioms:
                for pair in collect_variables(ax):
                    if pair not in seen_vars:
                        seen_vars.add(pair)
                        all_vars.append(pair)

            code_lines: list[str] = []
            short_names = {name for name, _sort in all_vars}
            # Shared variable declarations at the top
            for name, sort in all_vars:
                code_lines.append(f'{name} = var("{name}", "{sort}")')
            if all_vars:
                code_lines.append("")
            # Axiom lines using short names
            for ax in sort_covered_axioms:
                code_lines.append(render_axiom_to_python(ax, declarations=False))

            parts.append("```python")
            parts.extend(code_lines)
            parts.append("```")
        else:
            parts.append("(none)")

        parts.append("")

        # Section 2: Remaining obligations
        parts.append("### Remaining axiom obligations (you must write these)\n")

        # Group remaining cells by observer
        remaining_cells = [
            c
            for c in cells
            if (c.observer_name, c.constructor_name, c.dispatch) not in covered_keys
        ]

        if not remaining_cells:
            parts.append("All obligations for this sort are handled mechanically.\n")
            continue

        obs_remaining: dict[str, list[ObligationCell]] = {}
        for c in remaining_cells:
            obs_remaining.setdefault(c.observer_name, []).append(c)

        for obs_name in sorted(obs_remaining.keys()):
            # Observer heading with profile
            if obs_name in table.pred_roles:
                p = sig.predicates[obs_name]
                profile_args = " × ".join(p.sort for p in p.params)
                heading = f"#### {obs_name} (predicate: {profile_args})"
            else:
                f = sig.functions[obs_name]
                profile_args = " × ".join(p.sort for p in f.params)
                arrow = "→?" if obs_name in partial_fns else "→"
                profile = f"{profile_args} {arrow} {f.result}"
                heading = f"#### {obs_name} ({'partial ' if obs_name in partial_fns else ''}observer: {profile})"

            parts.append(heading)

            for cell in obs_remaining[obs_name]:
                ctor_app, obs_app, guard, delegation = _structural_hint_parts(cell, sig)
                item = f"- `{obs_app}`"
                if guard and cell.dispatch == CellDispatch.HIT:
                    item += f" when `{guard}`"

                # Tier hint
                match cell.tier:
                    case CellTier.BASE_CASE:
                        hint = "BASE_CASE"
                        if obs_name in partial_fns:
                            hint += ": likely ¬def(...)"
                        elif obs_name in table.pred_roles:
                            hint += ": typically false for base"
                    case CellTier.KEY_DISPATCH:
                        if cell.dispatch == CellDispatch.HIT:
                            if obs_name in table.pred_roles:
                                hint = "HIT: define predicate for matching key"
                            else:
                                hint = "HIT: domain-specific equation needed"
                        else:
                            hint = "MISS"  # Should be mechanical, but if not
                    case CellTier.DOMAIN:
                        hint = "DOMAIN"
                    case CellTier.SELECTOR_FOREIGN:
                        hint = "SELECTOR_FOREIGN: write ¬def(...) or preservation"
                    case CellTier.PRESERVATION:
                        hint = "PRESERVATION"
                        if obs_name in table.pred_roles:
                             hint = "PRESERVATION: typically delegates via iff"
                    case _:
                        hint = cell.tier.value

                parts.append(f"{item} — {hint}")
            parts.append("")

        # Additional axioms (outside the table)
        equality_preds = sorted(
            n
            for n, r in table.pred_roles.items()
            if r.kind == PredKind.EQUALITY and r.sort == gen_sort
        )
        partial_constructors = [c for c in ctor_names if c in partial_fns]

        extras: list[str] = []
        if equality_preds:
            for ep in equality_preds:
                extras.append(
                    f"- **`{ep}` basis:** reflexivity, symmetry, transitivity (3 axioms)"
                )
        if partial_constructors:
            for pc in partial_constructors:
                extras.append(
                    f"- **`{pc}` definedness:** write a `Definedness` biconditional "
                    f"stating when `{pc}` is defined (1 axiom)"
                )

        if extras:
            parts.append("**Additional axioms (outside the table):**")
            parts.extend(extras)
            parts.append("")

    return "\n".join(parts)


def _fn_list(names: list[str], partial_fns: set[str], sig: Signature) -> str:
    """Format a list of function names with partial markers and profiles."""
    items = []
    for name in names:
        f = sig.functions[name]
        params = " × ".join(p.sort for p in f.params)
        arrow = "→?" if name in partial_fns else "→"
        profile = f"{params} {arrow} {f.result}" if params else f"{arrow} {f.result}"
        items.append(f"`{name} : {profile}`")
    return ", ".join(items)


def _structural_hint_parts(
    cell: ObligationCell,
    sig: Signature,
) -> tuple[str, str, str, str]:
    """Build structural components for a hint string.

    Returns (ctor_app, obs_app, guard, delegation) where:
      - ctor_app: "add_stock(w, p, q)" or "init" for nullary
      - obs_app: "get_status(add_stock(w, p, q), p2)" — observer applied to ctor
      - guard: "eq_product(p, p2)" — key equality guard, or "" if no dispatch
      - delegation: "get_status(w, p2)" — observer applied to inner state
    """
    # Get the constructor symbol
    ctor = sig.functions[cell.constructor_name]

    # Get the observer symbol (function or predicate)
    if cell.observer_is_predicate:
        obs = sig.predicates[cell.observer_name]
    else:
        obs = sig.functions[cell.observer_name]

    gen_sort = cell.generated_sort

    # Ctor param names
    ctor_param_names = [p.name for p in ctor.params]
    ctor_param_name_set = set(ctor_param_names)

    # Observer lookup params (skip first param which is the state/generated sort)
    obs_lookup_params = list(obs.params[1:])

    # Rename observer lookup params that collide with ctor param names
    renamed_lookup: list[str] = []
    for p in obs_lookup_params:
        if p.name in ctor_param_name_set:
            renamed_lookup.append(p.name + "2")
        else:
            renamed_lookup.append(p.name)

    # Find the state variable: first ctor param whose sort is the generated sort
    state_var: str | None = None
    for p in ctor.params:
        if p.sort == gen_sort:
            state_var = p.name
            break

    # Build ctor application string
    if ctor_param_names:
        ctor_app = f"{cell.constructor_name}({', '.join(ctor_param_names)})"
    else:
        ctor_app = cell.constructor_name  # nullary: "init" not "init()"

    # Build observer application string: obs(ctor_app, lookup_params...)
    all_obs_args = [ctor_app] + renamed_lookup
    obs_app = f"{cell.observer_name}({', '.join(all_obs_args)})"

    # Build delegation string: obs(state_var, lookup_params...)
    if state_var is not None:
        deleg_args = [state_var] + renamed_lookup
    else:
        # Nullary ctor (no state var) — delegation doesn't apply
        deleg_args = renamed_lookup
    delegation = f"{cell.observer_name}({', '.join(deleg_args)})"

    # Build guard string from key dispatch info
    guard = ""
    if cell.eq_pred and cell.key_sort:
        # Find the ctor param with the key sort (skip state param)
        ctor_key: str | None = None
        for p in ctor.params:
            if p.sort == cell.key_sort and p.sort != gen_sort:
                ctor_key = p.name
                break
        # Find the observer lookup param with the key sort (use renamed name)
        obs_key: str | None = None
        for orig, renamed in zip(obs_lookup_params, renamed_lookup):
            if orig.sort == cell.key_sort:
                obs_key = renamed
                break
        if ctor_key is not None and obs_key is not None:
            guard = f"{cell.eq_pred}({ctor_key}, {obs_key})"

    return ctor_app, obs_app, guard, delegation


