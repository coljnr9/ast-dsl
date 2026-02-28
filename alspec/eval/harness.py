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
        if pr.error_stage in ("stage1", "obligation"):
            parse_error = pr.error
        else:  # "stage2", "validation"
            checker_error = pr.error

    return EvalResult(
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
    )


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

        # Compute cache hit rate from eval_result fields for the trace output
        cache_hit_rate: float | None = None
        if eval_result.prompt_tokens and eval_result.prompt_tokens > 0:
            cached = eval_result.cached_tokens or 0
            cache_hit_rate = round(cached / eval_result.prompt_tokens, 3)

        langfuse.update_current_trace(
            output={
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
            }
        )

        langfuse.score_current_trace(
            name="spec_health",
            value=score.health,
            comment=f"errors={score.error_count} warnings={score.warning_count}",
        )
        langfuse.score_current_trace(
            name="well_formed",
            value=1.0 if score.well_formed else 0.0,
        )
        langfuse.score_current_trace(
            name="unconstrained_symbols",
            value=unconstrained_count,
            comment="dead symbols detected by audit_spec",
        )

        if eval_result.prompt_tokens and eval_result.prompt_tokens > 0:
            cached = eval_result.cached_tokens or 0
            langfuse.score_current_trace(
                name="cache_hit_rate",
                value=cached / eval_result.prompt_tokens,
                comment=f"cached={cached}/{eval_result.prompt_tokens}",
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
            }
        )
        # Log hard zeros so failed traces are visible in score-based filters.
        langfuse.score_current_trace(
            name="spec_health", value=0.0, comment=error_msg
        )
        langfuse.score_current_trace(name="well_formed", value=0.0)


@observe(capture_input=False, capture_output=False)
async def run_domain_eval(
    client: AsyncLLMClient,
    domain: DomainPrompt,
    model: str,
    *,
    session_id: str | None = None,
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
        },
        tags=[f"tier:{domain.complexity}", *sorted(domain.expected_features)],
    ):
        langfuse.update_current_trace(input=domain.description)

        result = await run_pipeline(
            client=client,
            domain_id=domain.id,
            domain_description=domain.description,
            model=model,
        )

        eval_result = _pipeline_to_eval(domain.id, model, result)

        _emit_langfuse_scores(eval_result)

    langfuse.flush()
    return eval_result
