from __future__ import annotations

import os
from dataclasses import dataclass
from typing import TextIO

from alspec.check import Severity
from alspec.score import SpecScore


@dataclass(frozen=True)
class ScoreResult:
    """Outcome of loading and scoring a single spec file."""

    file_path: str
    """Path as provided by the user (may be relative or absolute)."""

    spec_name: str
    """``Spec.name`` value, or an empty string when loading failed."""

    success: bool
    """``True`` if the file was loaded and scored without error."""

    error: str | None
    """Load/exec/parse error message when ``success`` is ``False``."""

    score: SpecScore | None
    """Populated when ``success`` is ``True``."""


def _short_path(path: str, max_len: int = 26) -> str:
    """Return a display-friendly (possibly truncated) relative path."""
    try:
        rel = os.path.relpath(path)
    except ValueError:
        rel = path
    if len(rel) > max_len:
        return "…" + rel[-(max_len - 1) :]
    return rel


def print_score_table(results: list[ScoreResult], out: TextIO) -> None:
    """Print a summary table of scored spec files.

    Columns: File | WF | Health | Sorts | Fns | Preds | Axioms | Errors | Warnings
    """
    out.write("\n")
    out.write(
        "  File                       │ WF  │ Health │ Sorts │ Fns │ Preds │ Axioms │ Errs │ Warns\n"
    )
    out.write(
        "  ─────────────────────────────┼─────┼────────┼───────┼─────┼───────┼────────┼──────┼──────\n"
    )

    total_success = 0
    total_wf = 0
    total_health = 0.0
    total_sorts = 0
    total_fns = 0
    total_preds = 0
    total_axioms = 0
    total_errors = 0
    total_warnings = 0

    for r in results:
        label = _short_path(r.file_path)
        if not r.success:
            out.write(f"  {label:<27}  │ ✗   │  FAIL  │   —   │  —  │   —   │   —    │   —  │   —\n")
            continue

        total_success += 1
        match r.score:
            case None:
                out.write(
                    f"  {label:<27}  │ ✓   │  —     │   —   │  —  │   —   │   —    │   —  │   —\n"
                )
            case score:
                wf = "✓" if score.well_formed else "✗"
                if score.well_formed:
                    total_wf += 1
                total_health += score.health
                total_sorts += score.sort_count
                total_fns += score.function_count
                total_preds += score.predicate_count
                total_axioms += score.axiom_count
                total_errors += score.error_count
                total_warnings += score.warning_count
                out.write(
                    f"  {label:<27}  │ {wf}   │ {score.health:4.2f}   │ {score.sort_count:>4}  "
                    f"│{score.function_count:>3}  │  {score.predicate_count:>3}  │   {score.axiom_count:>3}  "
                    f"│  {score.error_count:>2}  │  {score.warning_count:>2}\n"
                )

    out.write(
        "  ─────────────────────────────┼─────┼────────┼───────┼─────┼───────┼────────┼──────┼──────\n"
    )

    n = len(results)
    mean_health = total_health / total_success if total_success else 0.0
    out.write(
        f"  TOTALS ({total_success}/{n} loaded, {total_wf}/{total_success or 1} WF)  "
        f"│     │ {mean_health:4.2f}   │ {total_sorts:>4}  "
        f"│{total_fns:>3}  │  {total_preds:>3}  │   {total_axioms:>3}  "
        f"│  {total_errors:>2}  │  {total_warnings:>2}\n"
    )

    parse_pct = (total_success / n) * 100 if n else 0.0
    wf_pct = (total_wf / total_success) * 100 if total_success else 0.0
    out.write(f"\n  Load rate:         {parse_pct:5.1f}%\n")
    out.write(f"  Well-formed rate:  {wf_pct:5.1f}%\n")
    out.write(f"  Mean health:       {mean_health:4.2f}\n\n")


def print_score_diagnostics(results: list[ScoreResult], out: TextIO) -> None:
    """Print a per-file diagnostic breakdown (errors, warnings, load failures)."""
    out.write("  --- Diagnostics ---\n")
    for r in results:
        label = _short_path(r.file_path)
        if not r.success:
            out.write(f"\n  {label}\n")
            out.write(f"    ✗ {r.error}\n")
            continue

        match r.score:
            case None:
                continue
            case score:
                if not score.diagnostics:
                    continue
                out.write(f"\n  {label}  (health: {score.health:.2f})\n")
                for diag in score.diagnostics:
                    if diag.severity == Severity.ERROR:
                        out.write(f"    ✗ [{diag.check}] {diag.message}\n")
                    elif diag.severity == Severity.WARNING:
                        out.write(f"    ⚠ [{diag.check}] {diag.message}\n")
                    else:
                        out.write(f"    ℹ [{diag.check}] {diag.message}\n")
    out.write("\n")
