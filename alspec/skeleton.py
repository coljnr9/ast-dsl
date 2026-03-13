from __future__ import annotations

import inspect
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

logger = logging.getLogger(__name__)

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
    mechanical_axiom_lines: tuple[str, ...]  # Each is a complete Axiom(...) expression string
    mechanical_variables: tuple[tuple[str, str], ...]  # (name, sort) pairs from mechanical axioms
    constructor_terms: tuple[tuple[str, str, str], ...]  # (sort_name, abbrev_name, expression)
    remaining_cells_description: str  # Markdown description of cells the LLM must fill
    spec_name: str
    # Optional enrichment sections (toggleable for DoE)
    observer_reference: str = ""  # Component B — observer DSL patterns table


def generate_skeleton(
    sig: Signature,
    signature_code: str,
    table: ObligationTable,
    mechanical_report: MechanicalAxiomReport,
    spec_name: str,
    *,
    dsl_cell_hints: bool = True,
    observer_reference: bool = True,
) -> SkeletonData:
    """Logic to generate the skeleton data."""
    # 1. Imports
    imports = render_dsl_imports()

    # 2. (Removed) Variable declarations are now provided by the LLM in the tool call.

    # 3. Constructor term abbreviations
    constructor_terms: list[tuple[str, str, str]] = []
    reverse_abbreviations: dict[str, str] = {}
    ctor_name_to_abbrev: dict[str, str] = {}  # e.g. "register" -> "_library_register"
    for sort_name, info in sig.generated_sorts.items():
        for ctor_name in info.constructors:
            ctor = sig.functions[ctor_name]
            abbrev = f"_{sort_name.lower()}_{ctor_name}"
            if not ctor.params:
                expr = f'const("{ctor_name}")'
            else:
                params_str = ", ".join(p.name for p in ctor.params)
                expr = f'app("{ctor_name}", {params_str})'
            constructor_terms.append((sort_name, abbrev, expr))
            reverse_abbreviations[expr] = abbrev
            ctor_name_to_abbrev[ctor_name] = abbrev

    logger.info(
        "Generated %d constructor term abbreviations for %d sorts",
        len(constructor_terms),
        len(sig.generated_sorts),
    )

    # 4. Mechanical axiom lines
    from .axiom_gen import collect_variables

    mechanical_lines = tuple(
        render_axiom_to_python(ax, declarations=False, abbreviations=reverse_abbreviations)
        for ax in mechanical_report.axioms
    )

    mech_vars: list[tuple[str, str]] = []
    for axiom in mechanical_report.axioms:
        mech_vars.extend(collect_variables(axiom))

    # Deduplicate preserving order
    seen_vars: set[str] = set()
    unique_mech_vars: list[tuple[str, str]] = []
    for name, sort in mech_vars:
        if name not in seen_vars:
            seen_vars.add(name)
            unique_mech_vars.append((name, sort))

    # 5. Remaining cells description
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

            if dsl_cell_hints:
                # Build the renamed lookup parameter list (same logic as _structural_hint_parts)
                is_pred = cell.observer_is_predicate
                dsl_fn = "pred_app" if is_pred else "app"
                if is_pred:
                    obs_sym = sig.predicates[obs_name]
                else:
                    obs_sym = sig.functions[obs_name]
                ctor_sym = sig.functions[cell.constructor_name]
                ctor_param_name_set = {p.name for p in ctor_sym.params}
                obs_lookup_params = list(obs_sym.params[1:])
                renamed_lookup: list[str] = [
                    p.name + "2" if p.name in ctor_param_name_set else p.name
                    for p in obs_lookup_params
                ]

                # Find state variable: first ctor param whose sort equals generated sort
                gen_sort = cell.generated_sort
                state_var: str | None = None
                for p in ctor_sym.params:
                    if p.sort == gen_sort:
                        state_var = p.name
                        break

                ctor_abbrev = ctor_name_to_abbrev.get(cell.constructor_name, cell.constructor_name)

                dsl_obs_args = [ctor_abbrev] + renamed_lookup
                dsl_obs_call = f'{dsl_fn}("{obs_name}", {', '.join(dsl_obs_args)})'

                if state_var is not None:
                    deleg_args = [state_var] + renamed_lookup
                    deleg_call = f'{dsl_fn}("{obs_name}", {', '.join(deleg_args)})'
                    remaining_parts.append(
                        f"  DSL: `{dsl_obs_call}` | delegation: `{deleg_call}`"
                    )
                else:
                    remaining_parts.append(f"  DSL: `{dsl_obs_call}`")

        remaining_parts.append("")

    remaining_cells_description = "\n".join(remaining_parts)

    # 6. Observer quick reference table (Component B)
    observer_reference_str = ""
    if observer_reference and obs_remaining:
        ref_lines = [
            "### Observer DSL Patterns",
            "",
            "Use these patterns when constructing observer applications in your formulas.",
            "",
            "| Observer | Arity | DSL Pattern |",
            "|----------|-------|-------------|",
        ]
        for obs_name in sorted(obs_remaining.keys()):
            is_pred = obs_name in table.pred_roles
            dsl_fn = "pred_app" if is_pred else "app"
            if is_pred:
                obs_sym = sig.predicates[obs_name]
            else:
                obs_sym = sig.functions[obs_name]
            arity = len(obs_sym.params)
            placeholders = [f"<{p.sort}_term>" for p in obs_sym.params]
            pattern = f'{dsl_fn}("{obs_name}", {', '.join(placeholders)})'
            ref_lines.append(f"| `{obs_name}` | {arity} | `{pattern}` |")
        observer_reference_str = "\n".join(ref_lines)

    return SkeletonData(
        imports=imports,
        signature_code=_strip_imports(signature_code),
        mechanical_axiom_lines=mechanical_lines,
        mechanical_variables=tuple(unique_mech_vars),
        constructor_terms=tuple(constructor_terms),
        remaining_cells_description=remaining_cells_description,
        spec_name=spec_name,
        observer_reference=observer_reference_str,
    )


def render_variable_declarations(variables: list[dict[str, str]]) -> str:
    """Render LLM-provided variable declarations as Python var() calls.

    Deduplicates by name (first occurrence wins) and sorts alphabetically.
    """
    seen: dict[str, str] = {}
    for v in variables:
        name = v["name"]
        sort = v["sort"]
        if name not in seen:
            seen[name] = sort
    lines = []
    for name, sort in sorted(seen.items()):
        lines.append(f'{name} = var("{name}", "{sort}")')
    return "\n".join(lines)


def splice_fills(
    skeleton: SkeletonData,
    variables: list[dict[str, str]],
    fills: list[dict[str, str]],
) -> str:
    """Assembles the final .py file from skeleton + fills."""
    # Merge mechanical axiom variables with LLM-provided variables
    # LLM variables take precedence (they come first in the list for dedup)
    merged_variables = list(variables)
    for name, sort in skeleton.mechanical_variables:
        merged_variables.append({"name": name, "sort": sort})

    var_declarations = render_variable_declarations(merged_variables)
    constructor_term_lines = "\n".join(
        f"{abbrev} = {expr}" for _, abbrev, expr in skeleton.constructor_terms
    )
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
{var_declarations}

# Constructor terms
{constructor_term_lines}

axioms = (
    # === Mechanical axioms (deterministic) ===
{mechanical_axioms_code}
    # === Domain axioms (LLM-generated) ===
{fills_code}
)

spec = Spec(name="{skeleton.spec_name}", signature=sig, axioms=axioms)
"""
    return code
