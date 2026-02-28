"""Validate obligation table generation against golden specs.

Uses CASL-style explicit constructor declarations per generated sort.
"""

import pathlib
import sys
import importlib.util

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from alspec.obligation import build_obligation_table, classify_functions, classify_predicates, FnKind, PredKind
from alspec.obligation_render import render_obligation_table
from alspec.signature import Signature


# CASL-style: each generated sort maps to its constructor list
GOLDEN_GENERATED_SORTS: dict[str, dict[str, tuple[str, ...]]] = {
    "access-control": {"System": ("init", "set_role", "grant", "revoke")},
    "auction": {"Auction": ("new", "register", "submit", "close")},
    "bank-account": {"Account": ("empty", "deposit", "withdraw")},
    "boolean-flag": {"Flag": ("init", "enable", "disable")},
    "bounded-counter": {"Counter": ("new", "inc")},
    "bug-tracker": {"Store": ("empty", "create_ticket", "resolve_ticket", "assign_ticket")},
    "counter": {"Counter": ("new", "inc", "dec", "reset")},
    "door-lock": {"Lock": ("new", "lock", "unlock", "open_door", "close_door")},
    "email-inbox": {"Inbox": ("empty", "receive", "mark_read", "mark_unread", "delete", "star")},
    "inventory": {"Inventory": ("empty", "add_stock", "remove_stock")},
    "library-lending": {"Library": ("empty", "register", "borrow", "return_book")},
    "phone-book": {"PhoneBook": ("empty", "add", "remove")},
    "queue": {"Queue": ("empty", "enqueue")},
    "shopping-cart": {"Cart": ("empty", "add_item", "apply_discount", "remove_item")},
    "stack": {"Stack": ("new", "push")},
    "temperature-sensor": {"Sensor": ("init", "record")},
    "thermostat": {"Thermostat": ("new", "set_target", "read_temp")},
    "todo-list": {"TodoList": ("empty", "add_item", "complete_item", "remove_item")},
    "traffic-light": {
        "Color": ("red", "yellow", "green"),
        "Light": ("init", "cycle"),
    },
    "version-history": {"Repo": ("init", "commit", "revert")},
}


def _load_golden(filename: str):
    golden_dir = pathlib.Path("golden")
    path = golden_dir / filename
    spec = importlib.util.spec_from_file_location(path.stem, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "summary"
    # --render <domain> to show full rendered table
    # --all to show all rendered tables
    # default: summary view

    golden_dir = pathlib.Path("golden")
    for f in sorted(golden_dir.glob("*.py")):
        domain_id = f.stem
        gen_sorts = GOLDEN_GENERATED_SORTS.get(domain_id)
        if gen_sorts is None:
            print(f"  SKIP {domain_id} (no generated_sorts annotation)")
            continue

        mod = _load_golden(f.name)
        fn_name = domain_id.replace("-", "_") + "_spec"
        spec = getattr(mod, fn_name)()
        sig = spec.signature

        patched_sig = Signature(
            sorts=sig.sorts,
            functions=sig.functions,
            predicates=sig.predicates,
            generated_sorts=gen_sorts,
        )

        fn_roles = classify_functions(patched_sig)
        pred_roles = classify_predicates(patched_sig)
        table = build_obligation_table(patched_sig)

        ctors = sorted(n for n, r in fn_roles.items() if r.kind == FnKind.CONSTRUCTOR)
        fn_obs = sorted(n for n, r in fn_roles.items() if r.kind == FnKind.OBSERVER)
        pred_obs = sorted(n for n, r in pred_roles.items() if r.kind == PredKind.OBSERVER)
        constants = sorted(n for n, r in fn_roles.items() if r.kind == FnKind.CONSTANT)
        uninterp = sorted(n for n, r in fn_roles.items() if r.kind == FnKind.UNINTERPRETED)
        eq_preds = sorted(n for n, r in pred_roles.items() if r.kind == PredKind.EQUALITY)
        other_preds = sorted(n for n, r in pred_roles.items() if r.kind == PredKind.OTHER)

        if mode == "--all" or (mode == "--render" and len(sys.argv) > 2 and sys.argv[2] == domain_id):
            rendered = render_obligation_table(patched_sig, table)
            print(f"\n{'='*70}")
            print(f"  {domain_id}")
            print(f"{'='*70}")
            print(rendered)
        else:
            delta = table.cell_count - len(spec.axioms)
            delta_str = f" ({'+' if delta >= 0 else ''}{delta})" if delta != 0 else ""
            print(f"\n{'='*60}")
            print(f"  {domain_id}  (generated: {', '.join(gen_sorts.keys())})")
            print(f"{'='*60}")
            print(f"  Constructors:   {ctors}")
            print(f"  Fn observers:   {fn_obs}")
            print(f"  Pred observers: {pred_obs}")
            print(f"  Constants:      {constants}")
            print(f"  Uninterpreted:  {uninterp}")
            print(f"  Eq predicates:  {eq_preds}")
            if other_preds:
                print(f"  Other preds:    {other_preds}")
            print(f"  Obligation cells: {table.cell_count}")
            print(f"  Actual axioms:    {len(spec.axioms)}{delta_str}")

            for cell in table.cells:
                dispatch_str = f" [{cell.dispatch.value}]" if cell.dispatch.value != "plain" else ""
                obs_type = "pred" if cell.observer_is_predicate else "fn"
                print(f"    {cell.observer_name}({obs_type}) × {cell.constructor_name}{dispatch_str}")


if __name__ == "__main__":
    main()
