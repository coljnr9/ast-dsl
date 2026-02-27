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


def score_spec(spec: Spec, *, strict: bool = True, audit: bool = False) -> SpecScore:
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
    all_diagnostics = result.diagnostics + audit_diagnostics

    # Checker warnings + audit WARNINGs count toward warning_count.
    # INFO-level diagnostics (e.g., coverage reports) are excluded.
    audit_warnings = sum(
        1 for d in audit_diagnostics if d.severity == Severity.WARNING
    )
    warning_count = len(result.warnings) + audit_warnings

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
    )
