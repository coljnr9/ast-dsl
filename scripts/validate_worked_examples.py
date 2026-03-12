#!/usr/bin/env python3
"""Validate worked examples are structurally correct.

Run from project root after fix_worked_examples.py:
    uv run python scripts/validate_worked_examples.py

This enforces the "fail loud, no silent defaults" principle.
Every field must be the correct type — no strings where enums belong,
no None where empty strings belong, no bare code outside functions.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


def main() -> int:
    # Import from the actual package
    try:
        from alspec.worked_example import (
            WorkedExample, FunctionRole, CellType, Pattern,
            RenderMode, SortInfo, FunctionInfo, ObligationCell,
            DesignDecision,
        )
        from alspec.reference.worked_examples import ALL_EXAMPLES
    except Exception as e:
        print(f"IMPORT ERROR: {e}")
        print("  Make sure you're running from the project root with uv")
        return 1

    errors: list[str] = []
    warnings: list[str] = []

    print(f"Validating {len(ALL_EXAMPLES)} examples...\n")

    for domain_id, ex in ALL_EXAMPLES.items():
        prefix = f"[{domain_id}]"

        # ----------------------------------------------------------
        # Type checks — these MUST be enum instances, not strings
        # ----------------------------------------------------------
        for i, fi in enumerate(ex.functions):
            if not isinstance(fi.role, FunctionRole):
                errors.append(f"{prefix} functions[{i}].role is {type(fi.role).__name__}('{fi.role}'), expected FunctionRole enum")

        for i, oc in enumerate(ex.obligations):
            if not isinstance(oc.cell_type, CellType):
                errors.append(f"{prefix} obligations[{i}].cell_type is {type(oc.cell_type).__name__}('{oc.cell_type}'), expected CellType enum")
            if oc.guard is None:
                errors.append(f"{prefix} obligations[{i}].guard is None, expected str (use '' for no guard)")
            if oc.constructor is None:
                errors.append(f"{prefix} obligations[{i}].constructor is None, expected str (use '—' for no constructor)")

        for p in ex.patterns:
            if not isinstance(p, Pattern):
                errors.append(f"{prefix} pattern {p} is not a Pattern enum instance")

        # ----------------------------------------------------------
        # Code structure checks
        # ----------------------------------------------------------
        code = ex.code.strip()

        # Must have a function definition
        func_match = re.search(r'def (\w+_spec)\s*\(\)\s*->\s*Spec:', code)
        if not func_match:
            errors.append(f"{prefix} Code does not contain 'def xxx_spec() -> Spec:'")
        else:
            fn_name = func_match.group(1)
            # Must have return Spec( inside the function
            after_def = code[func_match.end():]
            if 'return Spec(' not in after_def:
                errors.append(f"{prefix} Function {fn_name} does not contain 'return Spec('")

        # Must NOT have spec = Spec( at module level
        # (before any def statement)
        before_def = code[:code.find('def ')] if 'def ' in code else code
        if re.search(r'^\s*spec\s*=\s*Spec\(', before_def, re.MULTILINE):
            errors.append(f"{prefix} Has 'spec = Spec(...)' at module level (should be inside function)")

        # Must NOT have return at module level
        if re.search(r'^return\s', before_def, re.MULTILINE):
            errors.append(f"{prefix} Has 'return' at module level (should be inside function)")

        # Imports must be at module level (before def)
        if 'def ' in code:
            func_body = code[code.find('def '):]
            if re.search(r'^\s+from alspec import', func_body, re.MULTILINE):
                errors.append(f"{prefix} Has 'from alspec import' inside function body (must be at module level)")

        # Must use GeneratedSortInfo, not raw tuples
        # Look for generated_sorts={"SortName": ("ctor1", "ctor2")} without GeneratedSortInfo
        if re.search(r'generated_sorts\s*=\s*\{\s*"\w+"\s*:\s*\(', code):
            if 'GeneratedSortInfo' not in code:
                warnings.append(f"{prefix} Possible raw tuple in generated_sorts (no GeneratedSortInfo found)")

        # ----------------------------------------------------------
        # Axiom count vs obligation count
        # ----------------------------------------------------------
        axiom_count = len(re.findall(r'Axiom\s*\(', code))
        obligation_count = len(ex.obligations)

        # These won't always match exactly (eq_id basis axioms may not
        # have 1:1 obligation rows), but large mismatches are suspicious
        if axiom_count == 0:
            errors.append(f"{prefix} Zero Axiom() calls found in code!")
        elif abs(axiom_count - obligation_count) > axiom_count * 0.5:
            warnings.append(
                f"{prefix} Axiom count ({axiom_count}) vs obligation count ({obligation_count}) "
                f"differ by >50% — may indicate missing axioms or obligations"
            )

        # ----------------------------------------------------------
        # Render smoke test — must not crash
        # ----------------------------------------------------------
        try:
            for mode in RenderMode:
                rendered = ex.render(mode)
                if len(rendered) < 50:
                    errors.append(f"{prefix} render({mode.name}) produced suspiciously short output ({len(rendered)} chars)")

            # Also test include_table=False
            rendered_no_table = ex.render(RenderMode.FULL, include_table=False)
            rendered_with_table = ex.render(RenderMode.FULL, include_table=True)
            if len(rendered_no_table) >= len(rendered_with_table):
                warnings.append(f"{prefix} include_table=False didn't reduce output size")
        except Exception as e:
            errors.append(f"{prefix} render() crashed: {e}")

        # ----------------------------------------------------------
        # Domain name should be human-readable
        # ----------------------------------------------------------
        if re.match(r'^[A-Z][a-z]+[A-Z]', ex.domain_name):
            warnings.append(f"{prefix} domain_name '{ex.domain_name}' looks like CamelCase (should be 'Spaced Words')")

    # ================================================================
    # Cross-example checks
    # ================================================================

    # All 20 must be present
    expected_ids = {
        "stack", "counter", "traffic-light", "queue", "bounded-counter",
        "bug-tracker", "phone-book", "bank-account", "boolean-flag",
        "temperature-sensor", "thermostat", "door-lock", "todo-list",
        "inventory", "shopping-cart", "access-control", "library-lending",
        "email-inbox", "auction", "version-history",
    }
    actual_ids = set(ALL_EXAMPLES.keys())
    missing = expected_ids - actual_ids
    extra = actual_ids - expected_ids
    if missing:
        errors.append(f"ALL_EXAMPLES missing domain IDs: {missing}")
    if extra:
        warnings.append(f"ALL_EXAMPLES has unexpected domain IDs: {extra}")

    # Pattern coverage — every Pattern enum should appear at least once
    all_patterns: set[Pattern] = set()
    for ex in ALL_EXAMPLES.values():
        all_patterns.update(ex.patterns)
    unused = set(Pattern) - all_patterns
    if unused:
        warnings.append(f"Patterns never used across any example: {[p.name for p in unused]}")

    # ================================================================
    # Pipeline check
    # ================================================================
    try:
        import inspect
        from alspec.stages import _execute_signature_code
        source = inspect.getsource(_execute_signature_code)

        if "normalized" in source:
            errors.append("stages.py: _execute_signature_code still contains 'normalized'")
        if "Pattern B" in source or "Pattern A" in source:
            errors.append("stages.py: _execute_signature_code still contains legacy Pattern A/B comments")
        if "generated_sorts[" in source and "GeneratedSortInfo(" in source and "patch" in source.lower():
            errors.append("stages.py: _execute_signature_code still patches generated_sorts")

        # Make sure it actually enforces the type
        if "GeneratedSortInfo" not in source or "isinstance" not in source:
            errors.append("stages.py: _execute_signature_code doesn't validate GeneratedSortInfo types")

    except Exception as e:
        errors.append(f"stages.py: Could not inspect _execute_signature_code: {e}")

    # ================================================================
    # Report
    # ================================================================
    if errors:
        print(f"{'='*60}")
        print(f"  ERRORS: {len(errors)}")
        print(f"{'='*60}\n")
        for i, err in enumerate(errors, 1):
            print(f"  ✗ {i:2d}. {err}")

    if warnings:
        print(f"\n{'='*60}")
        print(f"  WARNINGS: {len(warnings)}")
        print(f"{'='*60}\n")
        for i, warn in enumerate(warnings, 1):
            print(f"  ⚠ {i:2d}. {warn}")

    if not errors and not warnings:
        print("  ✓ All 20 examples pass validation!")

    if not errors:
        # Print summary table
        print(f"\n{'='*60}")
        print(f"  SUMMARY")
        print(f"{'='*60}\n")
        print(f"  {'Domain':<22s} {'Patterns':>8s} {'Axioms':>7s} {'Obligations':>12s} {'Full tok':>9s} {'Bare tok':>9s}")
        print(f"  {'─'*22} {'─'*8} {'─'*7} {'─'*12} {'─'*9} {'─'*9}")
        for did, ex in sorted(ALL_EXAMPLES.items()):
            axioms = len(re.findall(r'Axiom\s*\(', ex.code))
            toks = ex.token_estimate
            print(
                f"  {did:<22s} {len(ex.patterns):>8d} {axioms:>7d} "
                f"{len(ex.obligations):>12d} {toks['FULL']:>9d} {toks['CODE_BARE']:>9d}"
            )
        print()

    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
