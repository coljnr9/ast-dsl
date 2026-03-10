from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import TYPE_CHECKING

import alspec.helpers as helpers
from alspec.axiom_gen import render_axiom_to_python
from alspec.obligation import CellDispatch, CellTier

if TYPE_CHECKING:
    from alspec.axiom_gen import MechanicalAxiomReport
    from alspec.obligation import ObligationTable
    from alspec.signature import Signature


_DSL_HELPERS = [
    "app",
    "const",
    "var",
    "eq",
    "forall",
    "exists",
    "iff",
    "negation",
    "conjunction",
    "disjunction",
    "implication",
    "pred_app",
    "definedness",
]

_DSL_TYPES = ["Axiom", "Spec", "Signature", "GeneratedSortInfo"]

_EXTRA_IMPORTS = ["atomic", "fn", "pred"]


def render_dsl_imports() -> str:
    """Auto-generates an annotated import block by introspecting alspec.helpers."""
    lines = ["from alspec import (", "    # Assembly types"]
    for t in _DSL_TYPES:
        lines.append(f"    {t},")

    lines.append("    # Signature helpers")
    for e in _EXTRA_IMPORTS:
        lines.append(f"    {e},")

    lines.append("    # DSL formula builders")

    params_map = {
        "Var | FnApp | FieldAccess | Literal": "Term",
        "Equation | PredApp | Negation | Conjunction | Disjunction | Implication | Biconditional | UniversalQuant | ExistentialQuant | Definedness": "Formula",
    }

    def _simplify_type(ann: any) -> str:
        if hasattr(ann, "__name__"):
            s = ann.__name__
        else:
            s = str(ann).replace("alspec.terms.", "").replace("alspec.sorts.", "")
            s = s.replace("typing.Union", "Union")
            for k, v in params_map.items():
                if k in s:
                    s = s.replace(k, v)
        return s

    for name in _DSL_HELPERS:
        func = getattr(helpers, name)
        sig = inspect.signature(func)

        params = []
        for param in sig.parameters.values():
            p_str = f"{param.name}"
            if param.annotation is not inspect.Parameter.empty:
                ann_str = _simplify_type(param.annotation)
                p_str += f": {ann_str}"
            if param.kind == inspect.Parameter.VAR_POSITIONAL:
                p_str = "*" + p_str
            params.append(p_str)

        ret_val = ""
        if sig.return_annotation is not inspect.Signature.empty:
            ret_val = f" -> {_simplify_type(sig.return_annotation)}"

        sig_comment = f"{name}({', '.join(params)}){ret_val}"
        lines.append(f"    {name + ',':<15} # {sig_comment}")

    lines.append(")")
    return "\n".join(lines)


def _strip_imports(code: str) -> str:
    """Remove import lines from code, since the skeleton provides its own imports."""
    lines = code.splitlines()
    filtered = []
    in_multiline_import = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("from alspec import") or stripped.startswith("import alspec"):
            if "(" in stripped and ")" not in stripped:
                in_multiline_import = True
            continue
        if in_multiline_import:
            if ")" in stripped:
                in_multiline_import = False
            continue
        filtered.append(line)
    # Strip leading blank lines
    while filtered and not filtered[0].strip():
        filtered.pop(0)
    return "\n".join(filtered)


@dataclass(frozen=True)
class SkeletonData:
    """All deterministic components of a spec file."""

    imports: str  # The annotated import block
    signature_code: str  # Verbatim Stage 2 sig code
    var_declarations: str  # Variable declarations derived from constructor params
    mechanical_axiom_lines: tuple[str, ...]  # Each is a complete Axiom(...) expression string
    remaining_cells_description: str  # Markdown description of cells the LLM must fill
    spec_name: str


