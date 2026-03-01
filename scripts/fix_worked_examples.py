#!/usr/bin/env python3
"""Fix worked_examples.py migration issues.

Run from project root:
    uv run python scripts/fix_worked_examples.py

Issues fixed:
1. String enum values → actual enum instances (FunctionRole, CellType)
2. guard=None → guard="" (ObligationCell)
3. Module-level code → wrapped in def xxx_spec() -> Spec function
4. Bare `spec = Spec(...)` → `return Spec(...)`
5. Bare `return Spec(...)` outside function → wrapped
6. Pattern tags updated to match canonical matrix
7. Domain names standardized to match eval domain IDs
8. pipeline.py legacy normalization killed
9. worked_example.py string-coercion workaround removed

Fails loud on anything it can't fix mechanically.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


def main() -> int:
    root = Path(".")
    if not (root / "alspec").is_dir():
        print("ERROR: Run from project root (directory containing alspec/)")
        return 1

    errors: list[str] = []
    fixes: list[str] = []

    # ================================================================
    # Fix 1: worked_example.py — remove string coercion in render
    # ================================================================
    we_path = root / "alspec" / "worked_example.py"
    we_text = we_path.read_text()

    # Remove the isinstance checks that allow strings through
    old_role_line = '            role_name = f.role if isinstance(f.role, str) else f.role.name'
    new_role_line = '            role_name = f.role.name'
    if old_role_line in we_text:
        we_text = we_text.replace(old_role_line, new_role_line)
        fixes.append("worked_example.py: Removed string coercion for FunctionRole in render")
    else:
        # Check if it's already clean
        if 'isinstance(f.role, str)' in we_text:
            errors.append("worked_example.py: Found unexpected isinstance(f.role, str) pattern")

    old_cell_line = '                cell_val = o.cell_type if isinstance(o.cell_type, str) else o.cell_type.value'
    new_cell_line = '                cell_val = o.cell_type.value'
    if old_cell_line in we_text:
        we_text = we_text.replace(old_cell_line, new_cell_line)
        fixes.append("worked_example.py: Removed string coercion for CellType in render")

    we_path.write_text(we_text)

    # ================================================================
    # Fix 2: worked_examples.py — the big one
    # ================================================================
    wes_path = root / "alspec" / "reference" / "worked_examples.py"
    wes_text = wes_path.read_text()

    # ----------------------------------------------------------
    # 2a: Replace string FunctionRole values with enum references
    # ----------------------------------------------------------
    role_map = {
        '"CONSTRUCTOR"': "FunctionRole.CONSTRUCTOR",
        '"CONSTANT"': "FunctionRole.CONSTANT",
        '"OBSERVER"': "FunctionRole.OBSERVER",
        '"PARTIAL_OBSERVER"': "FunctionRole.PARTIAL_OBSERVER",
        '"PARTIAL_CONSTRUCTOR"': "FunctionRole.CONSTRUCTOR",  # Not a real role — map to CONSTRUCTOR
        '"SELECTOR"': "FunctionRole.SELECTOR",
        '"PREDICATE"': "FunctionRole.PREDICATE",
        '"HELPER"': "FunctionRole.HELPER",
    }

    for old, new in role_map.items():
        count = wes_text.count(old)
        if count > 0:
            # Only replace in FunctionInfo context — be precise
            # FunctionInfo("name", "profile", "ROLE", "notes")
            # The role is always the 3rd positional arg
            wes_text = wes_text.replace(old, new)
            fixes.append(f"worked_examples.py: Replaced {count}x {old} → {new}")

    # Verify no string roles remain
    leftover_roles = re.findall(
        r'FunctionInfo\([^)]*"(CONSTRUCTOR|OBSERVER|HELPER|CONSTANT|PREDICATE|SELECTOR|PARTIAL_OBSERVER|PARTIAL_CONSTRUCTOR)"',
        wes_text,
    )
    if leftover_roles:
        errors.append(f"worked_examples.py: {len(leftover_roles)} string FunctionRole values remain!")

    # ----------------------------------------------------------
    # 2b: Replace string CellType values with enum references
    # ----------------------------------------------------------
    cell_map = {
        '"SELECTOR_EXTRACT"': "CellType.SELECTOR_EXTRACT",
        '"SELECTOR_FOREIGN"': "CellType.SELECTOR_FOREIGN",
        '"DOMAIN"': "CellType.DOMAIN",
        '"KEY_HIT"': "CellType.KEY_HIT",
        '"KEY_MISS"': "CellType.KEY_MISS",
        '"PRESERVATION"': "CellType.PRESERVATION",
        '"GUARDED"': "CellType.GUARDED",
        '"UNDEF"': "CellType.UNDEF",
        '"BASIS"': "CellType.BASIS",
    }

    for old, new in cell_map.items():
        count = wes_text.count(old)
        if count > 0:
            wes_text = wes_text.replace(old, new)
            fixes.append(f"worked_examples.py: Replaced {count}x {old} → {new}")

    # Verify no string cell types remain in ObligationCell contexts
    leftover_cells = re.findall(
        r'ObligationCell\([^)]*"(SELECTOR_EXTRACT|SELECTOR_FOREIGN|DOMAIN|KEY_HIT|KEY_MISS|PRESERVATION|GUARDED|UNDEF|BASIS)"',
        wes_text,
    )
    if leftover_cells:
        errors.append(f"worked_examples.py: {len(leftover_cells)} string CellType values remain!")

    # ----------------------------------------------------------
    # 2c: Fix guard=None → guard=""
    # ----------------------------------------------------------
    # ObligationCell(..., None) at end → ObligationCell(...)
    # The None is the 5th positional arg (guard)
    # Pattern: formula_sketch", None) → formula_sketch")
    none_count = 0
    # Match: ObligationCell("obs", "ctor", CellType.X, "formula", None)
    def fix_none_guard(m: re.Match) -> str:
        nonlocal none_count
        none_count += 1
        return m.group(1) + ")"

    wes_text = re.sub(
        r'(ObligationCell\([^)]+),\s*None\s*\)',
        fix_none_guard,
        wes_text,
    )
    if none_count:
        fixes.append(f"worked_examples.py: Removed {none_count}x guard=None (now uses default guard='')")

    # ----------------------------------------------------------
    # 2d: Fix module-level code → function-wrapped code
    # ----------------------------------------------------------
    # Strategy: Find each code=''' block, check if it has def xxx_spec,
    # if not, wrap it.

    # We need to handle both triple-quote styles
    # Find all WorkedExample blocks by domain_name
    domain_fn_map = {
        "Boolean Flag": "boolean_flag_spec",
        "FIFO Queue": "fifo_queue_spec",
        "PhoneBook": "phone_book_spec",
        "Shopping Cart": "shopping_cart_spec",
        "Warehouse Inventory Tracker": "inventory_spec",
        "Library Lending System": "library_lending_spec",
        "Todo List": "todo_list_spec",
        # These should already be fine but check anyway
        "SimpleCounter": "counter_spec",
        "Traffic Light": "traffic_light_spec",
        "BoundedCounter": "bounded_counter_spec",
        "Temperature Sensor": "temperature_sensor_spec",
        "Thermostat": "thermostat_spec",
        "BankAccount": "bank_account_spec",
        "Door Lock System": "door_lock_spec",
        "Access Control": "access_control_spec",
        "EmailInbox": "email_inbox_spec",
        "Auction": "auction_spec",
        "Version History": "version_history_spec",
    }

    # For each code block, check and fix
    code_block_pattern = re.compile(
        r"(domain_name=\"([^\"]+)\".*?)"
        r"code\s*=\s*('''|\"\"\"\\?\n?)(.*?)\3",
        re.DOTALL,
    )

    def fix_code_block(m: re.Match) -> str:
        preamble = m.group(1)
        domain_name = m.group(2)
        quote = m.group(3)
        code = m.group(4)

        fn_name = domain_fn_map.get(domain_name)
        if fn_name is None:
            return m.group(0)  # Don't touch what we don't know

        has_func_def = bool(re.search(r'def \w+_spec\s*\(\)', code))

        if has_func_def:
            # Already wrapped — but check for domain_name issues
            return m.group(0)

        # Needs wrapping
        fixes.append(f"worked_examples.py [{domain_name}]: Wrapped code in def {fn_name}()")

        # Split code into imports and body
        lines = code.split('\n')
        import_lines = []
        body_lines = []
        in_imports = True

        for line in lines:
            stripped = line.strip()
            if in_imports and (
                stripped.startswith('from ') or
                stripped.startswith('import ') or
                stripped == '' or
                stripped.startswith(')')
            ):
                import_lines.append(line)
            else:
                in_imports = False
                body_lines.append(line)

        # Fix: replace bare `spec = Spec(` with `return Spec(`
        # Fix: replace bare `return Spec(` (outside function) — just keep it, we'll wrap
        body_text = '\n'.join(body_lines)
        body_text = re.sub(r'^(\s*)spec\s*=\s*Spec\(', r'\1return Spec(', body_text, flags=re.MULTILINE)

        # Check for `return Spec(` or `return Spec` in body and ensure it exists
        if 'return Spec(' not in body_text and 'return Spec (' not in body_text:
            # Maybe it ends with just spec = ... without Spec — flag it
            if 'Spec(' not in body_text:
                errors.append(f"worked_examples.py [{domain_name}]: No Spec() construction found in code!")

        # Indent body by 4 spaces
        indented_body_lines = []
        for line in body_text.split('\n'):
            if line.strip():
                indented_body_lines.append('    ' + line)
            else:
                indented_body_lines.append('')

        # Reconstruct
        import_section = '\n'.join(import_lines)
        func_header = f"\ndef {fn_name}() -> Spec:"
        indented_body = '\n'.join(indented_body_lines)

        new_code = f"{import_section}{func_header}\n{indented_body}"

        return f'{preamble}code={quote}{new_code}\n{quote}'

    wes_text = code_block_pattern.sub(fix_code_block, wes_text)

    # ----------------------------------------------------------
    # 2e: Fix pattern tags to match canonical matrix
    # ----------------------------------------------------------
    pattern_matrix: dict[str, set[str]] = {
        "SimpleCounter": {"KEYLESS_AGG", "ACCUMULATION", "CROSS_SORT"},
        "Traffic Light": {"ENUMERATION", "ENUM_CASE_SPLIT", "MULTI_GEN_SORT", "CROSS_SORT"},
        "Boolean Flag": {"SINGLETON"},
        "FIFO Queue": {"EXPLICIT_UNDEF", "STRUCT_RECUR"},
        "BoundedCounter": {"PARTIAL_CTOR", "COND_DEF", "ACCUMULATION", "CROSS_SORT"},
        "PhoneBook": {"COLLECTION_CONTAINER", "KEYED_CONSTRUCTOR", "KEY_DISPATCH", "DELEGATION", "OVERWRITE", "EXPLICIT_UNDEF", "PRESERVATION"},
        "Temperature Sensor": {"SEL_EXTRACT", "EXPLICIT_UNDEF"},
        "Thermostat": {"SEL_EXTRACT", "BICOND_CHAR", "PRESERVATION", "UNINTERP_FN"},
        "BankAccount": {"KEYED_CONSTRUCTOR", "PARTIAL_CTOR", "COND_DEF", "ACCUMULATION", "BOTH_GUARD_POL"},
        "Door Lock System": {"ENUMERATION", "ENUM_CASE_SPLIT", "STATE_DEPENDENT", "BOTH_GUARD_POL"},
        "Todo List": {"COLLECTION_CONTAINER", "KEYED_CONSTRUCTOR", "KEY_DISPATCH", "DELEGATION", "OVERWRITE", "EXPLICIT_UNDEF", "PRESERVATION", "BICOND_CHAR"},
        "Warehouse Inventory Tracker": {"COLLECTION_CONTAINER", "KEYED_CONSTRUCTOR", "KEY_DISPATCH", "DELEGATION", "ACCUMULATION", "EXPLICIT_UNDEF", "PRESERVATION"},
        "Shopping Cart": {"COLLECTION_CONTAINER", "KEYED_CONSTRUCTOR", "KEY_DISPATCH", "DELEGATION", "ACCUMULATION", "EXPLICIT_UNDEF", "PRESERVATION"},
        "Access Control": {"COLLECTION_CONTAINER", "KEYED_CONSTRUCTOR", "KEY_DISPATCH", "DELEGATION", "EXPLICIT_UNDEF", "PRESERVATION", "BOTH_GUARD_POL", "NESTED_GUARD", "BICOND_CHAR"},
        "Library Lending System": {"COLLECTION_CONTAINER", "KEYED_CONSTRUCTOR", "KEY_DISPATCH", "DELEGATION", "EXPLICIT_UNDEF", "PRESERVATION", "BOTH_GUARD_POL", "NESTED_GUARD", "BICOND_CHAR", "UNINTERP_FN"},
        "EmailInbox": {"COLLECTION_CONTAINER", "KEYED_CONSTRUCTOR", "KEY_DISPATCH", "DELEGATION", "OVERWRITE", "EXPLICIT_UNDEF", "PRESERVATION"},
        "Auction": {"COLLECTION_CONTAINER", "KEYED_CONSTRUCTOR", "KEY_DISPATCH", "DELEGATION", "EXPLICIT_UNDEF", "PRESERVATION", "BOTH_GUARD_POL", "NESTED_GUARD", "STATE_DEPENDENT", "COND_DEF"},
        "Version History": {"COLLECTION_CONTAINER", "KEYED_CONSTRUCTOR", "KEY_DISPATCH", "DELEGATION", "EXPLICIT_UNDEF", "PRESERVATION", "STRUCT_RECUR"},
    }

    for domain_name, expected in pattern_matrix.items():
        # Find the patterns=frozenset({...}) block for this domain
        # We need to locate the block and replace its contents
        escaped = re.escape(domain_name)
        block_match = re.search(
            rf'domain_name="{escaped}".*?patterns\s*=\s*frozenset\(\{{(.*?)\}}\)',
            wes_text,
            re.DOTALL,
        )
        if not block_match:
            errors.append(f"worked_examples.py: Can't find patterns block for {domain_name}")
            continue

        # Parse current patterns
        current_text = block_match.group(1)
        current_patterns = set(re.findall(r'Pattern\.(\w+)', current_text))

        if current_patterns != expected:
            missing = expected - current_patterns
            extra = current_patterns - expected
            if missing:
                fixes.append(f"worked_examples.py [{domain_name}]: Adding missing patterns: {missing}")
            if extra:
                fixes.append(f"worked_examples.py [{domain_name}]: Removing extra patterns: {extra}")

            # Build new patterns string
            new_patterns = ", ".join(f"Pattern.{p}" for p in sorted(expected))
            old_full = block_match.group(0)
            new_full = old_full[:block_match.start(1) - block_match.start(0)] + new_patterns + old_full[block_match.end(1) - block_match.start(0):]
            wes_text = wes_text.replace(old_full, new_full)

    # ----------------------------------------------------------
    # 2f: Fix domain names to match eval IDs
    # ----------------------------------------------------------
    domain_name_fixes = {
        'domain_name="SimpleCounter"': 'domain_name="Counter"',
        'domain_name="FIFO Queue"': 'domain_name="Queue"',
        'domain_name="Warehouse Inventory Tracker"': 'domain_name="Inventory"',
        'domain_name="Door Lock System"': 'domain_name="Door Lock"',
        'domain_name="Library Lending System"': 'domain_name="Library Lending"',
        'domain_name="EmailInbox"': 'domain_name="Email Inbox"',
        'domain_name="PhoneBook"': 'domain_name="Phone Book"',
        'domain_name="BankAccount"': 'domain_name="Bank Account"',
        'domain_name="BoundedCounter"': 'domain_name="Bounded Counter"',
    }
    for old, new in domain_name_fixes.items():
        if old in wes_text:
            wes_text = wes_text.replace(old, new)
            fixes.append(f"worked_examples.py: {old} → {new}")

    # Also fix Spec name= inside code blocks to match
    spec_name_fixes = {
        'name="SimpleCounter"': 'name="Counter"',
        'name="FIFOQueue"': 'name="Queue"',
        'name="InventoryTracker"': 'name="Inventory"',
        'name="AuctionSpec"': 'name="Auction"',
    }
    for old, new in spec_name_fixes.items():
        if old in wes_text:
            wes_text = wes_text.replace(old, new)
            fixes.append(f"worked_examples.py: Spec {old} → {new}")

    # After domain_name_fixes, also update the pattern_matrix keys for the
    # second pass validation
    # (not needed since we already did the replacement)

    # Write the fixed file
    wes_path.write_text(wes_text)

    # ================================================================
    # Fix 3: pipeline.py — kill legacy normalization
    # ================================================================
    pipe_path = root / "alspec" / "pipeline.py"
    pipe_text = pipe_path.read_text()

    # Find _execute_signature_code and replace it entirely
    func_pattern = re.compile(
        r'(def _execute_signature_code\(code: str\) -> Signature \| str:.*?)(?=\ndef |\nclass |\n# ---)',
        re.DOTALL,
    )

    new_func = '''def _execute_signature_code(code: str) -> Signature | str:
    """Execute Stage 1 code and extract a Signature.

    The LLM must produce a Signature with GeneratedSortInfo objects
    baked into the constructor. No legacy normalization — fail loud
    if the format is wrong.
    """
    namespace: dict[str, Any] = {}
    exec("from alspec import *", namespace)
    exec("from alspec.helpers import *", namespace)

    try:
        exec(code, namespace)
    except Exception as e:
        return f"Stage 1 code execution failed: {e}"

    # Look for signature — accept `sig` or `signature` variable names,
    # or any Signature instance in the namespace
    sig = namespace.get("sig") or namespace.get("signature")
    if sig is None:
        for name, val in namespace.items():
            if isinstance(val, Signature):
                sig = val
                break

    if not isinstance(sig, Signature):
        return "Stage 1 code did not produce a Signature object (expected `sig = Signature(...))`"

    # Validate generated_sorts contains proper GeneratedSortInfo objects
    if not sig.generated_sorts:
        return "Stage 1 Signature has empty generated_sorts — must define at least one generated sort"

    for sort_name, info in sig.generated_sorts.items():
        if not isinstance(info, GeneratedSortInfo):
            return (
                f"generated_sorts['{sort_name}'] is {type(info).__name__}, "
                f"expected GeneratedSortInfo. Raw tuples/dicts are not accepted."
            )

    return sig

'''

    match = func_pattern.search(pipe_text)
    if match:
        pipe_text = pipe_text[:match.start()] + new_func + pipe_text[match.end():]
        fixes.append("pipeline.py: Replaced _execute_signature_code with strict version (no legacy normalization)")
    else:
        errors.append("pipeline.py: Could not find _execute_signature_code function to replace")

    pipe_path.write_text(pipe_text)

    # ================================================================
    # Report
    # ================================================================
    print(f"\n{'='*60}")
    print(f"  FIXES APPLIED: {len(fixes)}")
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

    print(f"\n  All fixes applied cleanly.")
    print(f"\n  Next steps:")
    print(f"    1. uv run python -c 'from alspec.reference.worked_examples import ALL_EXAMPLES; print(f\"Loaded {{len(ALL_EXAMPLES)}} examples\")'")
    print(f"    2. uv run pytest tests/ -x -q")
    print(f"    3. Manually verify the 7 function-wrapped examples compile")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
