"""Two-stage spec generation pipeline.

Stage 1: LLM generates a Signature with generated_sorts annotations
Stage 2: Deterministic obligation table generation
Stage 3: LLM generates axioms guided by the obligation table

The pipeline is the core logic; eval harness is a thin wrapper around it.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from .llm import AsyncLLMClient, UsageInfo
from .obligation import build_obligation_table, ObligationTable
from .obligation_render import render_obligation_table
from .prompt import render
from .prompt_chunks import ChunkId, Stage, assemble_prompt, build_default_prompt
from .result import Err, Ok, Result
from .score import SpecScore, score_spec
from .signature import GeneratedSortInfo, Signature
from .spec import Spec


# ---------------------------------------------------------------------------
# Pipeline result
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StageUsage:
    """Token usage for a single pipeline stage."""

    stage: str
    usage: UsageInfo | None


@dataclass(frozen=True)
class PipelineResult:
    """Complete result from the two-stage pipeline."""

    success: bool

    # Stage 1 outputs
    signature: Signature | None
    signature_code: str | None
    signature_analysis: str | None

    # Deterministic stage outputs
    obligation_table: ObligationTable | None
    obligation_table_rendered: str | None

    # Stage 2 outputs
    spec: Spec | None
    spec_code: str | None
    spec_analysis: str | None

    # Scoring
    score: SpecScore | None

    # Errors
    error: str | None
    error_stage: str | None  # "stage1", "obligation", "stage2", "validation"

    # Timing & usage
    stage_usages: tuple[StageUsage, ...]
    total_latency_ms: int


# ---------------------------------------------------------------------------
# Prompt building
# ---------------------------------------------------------------------------


def _build_stage1_system_prompt() -> str:
    """Build the system prompt for Stage 1 (signature generation)."""
    return build_default_prompt(Stage.STAGE1)


def _build_stage2_system_prompt() -> str:
    """Build the system prompt for Stage 2 (axiom generation)."""
    return build_default_prompt(Stage.STAGE2)


def _build_stage1_user_prompt(domain_description: str, fn_name: str) -> str:
    """Build Stage 1 user prompt: generate signature only."""
    return render(
        "generate_signature.md.j2",
        domain_description=domain_description,
        fn_name=fn_name,
    )


def _build_stage2_user_prompt(
    domain_description: str,
    fn_name: str,
    signature_code: str,
    obligation_table_md: str,
) -> str:
    """Build Stage 2 user prompt: generate axioms from signature + obligation table."""
    return render(
        "generate_axioms.md.j2",
        domain_description=domain_description,
        fn_name=fn_name,
        signature_code=signature_code,
        obligation_table_md=obligation_table_md,
    )


# ---------------------------------------------------------------------------
# Code execution helpers
# ---------------------------------------------------------------------------


def _execute_signature_code(code: str) -> Signature | str:
    """Execute Stage 1 code and extract a Signature.

    The LLM must produce a Signature with GeneratedSortInfo objects
    baked into the constructor. No legacy normalization — fail loud
    if the format is wrong.
    """
    namespace: dict[str, Any] = {}
    exec("from alspec import *", namespace)
    exec("from alspec.helpers import *", namespace)

    try:
        exec(code, namespace)
    except Exception as e:
        return f"Stage 1 code execution failed: {e}"

    # Look for signature — accept `sig` or `signature` variable names,
    # or any Signature instance in the namespace
    sig = namespace.get("sig") or namespace.get("signature")
    if sig is None:
        for name, val in namespace.items():
            if isinstance(val, Signature):
                sig = val
                break

    if not isinstance(sig, Signature):
        return "Stage 1 code did not produce a Signature object (expected `sig = Signature(...))`"


    for sort_name, info in sig.generated_sorts.items():
        if not isinstance(info, GeneratedSortInfo):
            return (
                f"generated_sorts['{sort_name}'] is {type(info).__name__}, "
                f"expected GeneratedSortInfo. Raw tuples/dicts are not accepted."
            )

    return sig


def _execute_spec_code(code: str, fn_name: str) -> Spec | str:
    """Execute Stage 2 code and call the spec function."""
    namespace: dict[str, Any] = {}
    exec("from alspec import *", namespace)
    exec("from alspec.helpers import *", namespace)

    try:
        exec(code, namespace)
    except Exception as e:
        return f"Stage 2 code execution failed: {e}"

    if fn_name not in namespace:
        return f"Function '{fn_name}' not found in generated code"

    try:
        spec = namespace[fn_name]()
    except Exception as e:
        return f"Spec function raised: {e}"

    if not isinstance(spec, Spec):
        return f"Function returned {type(spec).__name__}, expected Spec"

    return spec


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------


async def run_pipeline_stage1_only(
    client: AsyncLLMClient,
    domain_id: str,
    domain_description: str,
    model: str,
    *,
    stage1_chunks: list[ChunkId] | None = None,
) -> PipelineResult:
    """Run only Stage 1: Signature generation."""
    fn_name = domain_id.replace("-", "_") + "_spec"
    start_time = time.time()
    stage_usages: list[StageUsage] = []

    # ---- Stage 1: Signature generation ----
    if stage1_chunks is not None:
        system1 = assemble_prompt(
            stage1_chunks, Stage.STAGE1, validate_deps=False, validate_stage=False
        )
    else:
        system1 = _build_stage1_system_prompt()
    stage1_user = _build_stage1_user_prompt(domain_description, fn_name)
    stage1_messages = [
        {"role": "system", "content": system1},
        {"role": "user", "content": stage1_user},
    ]

    result1 = await client.generate_with_tool_call(
        stage1_messages, model=model, tool_name="submit_signature"
    )

    match result1:
        case Err(e):
            return PipelineResult(
                success=False,
                signature=None,
                signature_code=None,
                signature_analysis=None,
                obligation_table=None,
                obligation_table_rendered=None,
                spec=None,
                spec_code=None,
                spec_analysis=None,
                score=None,
                error=f"Stage 1 LLM error: {e}",
                error_stage="stage1",
                stage_usages=tuple(stage_usages),
                total_latency_ms=int((time.time() - start_time) * 1000),
            )
        case Ok((analysis1, code1, usage1)):
            stage_usages.append(StageUsage("stage1", usage1))

    sig_or_err = _execute_signature_code(code1)
    match sig_or_err:
        case str(err):
            return PipelineResult(
                success=False,
                signature=None,
                signature_code=code1,
                signature_analysis=analysis1,
                obligation_table=None,
                obligation_table_rendered=None,
                spec=None,
                spec_code=None,
                spec_analysis=None,
                score=None,
                error=err,
                error_stage="stage1",
                stage_usages=tuple(stage_usages),
                total_latency_ms=int((time.time() - start_time) * 1000),
            )
        case Signature() as sig:
            return PipelineResult(
                success=True,
                signature=sig,
                signature_code=code1,
                signature_analysis=analysis1,
                obligation_table=None,
                obligation_table_rendered=None,
                spec=None,
                spec_code=None,
                spec_analysis=None,
                score=None,
                error=None,
                error_stage=None,
                stage_usages=tuple(stage_usages),
                total_latency_ms=int((time.time() - start_time) * 1000),
            )


async def run_pipeline(
    client: AsyncLLMClient,
    domain_id: str,
    domain_description: str,
    model: str,
    *,
    stage1_chunks: list[ChunkId] | None = None,
) -> PipelineResult:
    """Run the full two-stage pipeline for a domain.

    Stage 1: Generate Signature + generated_sorts
    Deterministic: Build obligation table
    Stage 2: Generate complete Spec with axioms
    Validation: Score the spec
    """
    fn_name = domain_id.replace("-", "_") + "_spec"
    start_time = time.time()

    # ---- Stage 1: Signature generation ----
    s1_result = await run_pipeline_stage1_only(
        client,
        domain_id,
        domain_description,
        model,
        stage1_chunks=stage1_chunks,
    )
    if not s1_result.success:
        return s1_result

    # Since success is True, these are guaranteed
    sig = s1_result.signature
    assert sig is not None
    code1 = s1_result.signature_code
    assert code1 is not None
    analysis1 = s1_result.signature_analysis
    assert analysis1 is not None
    stage_usages = list(s1_result.stage_usages)

    # ---- Deterministic: Obligation table ----
    try:
        table = build_obligation_table(sig)
        table_md = render_obligation_table(sig, table)
    except Exception as e:
        return PipelineResult(
            success=False,
            signature=sig,
            signature_code=code1,
            signature_analysis=analysis1,
            obligation_table=None,
            obligation_table_rendered=None,
            spec=None,
            spec_code=None,
            spec_analysis=None,
            score=None,
            error=f"Obligation table error: {e}",
            error_stage="obligation",
            stage_usages=tuple(stage_usages),
            total_latency_ms=int((time.time() - start_time) * 1000),
        )

    # ---- Stage 2: Axiom generation ----
    stage2_user = _build_stage2_user_prompt(
        domain_description=domain_description,
        fn_name=fn_name,
        signature_code=code1,
        obligation_table_md=table_md,
    )
    system2 = _build_stage2_system_prompt()
    stage2_messages = [
        {"role": "system", "content": system2},
        {"role": "user", "content": stage2_user},
    ]

    result2 = await client.generate_with_tool_call(
        stage2_messages, model=model, tool_name="submit_spec"
    )

    match result2:
        case Err(e):
            return PipelineResult(
                success=False,
                signature=sig, signature_code=code1, signature_analysis=analysis1,
                obligation_table=table, obligation_table_rendered=table_md,
                spec=None, spec_code=None, spec_analysis=None,
                score=None,
                error=f"Stage 2 LLM error: {e}", error_stage="stage2",
                stage_usages=tuple(stage_usages),
                total_latency_ms=int((time.time() - start_time) * 1000),
            )
        case Ok((analysis2, code2, usage2)):
            stage_usages.append(StageUsage("stage2", usage2))

    # ---- Validation ----
    spec_or_err = _execute_spec_code(code2, fn_name)
    match spec_or_err:
        case str(err):
            return PipelineResult(
                success=False,
                signature=sig, signature_code=code1, signature_analysis=analysis1,
                obligation_table=table, obligation_table_rendered=table_md,
                spec=None, spec_code=code2, spec_analysis=analysis2,
                score=None,
                error=err, error_stage="validation",
                stage_usages=tuple(stage_usages),
                total_latency_ms=int((time.time() - start_time) * 1000),
            )
        case Spec() as spec:
            pass

    score = await score_spec(spec, strict=False, audit=True)

    return PipelineResult(
        success=True,
        signature=sig, signature_code=code1, signature_analysis=analysis1,
        obligation_table=table, obligation_table_rendered=table_md,
        spec=spec, spec_code=code2, spec_analysis=analysis2,
        score=score,
        error=None, error_stage=None,
        stage_usages=tuple(stage_usages),
        total_latency_ms=int((time.time() - start_time) * 1000),
    )
