from dataclasses import dataclass

from dotenv import load_dotenv

# load_dotenv MUST run before get_client() so the LANGFUSE_* env vars
# are visible when the Langfuse client initializes.
load_dotenv()

from langfuse import get_client, observe, propagate_attributes

from alspec.eval.domains import DomainPrompt
from alspec.llm import AsyncLLMClient
from alspec.pipeline import PipelineResult, run_pipeline
from alspec.score import SpecScore

langfuse = get_client()


@dataclass(frozen=True)
class EvalResult:
    domain_id: str
    model: str
    success: bool
    parse_error: str | None
    checker_error: str | None
    score: SpecScore | None
    analysis: str | None  # The model's chain-of-thought (from submit_spec tool)
    code: str | None  # Extracted / tool-provided code
    latency_ms: int
    prompt_tokens: int | None
    completion_tokens: int | None
    cached_tokens: int | None
    cache_write_tokens: int | None
    # NEW: coverage from obligation table matching
    obligation_cell_count: int = 0
    covered_cell_count: int = 0
    coverage_ratio: float | None = None
    # NEW: intrinsic health
    intrinsic_health: float = 0.0
    tier1_parse: float = 0.0
    tier2_sig: float = 0.0
    tier3_oblig: float = 0.0
    tier4_balance: float = 0.0
    tier5_complexity: float = 0.0
    # NEW: captured failure reasons
    stage2_skip_reason: str | None = None
    # Replicate index (1-based); 1 means no replication
    replicate: int = 1
    # Failure taxonomy classification
    failure_category: str = "pass"  # FailureCategory.value — stored as string for serialization


@dataclass(frozen=True)
class EvalRun:
    timestamp: str
    models: tuple[str, ...]
    prompt_version: str
    results: tuple[EvalResult, ...]


def _pipeline_to_eval(domain_id: str, model: str, pr: PipelineResult) -> EvalResult:
    """Map a PipelineResult to an EvalResult, aggregating token usage across stages."""
    prompt_tokens = 0
    completion_tokens = 0
    cached_tokens = 0
    cache_write_tokens = 0
    for su in pr.stage_usages:
        if su.usage:
            prompt_tokens += su.usage.prompt_tokens
            completion_tokens += su.usage.completion_tokens
            cached_tokens += su.usage.cached_tokens
            cache_write_tokens += su.usage.cache_write_tokens

    # Map error_stage to parse_error vs checker_error
    parse_error: str | None = None
    checker_error: str | None = None
    if pr.error:
        if pr.error_stage in ("signature", "obligation"):
            parse_error = pr.error
        else:  # "axioms", "validation", "analysis"
            checker_error = pr.error

    # Extract coverage from score if available
    obligation_cell_count = 0
    covered_cell_count = 0
    coverage_ratio = None
    if pr.score is not None:
        obligation_cell_count = pr.score.obligation_cell_count
        covered_cell_count = pr.score.covered_cell_count
        coverage_ratio = pr.score.coverage_ratio

    # Compute intrinsic health from structural metrics
    from alspec.eval.stage1_score import compute_intrinsic_health, _constructor_names, _observer_count, _check_well_formed

    intrinsic = {"intrinsic_health": 0.0}
    if pr.signature:
        sig = pr.signature
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
            "obligation_cell_count": pr.score.obligation_cell_count if pr.score else 0,
        }
        res = compute_intrinsic_health(score_dict)
        intrinsic = {
            "intrinsic_health": res["intrinsic_health"],
            "tier1_parse": res["tier1_parse"],
            "tier2_sig": res["tier2_sig"],
            "tier3_oblig": res["tier3_oblig"],
            "tier4_balance": res["tier4_balance"],
            "tier5_complexity": res["tier5_complexity"],
        }
    else:
        # Minimal credit for trying even if parse fails
        intrinsic["intrinsic_health"] = 0.05 if pr.error_stage == "signature" else 0.0

    eval_result = EvalResult(
        domain_id=domain_id,
        model=model,
        success=pr.success,
        parse_error=parse_error,
        checker_error=checker_error,
        score=pr.score,
        analysis=pr.spec_analysis,
        code=pr.spec_code,
        latency_ms=pr.total_latency_ms,
        prompt_tokens=prompt_tokens or None,
        completion_tokens=completion_tokens or None,
        cached_tokens=cached_tokens or None,
        cache_write_tokens=cache_write_tokens or None,
        obligation_cell_count=obligation_cell_count,
        covered_cell_count=covered_cell_count,
        coverage_ratio=coverage_ratio,
        stage2_skip_reason=pr.axioms_skip_reason,
        **intrinsic
    )

    # Classify after construction since classifier reads EvalResult fields.
    import dataclasses
    from alspec.eval.taxonomy import classify_failure
    category = classify_failure(eval_result)
    eval_result = dataclasses.replace(eval_result, failure_category=category.value)

    return eval_result


