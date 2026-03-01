#!/usr/bin/env python3
"""Second pass fixes for worked_examples.py residual issues.

Run from project root after fix_worked_examples.py:
    uv run python scripts/fix_worked_examples_v2.py

Fixes:
1. constructor=None → constructor="—"
2. guard=None (remaining cases the v1 regex missed)
3. String CellType values that aren't real CellType members (BICOND_CHAR, ACCUMULATION, DELEGATION)
4. Missing return Spec(...) in 4 wrapped functions
"""

from __future__ import annotations

import ast
import re
import sys
import textwrap
from pathlib import Path


def main() -> int:
    root = Path(".")
    if not (root / "alspec").is_dir():
        print("ERROR: Run from project root (directory containing alspec/)")
        return 1

    fixes: list[str] = []
    errors: list[str] = []

    wes_path = root / "alspec" / "reference" / "worked_examples.py"
    wes_text = wes_path.read_text()

    # ================================================================
    # Fix 1: Remaining invalid string CellType values
    # ================================================================
    # These are pattern names the LLM put in CellType position.
    # Map them to the closest real CellType:
    #   BICOND_CHAR → DOMAIN (it's a characterization axiom, basically a domain property)
    #   ACCUMULATION → DOMAIN (accumulation is a pattern, not a cell type)
    #   DELEGATION → KEY_MISS (delegation IS the miss-case behavior)
    invalid_celltypes = {
        '"BICOND_CHAR"': 'CellType.DOMAIN',
        '"ACCUMULATION"': 'CellType.DOMAIN',
        '"DELEGATION"': 'CellType.KEY_MISS',
    }
    for old, new in invalid_celltypes.items():
        count = wes_text.count(old)
        if count > 0:
            wes_text = wes_text.replace(old, new)
            fixes.append(f"Replaced {count}x invalid cell_type {old} → {new}")

    # Also check for any remaining string values in ObligationCell that look like they should be enums
    remaining_str_cells = re.findall(r'ObligationCell\([^)]*"([A-Z_]+)"[^)]*\)', wes_text)
    # Filter out formula_sketch strings (which are lowercase/mixed case descriptions)
    suspicious = [s for s in remaining_str_cells if s.isupper() and len(s) > 3 and s not in (
        # Known OK strings that appear as formula_sketch or guard values
    )]
    if suspicious:
        # Deduplicate
        unique_suspicious = sorted(set(suspicious))
        errors.append(f"Possibly remaining string enums in ObligationCell: {unique_suspicious}")

    # ================================================================
    # Fix 2: constructor=None and guard=None
    # ================================================================
    # We need to do this at the AST level since regex is failing us.
    # Strategy: find all ObligationCell(...) calls and fix None args.
    #
    # ObligationCell has 5 fields:
    #   observer: str, constructor: str, cell_type: CellType, formula_sketch: str, guard: str = ""
    #
    # The agent passed None for constructor (arg 2) and guard (arg 5)

    # Use a line-by-line approach since ObligationCell calls span multiple lines
    lines = wes_text.split('\n')
    new_lines = []
    in_obligation = False
    obligation_buffer = ""
    paren_depth = 0

    none_constructor_fixes = 0
    none_guard_fixes = 0

    def fix_obligation_call(call_text: str) -> str:
        nonlocal none_constructor_fixes, none_guard_fixes
        # Quick check: does it have None?
        if 'None' not in call_text:
            return call_text

        # Parse the positional args naively
        # Find the args between ObligationCell( and the final )
        inner_match = re.match(r'(\s*ObligationCell\()(.+)\)', call_text, re.DOTALL)
        if not inner_match:
            return call_text

        prefix = inner_match.group(1)
        args_text = inner_match.group(2)

        # Split by comma, respecting parens
        # This is tricky because CellType.X has no commas but formula strings might
        # Simpler: just replace None in specific positions

        # Strategy: Find all top-level comma-separated segments
        segments = []
        depth = 0
        current = ""
        for ch in args_text:
            if ch == '(' or ch == '[' or ch == '{':
                depth += 1
                current += ch
            elif ch == ')' or ch == ']' or ch == '}':
                depth -= 1
                current += ch
            elif ch == ',' and depth == 0:
                segments.append(current.strip())
                current = ""
            else:
                current += ch
        if current.strip():
            segments.append(current.strip())

        # Fix constructor (index 1) if None
        if len(segments) >= 2 and segments[1].strip() == 'None':
            segments[1] = '"—"'
            none_constructor_fixes += 1

        # Fix guard (index 4) if None
        if len(segments) >= 5 and segments[4].strip() == 'None':
            # Just remove it entirely — let it use the default
            segments = segments[:4]
            none_guard_fixes += 1

        return prefix + ', '.join(segments) + ')'

    # Process lines, collecting multi-line ObligationCell calls
    i = 0
    while i < len(lines):
        line = lines[i]

        if 'ObligationCell(' in line and not in_obligation:
            # Start of an ObligationCell call
            obligation_buffer = line
            paren_depth = line.count('(') - line.count(')')

            if paren_depth <= 0:
                # Single-line call
                new_lines.append(fix_obligation_call(obligation_buffer))
                obligation_buffer = ""
            else:
                in_obligation = True
        elif in_obligation:
            obligation_buffer += '\n' + line
            paren_depth += line.count('(') - line.count(')')

            if paren_depth <= 0:
                # End of multi-line call
                new_lines.append(fix_obligation_call(obligation_buffer))
                obligation_buffer = ""
                in_obligation = False
        else:
            new_lines.append(line)

        i += 1

    if obligation_buffer:
        new_lines.append(obligation_buffer)

    wes_text = '\n'.join(new_lines)

    if none_constructor_fixes:
        fixes.append(f"Fixed {none_constructor_fixes}x constructor=None → constructor='—'")
    if none_guard_fixes:
        fixes.append(f"Fixed {none_guard_fixes}x guard=None → removed (uses default '')")

    # ================================================================
    # Fix 3: Missing return Spec(...) in wrapped functions
    # ================================================================
    # BoundedCounter, BankAccount, EmailInbox, VersionHistory
    # These had bare code that ended without Spec construction.
    # The original code had either:
    #   - A bare axioms tuple with no Spec
    #   - spec = Spec(...) which got turned into return Spec(...)
    #     but maybe the indentation broke it
    #
    # Check each problem domain

    problem_domains = {
        "bounded_counter_spec": ("BoundedCounter", "Bounded Counter"),
        "bank_account_spec": ("BankAccount", "Bank Account"),
        "email_inbox_spec": ("EmailInbox", "Email Inbox"),
        "version_history_spec": ("VersionHistory", "Version History"),
    }

    for fn_name, (spec_name, display_name) in problem_domains.items():
        # Find the function in the code blocks
        # Look for def fn_name() that doesn't have return Spec(
        pattern = re.compile(
            rf"(def {fn_name}\(\)\s*->\s*Spec:.*?)((?=\ndef |\n[A-Z_]+ = WorkedExample|\nALL_EXAMPLES|\Z))",
            re.DOTALL,
        )
        match = pattern.search(wes_text)
        if not match:
            continue

        func_body = match.group(1)
        if 'return Spec(' in func_body:
            continue  # Already has it

        # Check if it ends with a bare axioms tuple
        # Add return Spec(...) at the end
        # Find the last line of the axioms tuple (the closing paren)
        # Then add return Spec(name=..., signature=sig, axioms=axioms)

        # Actually, these are inside code=''' blocks, not real Python.
        # We need to find them in the code string fields instead.

    # Different approach: find these in the code=''' blocks directly
    for fn_name, (spec_name, display_name) in problem_domains.items():
        # Find code block containing this function
        code_block_re = re.compile(
            rf"(code\s*=\s*'''.*?def {fn_name}\(\)\s*->\s*Spec:)(.*?)(''')",
            re.DOTALL,
        )
        match = code_block_re.search(wes_text)
        if not match:
            # Try """ quotes
            code_block_re = re.compile(
                rf'(code\s*=\s*""".*?def {fn_name}\(\)\s*->\s*Spec:)(.*?)(""")',
                re.DOTALL,
            )
            match = code_block_re.search(wes_text)

        if not match:
            errors.append(f"Could not find code block for {fn_name}")
            continue

        func_header = match.group(1)
        func_body = match.group(2)
        closing = match.group(3)

        if 'return Spec(' in func_body:
            continue

        # Add return Spec() at the end of the function body
        # Detect indentation level
        body_lines = func_body.rstrip().split('\n')
        # Find indentation of axioms = ( line
        indent = "    "
        for line in body_lines:
            if 'axioms' in line and '=' in line:
                indent = re.match(r'^(\s*)', line).group(1)
                break

        return_line = f"\n\n{indent}return Spec(name=\"{spec_name}\", signature=sig, axioms=axioms)\n"
        new_body = func_body.rstrip() + return_line

        wes_text = wes_text[:match.start(2)] + new_body + wes_text[match.end(2):]
        fixes.append(f"Added return Spec() to {fn_name}")

    # ================================================================
    # Write
    # ================================================================
    wes_path.write_text(wes_text)

    # ================================================================
    # Also fix the validate script's raw tuple regex (it's a false positive)
    # ================================================================
    val_path = root / "scripts" / "validate_worked_examples.py"
    if val_path.exists():
        val_text = val_path.read_text()
        # The regex `generated_sorts\s*=\s*\{[^}]*\(\s*"` matches constructors=("new",...)
        # which is CORRECT usage. Replace with a better check.
        old_check = """        # Must use GeneratedSortInfo, not raw tuples
        if re.search(r'generated_sorts\\s*=\\s*\\{[^}]*\\(\\s*"', code):
            # This catches generated_sorts={"X": ("a", "b")} — raw tuples
            warnings.append(f\"{prefix} Possible raw tuple in generated_sorts (check manually)\")"""
        new_check = """        # Must use GeneratedSortInfo, not raw tuples
        # Look for generated_sorts={"SortName": ("ctor1", "ctor2")} without GeneratedSortInfo
        if re.search(r'generated_sorts\\s*=\\s*\\{\\s*"\\w+"\\s*:\\s*\\(', code):
            if 'GeneratedSortInfo' not in code:
                warnings.append(f\"{prefix} Possible raw tuple in generated_sorts (no GeneratedSortInfo found)\")"""
        if old_check in val_text:
            val_text = val_text.replace(old_check, new_check)
            val_path.write_text(val_text)
            fixes.append("validate script: Fixed raw tuple false positive regex")

    # ================================================================
    # Report
    # ================================================================
    print(f"\n{'='*60}")
    print(f"  V2 FIXES APPLIED: {len(fixes)}")
    print(f"{'='*60}\n")
    for i, fix in enumerate(fixes, 1):
        print(f"  ✓ {i:2d}. {fix}")

    if errors:
        print(f"\n{'='*60}")
        print(f"  ERRORS (manual fix needed): {len(errors)}")
        print(f"{'='*60}\n")
        for i, err in enumerate(errors, 1):
            print(f"  ✗ {i:2d}. {err}")
        return 1

    print(f"\n  Now re-run: uv run python scripts/validate_worked_examples.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
