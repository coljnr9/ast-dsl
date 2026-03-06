"""Stage 4 scoring: parse spec code, check well-formedness, compute intrinsic health."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from alspec.axiom_gen import generate_mechanical_axioms
from alspec.axiom_match import match_spec
from alspec.check import check_spec
from alspec.obligation import build_obligation_table
from alspec.signature import Signature
from alspec.spec import Spec
from alspec.eval.stage1_score import (
    compute_intrinsic_health,
    _constructor_names,
    _observer_count,
    _check_well_formed,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Stage4Score:
    """Score for a single Stage 4 (axiom generation) trial."""

    domain: str
    trial_id: int
    replicate: int
    model: str

    # Parse & well-formedness
    parse_success: bool
    well_formed: bool
    parse_error: str = ""
    checker_errors: tuple[str, ...] = ()

    # Intrinsic health metrics
    intrinsic_health: float = 0.0
    coverage_ratio: float = 0.0
    covered_cells: int = 0
    total_cells: int = 0
    unmatched_axiom_count: int = 0
    uncovered_cell_count: int = 0

    # Golden health (regression gate, optional)
    golden_health: float | None = None

    # DoE metadata
    factor_levels: dict[str, int] = field(default_factory=dict)

    @property
    def health(self) -> float:
        """Alias for intrinsic_health to support generic evaluation code."""
        return self.intrinsic_health

    # Error summary
    error: str = ""


def _make_zero_stage4_score(
    domain: str,
    trial_id: int,
    replicate: int,
    model: str,
    error: str,
    factor_levels: dict[str, int] | None = None,
) -> Stage4Score:
    """Create a failure score for Stage 4."""
    return Stage4Score(
        domain=domain,
        trial_id=trial_id,
        replicate=replicate,
        model=model,
        parse_success=False,
        well_formed=False,
        error=error,
        factor_levels=factor_levels or {},
    )


async def score_stage4_output(
    code: str,
    domain: str,
    sig: Signature,
    trial_id: int = 0,
    replicate: int = 0,
    model: str = "unknown",
    factor_levels: dict[str, int] | None = None,
    golden_dir: Path | None = None,
) -> Stage4Score:
    """Score raw Stage 4 code against the provided signature.

    Parameters
    ----------
    code:
        The Python code string produced by the LLM.
    domain:
        Domain ID.
    sig:
        The signature used as input to Stage 4.
    trial_id:
        Row index in the design matrix.
    replicate:
        Replicate index (0-based).
    model:
        Model name.
    factor_levels:
        Factor levels for this trial.
    golden_dir:
        Optional path to golden specs.
    """
    # 1. Parse using exec() (identical to pipeline._execute_spec_code)
    namespace: dict[str, Any] = {}
    try:
        exec("from alspec import *", namespace)
        exec("from alspec.helpers import *", namespace)
        exec(code, namespace)
    except Exception as e:
        return _make_zero_stage4_score(
            domain, trial_id, replicate, model,
            f"Stage 4 code execution failed: {e}",
            factor_levels=factor_levels,
        )

    spec = namespace.get("spec")
    if not isinstance(spec, Spec):
        return _make_zero_stage4_score(
            domain, trial_id, replicate, model,
            f"Stage 4 code did not produce a `spec` variable of type Spec (got {type(spec).__name__ if spec is not None else 'nothing'})",
            factor_levels=factor_levels,
        )

    # 1.5. Merge mechanical axioms (Stage 3.5)
    # The LLM sees mechanical axioms in the prompt and is told not to repeat them.
    # We merge them here so that well-formedness and coverage reflect the complete spec.
    table = build_obligation_table(sig)
    mech_report = generate_mechanical_axioms(sig, table)
    mech_labels = {a.label for a in mech_report.axioms}

    combined_axioms = list(mech_report.axioms) + [
        a for a in spec.axioms if a.label not in mech_labels
    ]
    spec = Spec(
        name=spec.name,
        signature=sig,  # Use the validated signature
        axioms=tuple(combined_axioms),
    )

    # 2. Check well-formedness
    checker_report = check_spec(spec)
    well_formed = checker_report.is_well_formed
    checker_errors = tuple(str(d) for d in checker_report.diagnostics if d.severity.value == "error")

    # 3. Obligation table matching
    try:
        table = build_obligation_table(spec.signature)
        match_report = await match_spec(spec, table, spec.signature)
    except Exception as e:
        return _make_zero_stage4_score(
            domain, trial_id, replicate, model,
            f"Scoring failed during matching: {e}",
            factor_levels=factor_levels,
        )

    # 4. Coverage & Health
    total_cells = len(match_report.coverage)
    covered_cells = sum(1 for c in match_report.coverage if c.status.value != "uncovered")
    coverage_ratio = (covered_cells / total_cells) if total_cells > 0 else 0.0
    unmatched_axiom_count = len(match_report.unmatched_axioms)
    
    uncovered_cells = len(match_report.uncovered_cells)

    # 5. Intrinsic Health (structural only)
    # Reuse the same function used in harness.py and stage1_score.py
    ctors = _constructor_names(sig)
    score_dict = {
        "parse_success": True,
        "well_formed": _check_well_formed(sig),
        "has_generated_sorts": bool(sig.generated_sorts),
        "sort_count": len(sig.sorts),
        "function_count": len(sig.functions),
        "predicate_count": len(sig.predicates),
        "constructor_count": len(ctors),
        "observer_count": _observer_count(sig),
        "obligation_cell_count": total_cells,
    }
    intrinsic_res = compute_intrinsic_health(score_dict)

    # 6. Golden Health (optional)
    golden_health = None
    if golden_dir:
        # If we have a golden spec, we could run a more detailed comparison,
        # but for now we follow the simple harness approach.
        pass

    return Stage4Score(
        domain=domain,
        trial_id=trial_id,
        replicate=replicate,
        model=model,
        parse_success=True,
        well_formed=well_formed,
        checker_errors=checker_errors,
        intrinsic_health=intrinsic_res["intrinsic_health"],
        coverage_ratio=coverage_ratio,
        covered_cells=covered_cells,
        total_cells=total_cells,
        unmatched_axiom_count=unmatched_axiom_count,
        uncovered_cell_count=uncovered_cells,
        golden_health=golden_health,
        factor_levels=factor_levels or {},
    )
