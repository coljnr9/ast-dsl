"""Four-stage spec generation pipeline.

Stage 1 (ANALYSIS):   LLM produces structured domain analysis from source material
Stage 2 (SIGNATURE):  LLM generates a Signature with generated_sorts annotations
Stage 3 (OBLIGATION): Deterministic obligation table generation
Stage 4 (AXIOMS):     LLM generates axioms guided by the obligation table

The pipeline is the core logic; eval harness is a thin wrapper around it.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .llm import AsyncLLMClient, UsageInfo
from .axiom_gen import generate_mechanical_axioms
from .obligation import build_obligation_table, ObligationTable
from .obligation_render import render_obligation_prompt
from .prompt import render
from .prompt_chunks import ChunkId, Stage, assemble_prompt, build_default_prompt
from .result import Err, Ok, Result
from .score import SpecScore, score_spec
from .signature import GeneratedSortInfo, Signature
from .spec import Spec

logger = logging.getLogger(__name__)

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
    """Complete result from the 4-stage pipeline."""

    success: bool

    # Stage 1: Analysis
    domain_analysis: str | None

    # Stage 2: Signature
    signature: Signature | None
    signature_code: str | None
    signature_analysis: str | None

    # Stage 3: Obligation
    obligation_table: ObligationTable | None
    obligation_table_rendered: str | None

    # Stage 4: Axioms
    spec: Spec | None
    spec_code: str | None
    spec_analysis: str | None

    # Scoring
    score: SpecScore | None

    # Errors
    error: str | None
    error_stage: str | None  # "analysis", "signature", "obligation", "axioms", "validation"

    # Timing & usage
    stage_usages: tuple[StageUsage, ...]
    total_latency_ms: int

    # Skip Reasons
    axioms_skip_reason: str | None = None


# ---------------------------------------------------------------------------
# Prompt building
# ---------------------------------------------------------------------------


def _build_signature_system_prompt() -> str:
    """Build the system prompt for Stage 2 (signature generation)."""
    return build_default_prompt(Stage.SIGNATURE)


def _build_axioms_system_prompt() -> str:
    """Build the system prompt for Stage 4 (axiom generation)."""
    return build_default_prompt(Stage.AXIOMS)


def _build_signature_user_prompt(
    domain_description: str,
    domain_analysis: str | None = None,
) -> str:
    """Build Stage 2 user prompt: generate signature only."""
    return render(
        "generate_signature.md.j2",
        domain_description=domain_description,
        domain_analysis=domain_analysis,
    )


def _build_axioms_user_prompt(
    domain_description: str,
    spec_name: str,
    signature_code: str,
    signature_analysis: str,
    obligation_prompt_md: str,
    domain_analysis: str | None = None,
) -> str:
    """Build Stage 4 user prompt: generate axioms from signature + obligation table."""
    return render(
        "generate_axioms.md.j2",
        domain_description=domain_description,
        domain_analysis=domain_analysis,
        spec_name=spec_name,
        signature_code=signature_code,
        signature_analysis=signature_analysis,
        obligation_prompt_md=obligation_prompt_md,
    )


# ---------------------------------------------------------------------------
# Code execution helpers
# ---------------------------------------------------------------------------


def _execute_signature_code(code: str) -> Signature | str:
    """Execute Stage 2 code and extract a Signature.

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
        return f"Stage 2 (Signature) code execution failed: {e}"

    # Look for signature — accept `sig` or `signature` variable names,
    # or any Signature instance in the namespace
    sig = namespace.get("sig") or namespace.get("signature")
    if sig is None:
        for name, val in namespace.items():
            if isinstance(val, Signature):
                sig = val
                break

    if not isinstance(sig, Signature):
        return "Stage 2 code did not produce a Signature object (expected `sig = Signature(...))`"


    for sort_name, info in sig.generated_sorts.items():
        if not isinstance(info, GeneratedSortInfo):
            return (
                f"generated_sorts['{sort_name}'] is {type(info).__name__}, "
                f"expected GeneratedSortInfo. Raw tuples/dicts are not accepted."
            )

    return sig


def _execute_spec_code(code: str) -> Spec | str:
    """Execute Stage 4 code and extract the top-level `spec` variable."""
    namespace: dict[str, Any] = {}
    exec("from alspec import *", namespace)
    exec("from alspec.helpers import *", namespace)

    try:
        exec(code, namespace)
    except Exception as e:
        return f"Stage 4 (Axioms) code execution failed: {e}"

    spec = namespace.get("spec")
    if not isinstance(spec, Spec):
        return (
            f"Stage 4 code did not produce a `spec` variable of type Spec "
            f"(got {type(spec).__name__ if spec is not None else 'nothing'}). "
            "Expected top-level: `spec = Spec(name=..., signature=sig, axioms=axioms)`"
        )

    return spec


