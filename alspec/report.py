from __future__ import annotations

from typing import Any

from .check import Severity
from .score import SpecScore


def format_report(score: SpecScore) -> str:
    """Human-readable report for terminal output."""
    lines = []
    lines.append(f"{score.spec_name} — Health: {int(score.health * 100)}/100")

    if score.well_formed:
        lines.append("  ✓ Well-formed (0 errors)")
    else:
        lines.append(f"  × Ill-formed ({score.error_count} errors)")

    for diag in score.diagnostics:
        if diag.severity == Severity.ERROR:
            axiom_str = f" axiom '{diag.axiom}':" if diag.axiom else ""
            lines.append(f"    - [{diag.check}]{axiom_str} {diag.message} (ERROR)")

    if score.warning_count > 0:
        lines.append(
            f"  ⚠ {score.warning_count} warning{'s' if score.warning_count > 1 else ''}"
        )
        for diag in score.diagnostics:
            if diag.severity == Severity.WARNING:
                axiom_str = f" axiom '{diag.axiom}':" if diag.axiom else ""
                lines.append(
                    f"    - [{diag.check}]{axiom_str} {diag.message} (WARNING)"
                )

    lines.append(
        f"  Signature: {score.sort_count} sorts, {score.function_count} functions, {score.predicate_count} predicates, {score.axiom_count} axioms"
    )

    return "\n".join(lines)


def report_json(score: SpecScore) -> dict[str, Any]:
    """Machine-readable report for pipeline integration."""
    return {
        "spec_name": score.spec_name,
        "well_formed": score.well_formed,
        "error_count": score.error_count,
        "warning_count": score.warning_count,
        "health": score.health,
        "sort_count": score.sort_count,
        "function_count": score.function_count,
        "predicate_count": score.predicate_count,
        "axiom_count": score.axiom_count,
        "diagnostics": [
            {
                "check": d.check,
                "severity": d.severity.value,
                "axiom": d.axiom,
                "message": d.message,
                "path": d.path,
            }
            for d in score.diagnostics
        ],
    }