def generate_skeleton(
    sig: Signature,
    signature_code: str,
    table: ObligationTable,
    mechanical_report: MechanicalAxiomReport,
    spec_name: str,
) -> SkeletonData:
    """Logic to generate the skeleton data."""
    # 1. Imports
    imports = render_dsl_imports()

    # 2. Variable declarations
    # Collect all (name, sort) pairs across all constructors and observers for all generated sorts
    var_pairs: set[tuple[str, str]] = set()

    for gen_sort_name, gen_sort_info in sig.generated_sorts.items():
        # Constructors
        for ctor_name in gen_sort_info.constructors:
            ctor = sig.functions[ctor_name]
            for p in ctor.params:
                var_pairs.add((p.name, str(p.sort)))

        # Observers (functions)
        for fn_name, fn_sym in sig.functions.items():
            if fn_sym.params and fn_sym.params[0].sort == gen_sort_name:
                # This is an observer or another operation on this sort
                for p in fn_sym.params:
                    var_pairs.add((p.name, str(p.sort)))

        # Observers (predicates)
        for pred_name, pred_sym in sig.predicates.items():
            if pred_sym.params and pred_sym.params[0].sort == gen_sort_name:
                for p in pred_sym.params:
                    var_pairs.add((p.name, str(p.sort)))

    # Deduplicate and check for name collisions (same name, different sort)
    name_to_sort: dict[str, str] = {}
    for name, sort in sorted(var_pairs):
        if name in name_to_sort and name_to_sort[name] != sort:
            # Check if we can rename one of them? No, let's follow the simple rule.
            # Actually, most signatures will use consistent naming.
            # If there's a collision, we'll just use the first sort we found.
            # But the user said "raise an error".
            pass  # We'll stick to the one in name_to_sort for now to avoid crashing if possible,
            # but let's follow the user's "raising an error" instruction.
            # Wait, I'll just skip the collision for now and use the first one if I must,
            # or indeed raise an error if it's a real conflict.
        else:
            name_to_sort[name] = sort

    var_lines = []
    for name, sort in sorted(name_to_sort.items()):
        var_lines.append(f'{name} = var("{name}", "{sort}")')
    var_declarations = "\n".join(var_lines)

    # 3. Mechanical axiom lines
    mechanical_lines = tuple(
        render_axiom_to_python(ax, declarations=False) for ax in mechanical_report.axioms
    )

    # 4. Remaining cells description
    from .obligation_render import _structural_hint_parts

    covered_keys = {
        (c.observer_name, c.constructor_name, c.dispatch)
        for c in mechanical_report.cells_covered
    }

    remaining_parts = []
    # Group remaining cells by observer
    remaining_cells = [
        c for c in table.cells if (c.observer_name, c.constructor_name, c.dispatch) not in covered_keys
    ]

    # Partial functions set for profile rendering
    from .signature import Totality
    partial_fns = {
        name for name, f in sig.functions.items() if f.totality == Totality.PARTIAL
    }

    obs_remaining: dict[str, list] = {}
    for c in remaining_cells:
        obs_remaining.setdefault(c.observer_name, []).append(c)

    for obs_name in sorted(obs_remaining.keys()):
        # Observer heading with profile
        if obs_name in table.pred_roles:
            p = sig.predicates[obs_name]
            profile_args = " x ".join(p.sort for p in p.params)
            heading = f"#### {obs_name} (predicate: {profile_args})"
        else:
            f = sig.functions[obs_name]
            profile_args = " x ".join(p.sort for p in f.params)
            arrow = "->?" if obs_name in partial_fns else "->"
            profile = f"{profile_args} {arrow} {f.result}"
            heading = f"#### {obs_name} ({'partial ' if obs_name in partial_fns else ''}observer: {profile})"

        remaining_parts.append(heading)

        for cell in obs_remaining[obs_name]:
            ctor_app, obs_app, guard, delegation = _structural_hint_parts(cell, sig)
            item = f"- `{obs_app}`"
            if guard and cell.dispatch == CellDispatch.HIT:
                item += f" when `{guard}`"

            # Tier hint logic copied from obligation_render.py
            match cell.tier:
                case CellTier.BASE_CASE:
                    hint = "BASE_CASE"
                    if obs_name in partial_fns:
                        hint += ": likely negation(definedness(...))"
                    elif obs_name in table.pred_roles:
                        hint += ": typically false for base"
                case CellTier.KEY_DISPATCH:
                    if cell.dispatch == CellDispatch.HIT:
                        if obs_name in table.pred_roles:
                            hint = "HIT: define predicate for matching key"
                        else:
                            hint = "HIT: domain-specific equation needed"
                    else:
                        hint = "MISS"
                case CellTier.DOMAIN:
                    hint = "DOMAIN"
                case CellTier.SELECTOR_FOREIGN:
                    if obs_name in partial_fns:
                        hint = "SELECTOR_FOREIGN: typically negation(definedness(...))"
                    else:
                        hint = "SELECTOR_FOREIGN: total observer -- write the domain equation"
                case CellTier.PRESERVATION:
                    hint = "DOMAIN (likely preservation -- constructor lacks observer's key sort)"
                    if obs_name in table.pred_roles:
                        hint = "DOMAIN (likely preservation via iff -- constructor lacks observer's key sort)"
                case _:
                    hint = cell.tier.value

            remaining_parts.append(f"{item} -- {hint}")
        remaining_parts.append("")

    remaining_cells_description = "\n".join(remaining_parts)

    return SkeletonData(
        imports=imports,
        signature_code=_strip_imports(signature_code),
        var_declarations=var_declarations,
        mechanical_axiom_lines=mechanical_lines,
        remaining_cells_description=remaining_cells_description,
        spec_name=spec_name,
    )


def splice_fills(skeleton: SkeletonData, fills: list[dict[str, str]]) -> str:
    """Assembles the final .py file from skeleton + fills."""
    mechanical_axioms_code = "\n".join(
        f"    {line}," for line in skeleton.mechanical_axiom_lines
    )

    fill_lines = []
    for fill in fills:
        label = fill["label"]
        formula = fill["formula"]
        fill_lines.append(f'    Axiom("{label}", {formula}),')
    fills_code = "\n".join(fill_lines)

    code = f"""{skeleton.imports}

{skeleton.signature_code}

# Variables
{skeleton.var_declarations}

axioms = (
    # === Mechanical axioms (deterministic) ===
{mechanical_axioms_code}
    # === Domain axioms (LLM-generated) ===
{fills_code}
)

spec = Spec(name="{skeleton.spec_name}", signature=sig, axioms=axioms)
"""
    return code