# ---------------------------------------------------------------------------
# Error result helper
# ---------------------------------------------------------------------------


def _error_result(
    *,
    error: str,
    error_stage: str,
    stage_usages: list[StageUsage],
    start_time: float,
    domain_analysis: str | None = None,
    signature: Signature | None = None,
    signature_code: str | None = None,
    signature_analysis: str | None = None,
    obligation_table: ObligationTable | None = None,
    obligation_table_rendered: str | None = None,
    spec: Spec | None = None,
    spec_code: str | None = None,
    spec_analysis: str | None = None,
    axioms_skip_reason: str | None = None,
) -> PipelineResult:
    """Build a failed PipelineResult with minimal boilerplate."""
    return PipelineResult(
        success=False,
        domain_analysis=domain_analysis,
        signature=signature,
        signature_code=signature_code,
        signature_analysis=signature_analysis,
        obligation_table=obligation_table,
        obligation_table_rendered=obligation_table_rendered,
        spec=spec,
        spec_code=spec_code,
        spec_analysis=spec_analysis,
        score=None,
        error=error,
        error_stage=error_stage,
        axioms_skip_reason=axioms_skip_reason,
        stage_usages=tuple(stage_usages),
        total_latency_ms=int((time.time() - start_time) * 1000),
    )


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------


