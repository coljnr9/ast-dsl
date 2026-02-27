from __future__ import annotations

from dataclasses import dataclass

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


def score_spec(spec: Spec, *, strict: bool = True) -> SpecScore:
    """Check a spec and produce a quality score."""
    result = check_spec(spec)

    error_count = len(result.errors)
    warning_count = len(result.warnings)

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
        diagnostics=result.diagnostics,
    )
