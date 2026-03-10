#!/usr/bin/env python3
"""Diagnose compilation failures in eval results.

Reads saved spec files or scores.jsonl from a results directory,
runs multi-pass compilation diagnostics, and produces a histogram
of error types to guide the retry mechanism design.

Usage:
    # From a results directory with specs/ subdirectory:
    uv run python scripts/diagnose_failures.py results/post-hint-fix-2026-03-10

    # From a results directory with scores.jsonl containing code:
    uv run python scripts/diagnose_failures.py results/fresh-cache-2026-03-09

    # Direct .py files:
    uv run python scripts/diagnose_failures.py specs/bounded-counter-rep0.py specs/bounded-counter-rep4.py
"""

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

from alspec.compile_diagnostic import diagnose_code, CompileDiagnostic


def load_code_from_specs_dir(specs_dir: Path) -> list[tuple[str, str, str]]:
    """Load (domain, replicate, code) tuples from a specs/ directory."""
    results = []
    for py_file in sorted(specs_dir.glob("*.py")):
        # Try to parse domain-repN.py pattern
        m = re.match(r"(.+)-rep(\d+)\.py$", py_file.name)
        if m:
            domain, rep = m.group(1), m.group(2)
        else:
            domain = py_file.stem
            rep = "0"
        code = py_file.read_text()
        results.append((domain, rep, code))
    return results


def load_code_from_jsonl(jsonl_path: Path) -> list[tuple[str, str, str]]:
    """Load (domain, replicate, code) tuples from scores.jsonl.

    Only returns entries where code is present and non-empty.
    """
    results = []
    with jsonl_path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            # Try multiple field names
            code = record.get("code") or record.get("spec_code") or ""
            if not code:
                continue
            domain = record.get("domain_id") or record.get("domain") or "unknown"
            rep = str(record.get("replicate", record.get("rep", 0)))
            results.append((domain, rep, code))
    return results


def load_code_from_files(paths: list[Path]) -> list[tuple[str, str, str]]:
    """Load (domain, replicate, code) tuples from explicit file paths."""
    results = []
    for p in paths:
        m = re.match(r"(.+)-rep(\d+)\.py$", p.name)
        if m:
            domain, rep = m.group(1), m.group(2)
        else:
            domain = p.stem
            rep = "0"
        code = p.read_text()
        results.append((domain, rep, code))
    return results


