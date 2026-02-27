from __future__ import annotations

from dataclasses import dataclass

from .check import check_spec, compute_obligations, Diagnostic
from .spec import Spec

@dataclass(frozen=True)
class SpecScore:
    spec_name: str
    well_formed: bool
    error_count: int
    warning_count: int
    obligation_total: int
    obligation_covered: int
    obligation_ratio: float
    health: float
    sort_count: int
    function_count: int
    predicate_count: int
    axiom_count: int
    diagnostics: tuple[Diagnostic, ...]

def score_spec(spec: Spec, *, strict: bool = True) -> SpecScore:
    """Check a spec and produce a quality score."""
    result = check_spec(spec)
    
    # Calculate obligation coverage
    obligations = compute_obligations(spec)
    
    obligation_total = len(obligations)
    obligation_covered = sum(1 for obs, con, has_ax, _ in obligations if has_ax)
    
    if obligation_total == 0:
        obligation_ratio = 1.0
    else:
        obligation_ratio = obligation_covered / obligation_total

    error_count = len(result.errors)
    warning_count = len(result.warnings)
    
    health = 1.0
    if strict:
        if error_count > 0:
            health = 0.0
        else:
            health -= warning_count * 0.05
            health -= (1.0 - obligation_ratio) * 0.50
    else:
        health -= error_count * 0.15
        health -= warning_count * 0.05
        health -= (1.0 - obligation_ratio) * 0.50
        
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
        obligation_total=obligation_total,
        obligation_covered=obligation_covered,
        obligation_ratio=obligation_ratio,
        health=health,
        sort_count=sort_count,
        function_count=function_count,
        predicate_count=predicate_count,
        axiom_count=axiom_count,
        diagnostics=result.diagnostics
    )
