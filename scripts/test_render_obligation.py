"""Print rendered obligation tables for selected golden specs."""

import pathlib
import sys
import importlib.util

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from alspec.obligation import build_obligation_table
from alspec.obligation_render import render_obligation_table
from alspec.signature import Signature


GOLDEN_GENERATED_SORTS = {
    "stack": frozenset({"Stack"}),
    "bug-tracker": frozenset({"Store"}),
    "bank-account": frozenset({"Account"}),
    "todo-list": frozenset({"TodoList"}),
    "traffic-light": frozenset({"Light", "Color"}),
}


def _load_golden(filename: str):
    golden_dir = pathlib.Path("golden")
    path = golden_dir / filename
    spec = importlib.util.spec_from_file_location(path.stem, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    for domain_id, gen_sorts in sorted(GOLDEN_GENERATED_SORTS.items()):
        mod = _load_golden(f"{domain_id}.py")
        fn_name = domain_id.replace("-", "_") + "_spec"
        spec = getattr(mod, fn_name)()
        sig = spec.signature

        patched_sig = Signature(
            sorts=sig.sorts,
            functions=sig.functions,
            predicates=sig.predicates,
            generated_sorts=gen_sorts,
        )

        table = build_obligation_table(patched_sig)
        rendered = render_obligation_table(patched_sig, table)

        print(f"\n{'='*70}")
        print(f"  {domain_id}")
        print(f"{'='*70}")
        print(rendered)


if __name__ == "__main__":
    main()