def _emit_langfuse_scores(eval_result: EvalResult) -> None:
    """Emit Langfuse trace output and scores for a completed eval result."""
    score = eval_result.score

    if score is not None:
        diag_dicts: list[dict[str, str | None]] = [
            {
                "check": d.check,
                "severity": d.severity.value,
                "axiom": d.axiom,
                "message": d.message,
                "path": d.path,
            }
            for d in score.diagnostics
        ]

        unconstrained_count = sum(
            1
            for d in score.diagnostics
            if d.check in ("unconstrained_fn", "unconstrained_pred", "orphan_sort")
        )

        uncovered_count = sum(
            1
            for d in score.diagnostics
            if d.check == "coverage" and d.severity.value == "warning"
            and "Uncovered obligation cell" in d.message
        )

        # Compute cache hit rate from eval_result fields for the trace output
        cache_hit_rate: float | None = None
        if eval_result.prompt_tokens and eval_result.prompt_tokens > 0:
            cached = eval_result.cached_tokens or 0
            cache_hit_rate = round(cached / eval_result.prompt_tokens, 3)

        trace_output = {
            "success": True,
            "health": round(score.health, 3),
            "well_formed": score.well_formed,
            "unconstrained_symbols": unconstrained_count,
            "error_count": score.error_count,
            "warning_count": score.warning_count,
            "diagnostics": diag_dicts,
            "analysis": eval_result.analysis,
            "code": eval_result.code,
            "prompt_tokens": eval_result.prompt_tokens,
            "completion_tokens": eval_result.completion_tokens,
            "cached_tokens": eval_result.cached_tokens,
            "cache_hit_rate": cache_hit_rate,
            "intrinsic_health": eval_result.intrinsic_health,
        }

        if score.obligation_cell_count > 0:
            trace_output["obligation_cell_count"] = score.obligation_cell_count
            trace_output["covered_cell_count"] = score.covered_cell_count
            trace_output["coverage_ratio"] = round(score.coverage_ratio, 3) if score.coverage_ratio is not None else None
            trace_output["uncovered_cell_count"] = uncovered_count

        langfuse.update_current_trace(output=trace_output)

        langfuse.score_current_trace(
            name="spec_health",
            value=score.health,
            comment=f"errors={score.error_count} warnings={score.warning_count}",
        )
        langfuse.score_current_trace(
            name="intrinsic_health",
            value=eval_result.intrinsic_health,
        )
        langfuse.score_current_trace(
            name="well_formed",
            value=1.0 if score.well_formed else 0.0,
        )
        if score.obligation_cell_count > 0 and score.coverage_ratio is not None:
            langfuse.score_current_trace(
                name="cell_coverage",
                value=score.coverage_ratio,
                comment=f"{score.covered_cell_count}/{score.obligation_cell_count}",
            )

        langfuse.score_current_trace(
            name="failure_category",
            value=eval_result.failure_category,
            comment=None,
            data_type="CATEGORICAL",
        )
    else:
        error_msg = eval_result.parse_error or eval_result.checker_error or "unknown failure"

        cache_hit_rate_failed: float | None = None
        if eval_result.prompt_tokens and eval_result.prompt_tokens > 0:
            cached = eval_result.cached_tokens or 0
            cache_hit_rate_failed = round(cached / eval_result.prompt_tokens, 3)

        langfuse.update_current_trace(
            output={
                "success": False,
                "error": error_msg,
                "parse_error": eval_result.parse_error,
                "checker_error": eval_result.checker_error,
                "analysis": eval_result.analysis,
                "code": eval_result.code,
                "prompt_tokens": eval_result.prompt_tokens,
                "completion_tokens": eval_result.completion_tokens,
                "cached_tokens": eval_result.cached_tokens,
                "cache_hit_rate": cache_hit_rate_failed,
                "stage2_skip_reason": eval_result.stage2_skip_reason,
            }
        )
        # Log hard zeros so failed traces are visible in score-based filters.
        langfuse.score_current_trace(
            name="spec_health", value=0.0, comment=error_msg
        )
        langfuse.score_current_trace(name="well_formed", value=0.0)
        langfuse.score_current_trace(
            name="failure_category",
            value=eval_result.failure_category,
            comment=error_msg,
            data_type="CATEGORICAL",
        )


