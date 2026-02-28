"""Render an ObligationTable as markdown for inclusion in LLM prompts.

The rendered table tells the LLM exactly which (observer, constructor) pairs
need axioms, whether key dispatch applies, and what kind of fill is expected.
"""

from __future__ import annotations

from .obligation import (
    CellDispatch,
    FnKind,
    ObligationCell,
    ObligationTable,
    PredKind,
)
from .signature import Signature, Totality


def render_obligation_table(sig: Signature, table: ObligationTable) -> str:
    """Render the obligation table as a markdown string.

    Produces one section per generated sort, with:
      - Role summary (constructors, observers, constants, uninterpreted)
      - The obligation grid as a markdown table
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
        ctor_names = list(sig.generated_sorts[gen_sort])

        # Gather role info
        fn_observers = sorted(
            n for n, r in table.fn_roles.items()
            if r.kind == FnKind.OBSERVER and r.sort == gen_sort
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

        # The obligation grid
        parts.append("| # | Observer | Constructor | Dispatch | Fill guidance |")
        parts.append("|---|----------|------------|----------|---------------|")

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

            # Fill guidance
            guidance = _cell_guidance(cell, sig, partial_fns, ctor_names)

            parts.append(f"| {i} | {obs_label} | {ctor_label} | {dispatch_str} | {guidance} |")

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


def _cell_guidance(
    cell: ObligationCell,
    sig: Signature,
    partial_fns: set[str],
    constructors: list[str],
) -> str:
    """Generate fill guidance for a single cell."""
    obs_is_partial = cell.observer_name in partial_fns and not cell.observer_is_predicate
    ctor = sig.functions[cell.constructor_name]
    ctor_is_base = ctor.is_constant

    match cell.dispatch:
        case CellDispatch.PLAIN:
            if ctor_is_base and obs_is_partial:
                return "Base ctor + partial obs: omit (safe) or write `¬def(...)`"
            elif ctor_is_base and cell.observer_is_predicate:
                return "Base ctor: typically false/negated"
            elif ctor_is_base:
                return "Base ctor: define initial value"
            else:
                return "Write equation or biconditional"

        case CellDispatch.HIT:
            if obs_is_partial:
                return "Key match: write equation, `¬def(...)`, or guarded equation"
            elif cell.observer_is_predicate:
                return "Key match: write predicate assertion or biconditional"
            else:
                return "Key match: write equation for the new/updated value"

        case CellDispatch.MISS:
            return "Key miss: delegate to inner state (preservation)"
