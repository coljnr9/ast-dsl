#!/usr/bin/env python3
"""Fix broken function wrapping in worked example code blocks + ruff format all.

Run from project root:
    uv run python scripts/fix_worked_examples_v4.py

The v1 wrapping script inserted `def xxx_spec() -> Spec:` inside multi-line
import parentheses. This script:

1. Extracts each code block from worked_examples.py
2. Uses ast.parse() to detect broken ones
3. Fixes structure: moves def after imports close, re-indents body
4. Runs `ruff format` on every code block for consistent style
5. Writes everything back

Requires: ruff (should already be in your dev deps)
"""

from __future__ import annotations

import ast
import re
import subprocess
import sys
import tempfile
from pathlib import Path


def extract_code_blocks(text: str) -> list[tuple[int, int, str, str]]:
    """Extract (start, end, quote_style, code) for each code=''' block."""
    blocks = []
    # Match code='''...''' or code=\"\"\"...\"\"\"
    for m in re.finditer(r"code\s*=\s*('''|\"\"\")(.*?)\1", text, re.DOTALL):
        blocks.append((m.start(2), m.end(2), m.group(1), m.group(2)))
    return blocks


def is_valid_python(code: str) -> tuple[bool, str]:
    """Check if code parses. Returns (ok, error_msg)."""
    try:
        ast.parse(code)
        return True, ""
    except SyntaxError as e:
        return False, f"line {e.lineno}: {e.msg}"


def fix_misplaced_def(code: str) -> str:
    """Fix the known failure: def xxx_spec() inserted inside import parens.

    The broken pattern is:
        from alspec import (
        def xxx_spec() -> Spec:
                Axiom, Conjunction, ...
            )

    Should be:
        from alspec import (
            Axiom, Conjunction, ...
        )

        def xxx_spec() -> Spec:
    """
    lines = code.split("\n")
    result_lines: list[str] = []
    def_line: str | None = None
    in_import_parens = False
    paren_depth = 0

    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Track if we're inside import (...)
        if re.match(r"^from\s+\S+\s+import\s*\(", stripped):
            in_import_parens = True
            paren_depth = stripped.count("(") - stripped.count(")")
            result_lines.append(line)
            i += 1
            continue

        if in_import_parens:
            # Check if this line is the misplaced def
            if re.match(r"def \w+_spec\s*\(", stripped):
                # Stash the def line, don't emit it here
                def_line = stripped
                i += 1
                continue

            # This line is import content — but it may be over-indented
            # because the v1 script indented it as "function body"
            # De-indent: remove exactly one level (4 spaces) of excess
            if line.startswith("        ") and not line.startswith("            "):
                # 8-space indent → 4-space (standard import continuation)
                line = line[4:]

            paren_depth += line.count("(") - line.count(")")
            result_lines.append(line)

            if paren_depth <= 0:
                in_import_parens = False
                # Now emit the stashed def line after the import closes
                if def_line is not None:
                    result_lines.append("")
                    result_lines.append("")
                    result_lines.append(def_line)
                    def_line = None

            i += 1
            continue

        # Outside imports: if we have a def stashed (shouldn't happen but safety)
        if def_line is not None and stripped and not stripped.startswith("#"):
            result_lines.append("")
            result_lines.append(def_line)
            def_line = None

        result_lines.append(line)
        i += 1

    code = "\n".join(result_lines)

    # Now fix indentation of the function body.
    # Everything after `def xxx_spec() -> Spec:` until end should be indented 4 spaces.
    # But the v1 script indented by 4 on top of existing indentation (some lines got 8 spaces).
    # Strategy: find the def line, then for each subsequent non-empty line,
    # ensure it has exactly 4 spaces of indentation (for top-level body statements).
    func_match = re.search(r"^(def \w+_spec\(\)\s*->\s*Spec:)", code, re.MULTILINE)
    if func_match:
        before = code[: func_match.end()]
        body = code[func_match.end() :]

        # Find the minimum indentation of non-empty body lines
        body_lines = body.split("\n")
        non_empty = [l for l in body_lines if l.strip()]
        if non_empty:
            min_indent = min(len(l) - len(l.lstrip()) for l in non_empty)
            # Re-indent: strip min_indent, add 4
            fixed_body_lines = []
            for l in body_lines:
                if l.strip():
                    fixed_body_lines.append("    " + l[min_indent:])
                else:
                    fixed_body_lines.append("")
            body = "\n".join(fixed_body_lines)

        code = before + "\n" + body

    return code


def ruff_format(code: str) -> str:
    """Run ruff format on a code string. Returns formatted code."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", delete=False
    ) as f:
        f.write(code)
        f.flush()
        tmp = Path(f.name)

    try:
        result = subprocess.run(
            ["ruff", "format", str(tmp)],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            print(f"  ruff format warning: {result.stderr.strip()}")
            return code  # Return unformatted if ruff fails
        return tmp.read_text()
    finally:
        tmp.unlink()


def main() -> int:
    root = Path(".")
    if not (root / "alspec").is_dir():
        print("ERROR: Run from project root")
        return 1

    # Check ruff is available
    try:
        subprocess.run(["ruff", "--version"], capture_output=True, check=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        print("ERROR: ruff not found. Install with: uv pip install ruff")
        return 1

    wes_path = root / "alspec" / "reference" / "worked_examples.py"
    text = wes_path.read_text()

    blocks = extract_code_blocks(text)
    print(f"Found {len(blocks)} code blocks\n")

    structural_fixes = 0
    format_fixes = 0
    errors: list[str] = []

    # Process blocks in reverse order so string offsets stay valid
    for start, end, quote, code in reversed(blocks):
        # Find which domain this belongs to (search backwards for domain_name=)
        preceding = text[:start]
        domain_match = re.search(r'domain_name="([^"]+)"', preceding[::-1])
        # That searches reversed string, so re-search forward
        domain_match = list(re.finditer(r'domain_name="([^"]+)"', preceding))
        domain = domain_match[-1].group(1) if domain_match else "???"

        ok, err = is_valid_python(code)

        if not ok:
            print(f"  [{domain}] BROKEN: {err}")
            fixed = fix_misplaced_def(code)
            ok2, err2 = is_valid_python(fixed)
            if ok2:
                print(f"  [{domain}] ✓ Structural fix applied")
                code = fixed
                structural_fixes += 1
            else:
                errors.append(f"[{domain}] Still broken after fix: {err2}")
                print(f"  [{domain}] ✗ Still broken: {err2}")
                continue
        else:
            print(f"  [{domain}] OK (valid syntax)")

        # Ruff format
        formatted = ruff_format(code)
        if formatted != code:
            format_fixes += 1

        # Ensure trailing newline before closing quotes
        if not formatted.endswith("\n"):
            formatted += "\n"

        # Replace in the main text
        text = text[:start] + formatted + text[end:]

    wes_path.write_text(text)

    # Final validation: does the whole file parse?
    ok, err = is_valid_python(text)
    if not ok:
        errors.append(f"worked_examples.py itself doesn't parse: {err}")

    print(f"\n{'='*60}")
    print(f"  Structural fixes: {structural_fixes}")
    print(f"  Ruff-formatted:   {format_fixes}")
    print(f"  Errors:           {len(errors)}")
    print(f"{'='*60}")

    if errors:
        for e in errors:
            print(f"  ✗ {e}")
        return 1

    print(f"\n  ✓ All code blocks valid and formatted")
    print(f"  Now re-run: uv run python scripts/validate_worked_examples.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