def _emit_session_scores(
    session_id: str,
    results: list[EvalResult],
) -> None:
    """Emit aggregate scores at the Langfuse session level.

    These appear in the session list view, enabling at-a-glance
    monitoring without drilling into individual traces.
    """
    from alspec.eval.report import _rep_aggregate

    agg = _rep_aggregate(results)

    langfuse.create_score(
        name="parse_rate",
        value=agg["parse_rate"],
        session_id=session_id,
        comment=f"{sum(1 for r in results if r.success)}/{len(results)}",
    )
    langfuse.create_score(
        name="wf_rate",
        value=agg["wf_rate"],
        session_id=session_id,
        comment="well-formed / parsed",
    )
    langfuse.create_score(
        name="golden_health",
        value=agg["mean_golden"],
        session_id=session_id,
    )
    langfuse.create_score(
        name="intrinsic_health",
        value=agg["mean_intrinsic"],
        session_id=session_id,
    )
    langfuse.create_score(
        name="coverage",
        value=agg["coverage_ratio"],
        session_id=session_id,
        comment=f"{sum(r.covered_cell_count for r in results if r.success)}/{sum(r.obligation_cell_count for r in results if r.success)}",
    )

    # Also useful: error count and cost
    total_errors = int(agg["total_errors"])
    langfuse.create_score(
        name="total_errors",
        value=float(total_errors),
        session_id=session_id,
    )


@observe(capture_input=False, capture_output=False)
async def run_domain_eval(
    client: AsyncLLMClient,
    domain: DomainPrompt,
    model: str,
    *,
    session_id: str | None = None,
    lens: str | None = None,
    replicate: int = 1,
) -> EvalResult:
    """Run the two-stage pipeline for a single domain and model.

    Langfuse trace structure:
      Trace: eval/{domain.id}/{model_short}
        Input:  domain.description (human-readable task)
        Output: {success, health, error} summary
        └── Generation: completions.create()  ← auto-captured by langfuse.openai
              Input:  [system prompt, user prompt]
              Output: tool call / assistant text

    Pass a shared ``session_id`` (e.g. ``f"eval-{timestamp}"`` generated once
    per batch) to group all runs in a single eval session in Langfuse.
    """
    model_short = model.split("/")[-1]
    trace_name = f"eval/{domain.id}/{model_short}"

    with propagate_attributes(
        trace_name=trace_name,
        session_id=session_id,
        metadata={
            "domain_id": domain.id,
            "complexity": str(domain.complexity),
            "model": model,
            "pipeline": "two-stage",
            "lens": lens or "none",
            "replicate": str(replicate),
        },
        tags=[f"tier:{domain.complexity}", *sorted(domain.expected_features)],
    ):
        langfuse.update_current_trace(input=domain.description)

        result = await run_pipeline(
            client=client,
            domain_id=domain.id,
            domain_description=domain.description,
            model=model,
            lens=lens,
        )

        eval_result = _pipeline_to_eval(domain.id, model, result)

        _emit_langfuse_scores(eval_result)

    return eval_result
