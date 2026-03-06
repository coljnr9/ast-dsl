"""Render an ObligationTable as markdown for inclusion in LLM prompts.

The rendered table tells the LLM exactly which (observer, constructor) pairs
need axioms, whether key dispatch applies, what kind of fill is expected,
and the CellTier annotation that indicates how deterministic the fill is.
"""

from __future__ import annotations

from .obligation import (
    CellDispatch,
    CellTier,
    FnKind,
    ObligationCell,
    ObligationTable,
    PredKind,
)
from .signature import Signature, Totality


def render_obligation_table(sig: Signature, table: ObligationTable) -> str:
    """Render the obligation table as a markdown string.

    Produces one section per generated sort, with:
      - Role summary (constructors, observers, selectors, constants, uninterpreted)
      - The obligation grid as a markdown table with Cell Type and Hint columns
      - Notes on equality basis axioms needed
      - Notes on partial constructor definedness axioms needed
    """
    parts: list[str] = []

    # Group cells by generated sort
    sort_cells: dict[str, list[ObligationCell]] = {}
    for cell in table.cells:
        sort_cells.setdefault(cell.generated_sort, []).append(cell)

    for gen_sort in sorted(sig.generated_sorts.keys()):
        cells = sort_cells.get(gen_sort, [])
        info = sig.generated_sorts[gen_sort]
        ctor_names = list(info.constructors)

        # Gather role info
        fn_observers = sorted(
            n for n, r in table.fn_roles.items()
            if r.kind == FnKind.OBSERVER and r.sort == gen_sort
        )
        fn_selectors = sorted(
            n for n, r in table.fn_roles.items()
            if r.kind == FnKind.SELECTOR and r.sort == gen_sort
        )
        pred_observers = sorted(
            n for n, r in table.pred_roles.items()
            if r.kind == PredKind.OBSERVER and r.sort == gen_sort
        )
        constants = sorted(
            n for n, r in table.fn_roles.items()
            if r.kind == FnKind.CONSTANT
        )
        uninterpreted = sorted(
            n for n, r in table.fn_roles.items()
            if r.kind == FnKind.UNINTERPRETED
        )
        equality_preds = sorted(
            n for n, r in table.pred_roles.items()
            if r.kind == PredKind.EQUALITY
        )

        # Partial functions
        partial_fns = {
            name for name, f in sig.functions.items()
            if f.totality == Totality.PARTIAL
        }
        partial_constructors = [c for c in ctor_names if c in partial_fns]

        # Header
        parts.append(f"### Obligation Table: `{gen_sort}`\n")

        # Role summary
        parts.append("**Roles:**\n")
        parts.append(f"- Constructors: {_fn_list(ctor_names, partial_fns, sig)}")
        if fn_observers:
            parts.append(f"- Function observers: {_fn_list(fn_observers, partial_fns, sig)}")
        if fn_selectors:
            parts.append(f"- Selectors (component extractors): {_fn_list(fn_selectors, partial_fns, sig)}")
        if pred_observers:
            parts.append(f"- Predicate observers: {', '.join(f'`{p}`' for p in pred_observers)}")
        if constants:
            parts.append(f"- Constants: {', '.join(f'`{c}`' for c in constants)}")
        if uninterpreted:
            parts.append(f"- Uninterpreted: {', '.join(f'`{u}`' for u in uninterpreted)}")
        if equality_preds:
            parts.append(f"- Equality predicates: {', '.join(f'`{e}`' for e in equality_preds)}")
        parts.append("")

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
            parts.append(f"**Key dispatch:** {ep} over {ks}\n")

        # The obligation grid with Cell Type and Hint columns
        parts.append("| # | Observer | Constructor | Dispatch | Cell Type | Hint |")
        parts.append("|---|----------|------------|----------|-----------|------|")

        for i, cell in enumerate(cells, 1):
            obs_name = cell.observer_name
            obs_type = "pred" if cell.observer_is_predicate else "fn"
            is_partial = obs_name in partial_fns and not cell.observer_is_predicate

            # Observer label
            partial_marker = " _(partial)_" if is_partial else ""
            obs_label = f"`{obs_name}` ({obs_type}){partial_marker}"

            # Constructor label
            ctor_label = f"`{cell.constructor_name}`"
            ctor_is_partial = cell.constructor_name in partial_fns
            if ctor_is_partial:
                ctor_label += " _(partial)_"

            # Dispatch
            match cell.dispatch:
                case CellDispatch.PLAIN:
                    dispatch_str = "—"
                case CellDispatch.HIT:
                    dispatch_str = f"hit (`{cell.eq_pred}`)"
                case CellDispatch.MISS:
                    dispatch_str = f"miss (`¬{cell.eq_pred}`)"

            # Cell type label
            match cell.tier:
                case CellTier.SELECTOR_EXTRACT:
                    tier_str = "`SELECTOR_EXTRACT`"
                case CellTier.SELECTOR_FOREIGN:
                    tier_str = "`SELECTOR_FOREIGN`"
                case CellTier.KEY_DISPATCH:
                    tier_str = "`KEY_DISPATCH`"
                case CellTier.PRESERVATION:
                    tier_str = "`PRESERVATION`"
                case CellTier.BASE_CASE:
                    tier_str = "`BASE_CASE`"
                case CellTier.DOMAIN:
                    tier_str = "`DOMAIN`"

            # Hint
            hint = _cell_hint(cell, sig, partial_fns, ctor_names)

            parts.append(f"| {i} | {obs_label} | {ctor_label} | {dispatch_str} | {tier_str} | {hint} |")

        parts.append("")

        # Extra axioms needed outside the table
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
            parts.append("**Additional axioms (outside the table):**\n")
            parts.extend(extras)
            parts.append("")

        # Cell count summary
        n_extra = len(equality_preds) * 3 + len(partial_constructors)
        parts.append(
            f"**Expected axiom count:** {len(cells)} obligation cells"
            + (f" + {n_extra} additional = {len(cells) + n_extra} minimum" if n_extra else "")
            + "\n"
        )
        parts.append(
            "Note: Some hit+miss pairs may collapse into a single universal preservation "
            "axiom if the constructor does not affect the observer for any key. The actual "
            "axiom count may be lower than the cell count.\n"
        )

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