async def run_pipeline_signature_only(
    client: AsyncLLMClient,
    domain_id: str,
    domain_description: str,
    model: str,
    *,
    signature_chunks: list[ChunkId] | None = None,
    lens: str | None = None,
    sources: list[Path] | None = None,
    cached_analysis: bool = False,
) -> PipelineResult:
    """Run Stage 1 (Analysis) + Stage 2 (Signature) only."""
    start_time = time.time()
    stage_usages: list[StageUsage] = []

    # ---- Stage 1: Domain Analysis ----
    domain_analysis: str | None = None
    if lens and lens != "none":
        try:
            from .lenses import run_analysis
            domain_analysis, analysis_usage = await run_analysis(
                client, domain_id, domain_description, model,
                sources=sources, lens_name=lens, cached=cached_analysis,
            )
            if analysis_usage:
                stage_usages.append(analysis_usage)
        except Exception as e:
            return _error_result(
                error=f"Stage 1 (Analysis) failed: {e}",
                error_stage="analysis",
                stage_usages=stage_usages,
                start_time=start_time,
            )

    # ---- Stage 2: Signature generation ----
    if signature_chunks is not None:
        system2 = assemble_prompt(
            signature_chunks, Stage.SIGNATURE, validate_deps=False, validate_stage=False
        )
    else:
        system2 = _build_signature_system_prompt()
    stage2_user = _build_signature_user_prompt(domain_description, domain_analysis)
    stage2_messages = [
        {"role": "system", "content": system2},
        {"role": "user", "content": stage2_user},
    ]

    result2 = await client.generate_with_tool_call(
        stage2_messages,
        model=model,
        tool_name="submit_signature",
        name=f"Stage 2 (Signature) - {domain_id}"
    )

    match result2:
        case Err(e):
            return _error_result(
                error=f"Stage 2 (Signature) LLM error: {result2.error_value}",
                error_stage="signature",
                stage_usages=stage_usages,
                start_time=start_time,
                domain_analysis=domain_analysis,
                axioms_skip_reason="Stage 2 LLM failure",
            )
        case Ok((analysis2, code2, usage2)):
            stage_usages.append(StageUsage("signature", usage2))

    sig_or_err = _execute_signature_code(code2)
    match sig_or_err:
        case str(err):
            return _error_result(
                error=err,
                error_stage="signature",
                stage_usages=stage_usages,
                start_time=start_time,
                domain_analysis=domain_analysis,
                signature_code=code2,
                signature_analysis=analysis2,
                axioms_skip_reason="Stage 2 code exec failure",
            )
        case Signature() as sig:
            return PipelineResult(
                success=True,
                domain_analysis=domain_analysis,
                signature=sig,
                signature_code=code2,
                signature_analysis=analysis2,
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


# Backward-compatible alias
async def run_pipeline_stage1_only(
    client: AsyncLLMClient,
    domain_id: str,
    domain_description: str,
    model: str,
    *,
    stage1_chunks: list[ChunkId] | None = None,
    lens: str | None = None,
    sources: list[Path] | None = None,
    cached_analysis: bool = False,
) -> PipelineResult:
    """[DEPRECATED] Use run_pipeline_signature_only() instead."""
    return await run_pipeline_signature_only(
        client, domain_id, domain_description, model,
        signature_chunks=stage1_chunks, lens=lens,
        sources=sources, cached_analysis=cached_analysis,
    )


async def run_pipeline(
    client: AsyncLLMClient,
    domain_id: str,
    domain_description: str,
    model: str,
    *,
    signature_chunks: list[ChunkId] | None = None,
    # Legacy alias kept for backward compat:
    stage1_chunks: list[ChunkId] | None = None,
    lens: str | None = None,
    sources: list[Path] | None = None,
    cached_analysis: bool = False,
) -> PipelineResult:
    """Run the full 4-stage pipeline for a domain.

    Stage 1 (Analysis):  Domain analysis from source material
    Stage 2 (Signature): Generate Signature + generated_sorts
    Stage 3 (Obligation): Build obligation table (deterministic)
    Stage 4 (Axioms):    Generate complete Spec with axioms
    Validation:          Score the spec
    """
    # Support legacy parameter name
    effective_sig_chunks = signature_chunks or stage1_chunks

    start_time = time.time()
    stage_usages: list[StageUsage] = []

    # ---- Stage 1: Domain Analysis ----
    domain_analysis: str | None = None
    if lens and lens != "none":
        try:
            from .lenses import run_analysis
            domain_analysis, analysis_usage = await run_analysis(
                client, domain_id, domain_description, model,
                sources=sources, lens_name=lens, cached=cached_analysis,
            )
            if analysis_usage:
                stage_usages.append(analysis_usage)
        except Exception as e:
            return _error_result(
                error=f"Stage 1 (Analysis) failed: {e}",
                error_stage="analysis",
                stage_usages=stage_usages,
                start_time=start_time,
            )

    # ---- Stage 2: Signature generation ----
    if effective_sig_chunks is not None:
        system2 = assemble_prompt(
            effective_sig_chunks, Stage.SIGNATURE, validate_deps=False, validate_stage=False
        )
    else:
        system2 = _build_signature_system_prompt()

    stage2_user = _build_signature_user_prompt(domain_description, domain_analysis)
    stage2_messages = [
        {"role": "system", "content": system2},
        {"role": "user", "content": stage2_user},
    ]

    result2 = await client.generate_with_tool_call(
        stage2_messages,
        model=model,
        tool_name="submit_signature",
        name=f"Stage 2 (Signature) - {domain_id}"
    )

    match result2:
        case Err(e):
            return _error_result(
                error=f"Stage 2 (Signature) LLM error: {result2.error_value}",
                error_stage="signature",
                stage_usages=stage_usages,
                start_time=start_time,
                domain_analysis=domain_analysis,
                axioms_skip_reason="Stage 2 LLM failure",
            )
        case Ok((analysis2, code2, usage2)):
            stage_usages.append(StageUsage("signature", usage2))

    sig_or_err = _execute_signature_code(code2)
    match sig_or_err:
        case str(err):
            return _error_result(
                error=err,
                error_stage="signature",
                stage_usages=stage_usages,
                start_time=start_time,
                domain_analysis=domain_analysis,
                signature_code=code2,
                signature_analysis=analysis2,
                axioms_skip_reason="Stage 2 code exec failure",
            )
        case Signature() as sig:
            pass

    # ---- Stage 3: Obligation Table (deterministic) ----
    from .obligation import ObligationTableError

    ob_start = time.time()
    try:
        table = build_obligation_table(sig)
        mech_report = generate_mechanical_axioms(sig, table)
        table_md = render_obligation_prompt(sig, table, mech_report)
        ob_elapsed_ms = int((time.time() - ob_start) * 1000)

        # Log to Langfuse as a child span (deterministic stage — not a generation)
        try:
            from langfuse import get_client as _lf_get_client
            _lf_client = _lf_get_client()
            if _lf_client:
                _ob_span = _lf_client.span(
                    name=f"Stage 3 (Obligation) - {domain_id}",
                    input={
                        "signature_sorts": list(sig.sorts.keys()),
                        "generated_sorts": list(sig.generated_sorts.keys()),
                    },
                    metadata={"deterministic": "true"},
                )
                _ob_span.end(
                    output={
                        "cell_count": len(table.cells),
                        "rendered_chars": str(len(table_md)),
                        "elapsed_ms": str(ob_elapsed_ms),
                    }
                )
        except Exception:
            # Langfuse not available or no active trace — non-fatal
            pass

        stage_usages.append(StageUsage("obligation", None))
    except ObligationTableError as e:
        return _error_result(
            error=f"Obligation Table Validation Failed: {e}",
            error_stage="obligation",
            stage_usages=stage_usages,
            start_time=start_time,
            domain_analysis=domain_analysis,
            signature=sig,
            signature_code=code2,
            signature_analysis=analysis2,
            axioms_skip_reason=str(e),
        )
    except Exception as e:
        return _error_result(
            error=f"Unexpected obligation table error: {e}",
            error_stage="obligation",
            stage_usages=stage_usages,
            start_time=start_time,
            domain_analysis=domain_analysis,
            signature=sig,
            signature_code=code2,
            signature_analysis=analysis2,
        )

    # ---- Stage 4: Axiom generation ----
    spec_name = domain_id.replace("-", " ").title().replace(" ", "")
    stage4_user = _build_axioms_user_prompt(
        domain_description=domain_description,
        spec_name=spec_name,
        signature_code=code2,
        signature_analysis=analysis2,
        obligation_prompt_md=table_md,
        domain_analysis=domain_analysis,
    )
    system4 = _build_axioms_system_prompt()
    stage4_messages = [
        {"role": "system", "content": system4},
        {"role": "user", "content": stage4_user},
    ]

    result4 = await client.generate_with_tool_call(
        stage4_messages,
        model=model,
        tool_name="submit_spec",
        name=f"Stage 4 (Axioms) - {domain_id}"
    )

    match result4:
        case Err(e):
            return _error_result(
                error=f"Stage 4 (Axioms) LLM error: {e}",
                error_stage="axioms",
                stage_usages=stage_usages,
                start_time=start_time,
                domain_analysis=domain_analysis,
                signature=sig,
                signature_code=code2,
                signature_analysis=analysis2,
                obligation_table=table,
                obligation_table_rendered=table_md,
            )
        case Ok((analysis4, code4, usage4)):
            stage_usages.append(StageUsage("axioms", usage4))

    # ---- Validation ----
    spec_or_err = _execute_spec_code(code4)
    match spec_or_err:
        case str(err):
            return _error_result(
                error=err,
                error_stage="validation",
                stage_usages=stage_usages,
                start_time=start_time,
                domain_analysis=domain_analysis,
                signature=sig,
                signature_code=code2,
                signature_analysis=analysis2,
                obligation_table=table,
                obligation_table_rendered=table_md,
                spec_code=code4,
                spec_analysis=analysis4,
            )
        case Spec() as spec:
            # Merge mechanical axioms (belt-and-suspenders: LLM was told not to repeat
            # these, but we merge anyway to guarantee coverage)
            mech_labels = {a.label for a in mech_report.axioms}
            combined_axioms = list(mech_report.axioms) + [
                a for a in spec.axioms if a.label not in mech_labels
            ]
            spec = Spec(
                name=spec.name,
                signature=sig,  # Use the validated signature
                axioms=tuple(combined_axioms),
            )

    score = await score_spec(spec, strict=False, audit=True)

    return PipelineResult(
        success=True,
        domain_analysis=domain_analysis,
        signature=sig, signature_code=code2, signature_analysis=analysis2,
        obligation_table=table, obligation_table_rendered=table_md,
        spec=spec, spec_code=code4, spec_analysis=analysis4,
        score=score,
        error=None, error_stage=None,
        stage_usages=tuple(stage_usages),
        total_latency_ms=int((time.time() - start_time) * 1000),
    )


# ---------------------------------------------------------------------------
# CLI Entrypoint
# ---------------------------------------------------------------------------


async def _main():
    import argparse
    import sys
    from alspec.llm import AsyncLLMClient

    parser = argparse.ArgumentParser(description="Alspec Pipeline CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run the pipeline for a domain")
    run_parser.add_argument("--domain", required=True, help="Domain ID (e.g. 'auction')")
    run_parser.add_argument("--lens", default="entity_lifecycle", help="Domain lens to apply")
    run_parser.add_argument("--model", default="google/gemini-3-flash-preview", help="LLM model")
    run_parser.add_argument("--signature-only", action="store_true", help="Run Stage 1+2 only")
    run_parser.add_argument("--cached-analysis", action="store_true", help="Use cached analysis")

    args = parser.parse_args()

    client_res = AsyncLLMClient.from_env()
    match client_res:
        case Ok(client):
            pass
        case Err(e):
            print(f"Error: {e}")
            sys.exit(1)

    if args.signature_only:
        result = await run_pipeline_signature_only(
            client=client,
            domain_id=args.domain,
            domain_description=args.domain.replace("-", " "),
            model=args.model,
            lens=args.lens,
            cached_analysis=args.cached_analysis,
        )
    else:
        result = await run_pipeline(
            client=client,
            domain_id=args.domain,
            domain_description=args.domain.replace("-", " "),
            model=args.model,
            lens=args.lens,
            cached_analysis=args.cached_analysis,
        )

    if result.success:
        print("Pipeline succeeded!")
        if result.domain_analysis:
            print("\n--- Domain Analysis ---")
            print(result.domain_analysis[:500] + "...")
        if result.signature_code:
            print("\n--- Signature Code ---")
            print(result.signature_code)
        if result.spec_code:
            print("\n--- Spec Code ---")
            print(result.spec_code)
        if result.score:
            print(f"\nScore (Golden Health): {result.score.health:.3f}")
    else:
        print(f"Pipeline failed at {result.error_stage}: {result.error}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(_main())
