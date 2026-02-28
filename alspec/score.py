from __future__ import annotations

from dataclasses import dataclass

from .analysis import audit_spec
from .check import Diagnostic, check_spec
from .spec import Spec


@dataclass(frozen=True)
class SpecScore:
    spec_name: str
    well_formed: bool
    error_count: int
    warning_count: int
    health: float
    sort_count: int
    function_count: int
    predicate_count: int
    axiom_count: int
    diagnostics: tuple[Diagnostic, ...]
    # NEW: obligation table coverage
    obligation_cell_count: int = 0          # total cells in obligation table
    covered_cell_count: int = 0             # cells with at least one matching axiom
    uncovered_cell_count: int = 0           # cells with no matching axiom
    unmatched_axiom_count: int = 0          # axioms that don't map to any cell
    coverage_ratio: float | None = None     # covered / total, None if no table


async def score_spec(spec: Spec, *, strict: bool = True, audit: bool = False) -> SpecScore:
    """Check a spec and produce a quality score.

    Parameters
    ----------
    strict:
        If True, health = 0.0 when any checker error is present; otherwise
        health degrades smoothly by 0.15 per error.
    audit:
        If True, run adequacy checks (audit_spec) and include their WARNING-
        level diagnostics in the returned SpecScore.  Audit diagnostics are
        counted in warning_count but NEVER affect well_formed or health —
        they are informational only.
    """
    result = check_spec(spec)

    # Only checker errors affect well-formedness and health.
    error_count = len(result.errors)

    from .check import Severity

    audit_diagnostics = audit_spec(spec) if audit else ()

    # --- NEW: obligation table matching ---
    coverage_diagnostics: tuple[Diagnostic, ...] = ()
    obligation_cell_count = 0
    covered_cell_count = 0
    uncovered_cell_count = 0
    unmatched_axiom_count = 0
    coverage_ratio: float | None = None

    if spec.signature.generated_sorts:
        from .axiom_match import match_spec
        from .obligation import build_obligation_table

        try:
            table = build_obligation_table(spec.signature)
            report = await match_spec(spec, table, spec.signature)

            obligation_cell_count = table.cell_count
            uncovered_cell_count = len(report.uncovered_cells)
            covered_cell_count = obligation_cell_count - uncovered_cell_count
            unmatched_axiom_count = len(report.unmatched_axioms)
            coverage_ratio = (
                covered_cell_count / obligation_cell_count
                if obligation_cell_count > 0
                else 1.0
            )

            coverage_diagnostics = _build_coverage_diagnostics(report)

        except Exception:
            import logging

            logger = logging.getLogger(__name__)
            logger.exception("Obligation table matching failed for %s", spec.name)
            # Don't crash scoring — log and continue without coverage data.
            # The obligation table is informational; checker results are authoritative.
    # --- END NEW ---

    all_diagnostics = result.diagnostics + audit_diagnostics + coverage_diagnostics

    # Checker warnings + audit WARNINGs + coverage WARNINGs count toward warning_count.
    # INFO-level diagnostics are excluded from the count.
    audit_warnings = sum(
        1 for d in audit_diagnostics if d.severity == Severity.WARNING
    )
    coverage_warnings = sum(
        1 for d in coverage_diagnostics if d.severity == Severity.WARNING
    )
    warning_count = len(result.warnings) + audit_warnings + coverage_warnings

    if strict:
        health = 0.0 if error_count > 0 else 1.0
    else:
        health = 1.0
        health -= error_count * 0.15
        health = max(health, 0.0)

    sort_count = len(spec.signature.sorts)
    function_count = len(spec.signature.functions)
    predicate_count = len(spec.signature.predicates)
    axiom_count = len(spec.axioms)

    return SpecScore(
        spec_name=spec.name,
        well_formed=result.is_well_formed,
        error_count=error_count,
        warning_count=warning_count,
        health=health,
        sort_count=sort_count,
        function_count=function_count,
        predicate_count=predicate_count,
        axiom_count=axiom_count,
        diagnostics=all_diagnostics,
        obligation_cell_count=obligation_cell_count,
        covered_cell_count=covered_cell_count,
        uncovered_cell_count=uncovered_cell_count,
        unmatched_axiom_count=unmatched_axiom_count,
        coverage_ratio=coverage_ratio,
    )


def _build_coverage_diagnostics(report: MatchReport) -> tuple[Diagnostic, ...]:
    """Convert a MatchReport into Diagnostic objects.

    Produces:
    - WARNING for each uncovered cell (missing axiom)
    - WARNING for each truly unmatched axiom (MatchKind.UNMATCHED)
    - INFO for coverage summary
    """
    from .axiom_match import CoverageStatus, MatchKind, MatchReport
    from .check import Diagnostic, Severity

    diagnostics: list[Diagnostic] = []

    # Uncovered cells — one WARNING per cell
    for cell in report.uncovered_cells:
        dispatch_str = (
            f" [{cell.dispatch.value}]" if cell.dispatch.value != "plain" else ""
        )
        obs_type = "pred" if cell.observer_is_predicate else "fn"
        diagnostics.append(
            Diagnostic(
                check="coverage",
                severity=Severity.WARNING,
                axiom=None,
                message=(
                    f"Uncovered obligation cell: "
                    f"{cell.observer_name}({obs_type}) × {cell.constructor_name}{dispatch_str} "
                    f"— no axiom matches this cell"
                ),
                path=None,
            )
        )

    # Unmatched axioms — one WARNING per axiom
    for m in report.matches:
        if m.kind == MatchKind.UNMATCHED:
            diagnostics.append(
                Diagnostic(
                    check="coverage",
                    severity=Severity.WARNING,
                    axiom=m.axiom_label,
                    message=f"Unmatched axiom: {m.reason}",
                    path=None,
                )
            )

    # Coverage summary — one INFO diagnostic
    total = len(report.coverage)
    covered = sum(1 for cc in report.coverage if cc.status != CoverageStatus.UNCOVERED)
    preservation_count = sum(
        1 for m in report.matches if m.kind == MatchKind.PRESERVATION
    )

    if total > 0:
        diagnostics.append(
            Diagnostic(
                check="coverage",
                severity=Severity.INFO,
                axiom=None,
                message=(
                    f"Cell coverage: {covered}/{total} "
                    f"({covered/total:.0%})"
                    f"{f', {preservation_count} preservation axioms' if preservation_count else ''}"
                ),
                path=None,
            )
        )

    return tuple(diagnostics)