def _cell_hint(
    cell: ObligationCell,
    sig: Signature,
    partial_fns: set[str],
    constructors: list[str],
) -> str:
    """Generate a hint for a single cell based on its CellTier and context."""
    obs_is_partial = cell.observer_name in partial_fns and not cell.observer_is_predicate

    match cell.tier:
        case CellTier.SELECTOR_EXTRACT:
            return "mechanical: `sel(ctor(x1,...,xn)) = xi`"

        case CellTier.SELECTOR_FOREIGN:
            return "write `¬def(...)` or preservation"

        case CellTier.KEY_DISPATCH:
            _, obs_app, guard, delegation = _structural_hint_parts(cell, sig)
            if cell.dispatch == CellDispatch.HIT:
                if cell.observer_is_predicate:
                    return f"write: `{guard} → {obs_app}` — define predicate for matching key"
                else:
                    return f"write: `{guard} → {obs_app} = <value>`"
            else:  # MISS
                if cell.observer_is_predicate:
                    return f"write: `¬{guard} → {obs_app} ↔ {delegation}`"
                else:
                    return f"write: `¬{guard} → {obs_app} = {delegation}`"

        case CellTier.PRESERVATION:
            _, obs_app, _, delegation = _structural_hint_parts(cell, sig)
            if cell.observer_is_predicate:
                return f"write: `{obs_app} ↔ {delegation}`"
            else:
                return f"write: `{obs_app} = {delegation}`"

        case CellTier.BASE_CASE:
            _, obs_app, _, _ = _structural_hint_parts(cell, sig)
            if obs_is_partial:
                return f"write: `¬def({obs_app})`"
            elif cell.observer_is_predicate:
                return f"write: `{obs_app}` — typically false for base"
            else:
                return f"write: `{obs_app} = <default>`"

        case CellTier.DOMAIN:
            _, obs_app, _, _ = _structural_hint_parts(cell, sig)
            if cell.observer_is_predicate:
                return f"write: `{obs_app} ↔ <condition>`"
            else:
                return f"write: `{obs_app} = <value>`"

    return "requires domain reasoning"