def main():
    parser = argparse.ArgumentParser(
        description="Diagnose compilation failures in eval results."
    )
    parser.add_argument(
        "input",
        nargs="+",
        help="Results directory, or individual .py files",
    )
    parser.add_argument(
        "--all", "-a",
        action="store_true",
        help="Diagnose ALL trials (not just failures). Useful to verify clean trials.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output diagnostics as JSONL to stdout (for downstream tooling).",
    )
    args = parser.parse_args()

    # Collect code samples
    samples: list[tuple[str, str, str]] = []  # (domain, rep, code)

    for input_path_str in args.input:
        input_path = Path(input_path_str)

        if input_path.is_dir():
            # Check for specs/ subdirectory first
            specs_dir = input_path / "specs"
            if specs_dir.is_dir():
                samples.extend(load_code_from_specs_dir(specs_dir))
            # Also check for scores.jsonl
            jsonl_path = input_path / "scores.jsonl"
            if jsonl_path.exists() and not specs_dir.is_dir():
                samples.extend(load_code_from_jsonl(jsonl_path))
            # If neither, warn
            if not specs_dir.is_dir() and not jsonl_path.exists():
                print(f"Warning: {input_path} has neither specs/ nor scores.jsonl", file=sys.stderr)
        elif input_path.suffix == ".py":
            samples.extend(load_code_from_files([input_path]))
        elif input_path.suffix == ".jsonl":
            samples.extend(load_code_from_jsonl(input_path))
        else:
            print(f"Warning: don't know how to handle {input_path}", file=sys.stderr)

    if not samples:
        print("No code samples found.", file=sys.stderr)
        sys.exit(1)

    # Run diagnostics
    diagnostics: list[tuple[str, str, CompileDiagnostic]] = []
    for domain, rep, code in samples:
        diag = diagnose_code(code)
        diagnostics.append((domain, rep, diag))

    # JSON output mode
    if args.json:
        for domain, rep, diag in diagnostics:
            record = diag.to_dict()
            record["domain"] = domain
            record["replicate"] = rep
            print(json.dumps(record))
        return

    # Filter to failures unless --all
    total = len(diagnostics)
    failures = [(d, r, diag) for d, r, diag in diagnostics if diag.pass_name != "clean"]
    clean = total - len(failures)

    # Report
    print(f"\n{'=' * 70}")
    print(f"  Compile Diagnostic Report")
    print(f"{'=' * 70}")
    print(f"  Total trials:    {total}")
    print(f"  Clean:           {clean} ({clean/total*100:.1f}%)")
    print(f"  Failures:        {len(failures)} ({len(failures)/total*100:.1f}%)")

    if not failures:
        print("\n  No failures found. All code compiles and executes cleanly.")
        return

    # Retryable breakdown
    retryable = sum(1 for _, _, d in failures if d.retryable)
    non_retryable = len(failures) - retryable
    print(f"\n  Retryable:       {retryable} ({retryable/len(failures)*100:.0f}% of failures)")
    print(f"  Non-retryable:   {non_retryable} ({non_retryable/len(failures)*100:.0f}% of failures)")

    # By pass
    pass_counts = Counter(d.pass_name for _, _, d in failures)
    print(f"\n{'─' * 70}")
    print(f"  Failures by pass:")
    print(f"{'─' * 70}")
    for pass_name, count in pass_counts.most_common():
        pct = count / len(failures) * 100
        print(f"    {pass_name:<12}  {count:>3}  ({pct:.0f}%)")

    # By error class
    class_counts = Counter(d.error_class for _, _, d in failures)
    print(f"\n{'─' * 70}")
    print(f"  Failures by error class:")
    print(f"{'─' * 70}")
    for error_class, count in class_counts.most_common():
        pct = count / len(failures) * 100
        retry_mark = " [retryable]" if any(
            d.retryable for _, _, d in failures if d.error_class == error_class
        ) else ""
        print(f"    {error_class:<25}  {count:>3}  ({pct:.0f}%){retry_mark}")

    # By error message (top N unique messages)
    msg_counts = Counter(d.message for _, _, d in failures)
    print(f"\n{'─' * 70}")
    print(f"  Top error messages:")
    print(f"{'─' * 70}")
    for msg, count in msg_counts.most_common(10):
        truncated = msg[:70] + "..." if len(msg) > 70 else msg
        print(f"    {count:>3}×  {truncated}")

    # By domain
    domain_counts: dict[str, list[CompileDiagnostic]] = defaultdict(list)
    for domain, rep, diag in failures:
        domain_counts[domain].append(diag)

    print(f"\n{'─' * 70}")
    print(f"  Failures by domain:")
    print(f"{'─' * 70}")
    # Count total trials per domain for failure rate
    domain_totals = Counter(d for d, _, _ in diagnostics)
    for domain in sorted(domain_counts, key=lambda d: len(domain_counts[d]), reverse=True):
        fails = domain_counts[domain]
        total_for_domain = domain_totals[domain]
        rate = len(fails) / total_for_domain * 100
        classes = Counter(d.error_class for d in fails)
        class_str = ", ".join(f"{cls}×{n}" for cls, n in classes.most_common(3))
        print(f"    {domain:<24}  {len(fails):>2}/{total_for_domain:<2}  ({rate:>5.1f}%)  {class_str}")

    # Detailed examples (first 2 per error class)
    print(f"\n{'─' * 70}")
    print(f"  Example errors (up to 2 per class):")
    print(f"{'─' * 70}")
    seen: dict[str, int] = defaultdict(int)
    for domain, rep, diag in failures:
        if seen[diag.error_class] >= 2:
            continue
        seen[diag.error_class] += 1
        print(f"\n    [{diag.error_class}] {domain} rep={rep}")
        print(f"    Pass: {diag.pass_name}  Line: {diag.line_number}  Retryable: {diag.retryable}")
        print(f"    Message: {diag.message}")
        if diag.offending_line:
            print(f"    Code:    {diag.offending_line.strip()}")

    print()


if __name__ == "__main__":
    main()
