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

from .llm import AsyncLLMClient, UsageInfo
from .obligation import ObligationTable
from .prompt_chunks import ChunkId
from .score import SpecScore
from .signature import Signature
from .spec import Spec
from .compile_diagnostic import CompileDiagnostic

from .stages import (
    StageContext,
    AnalysisOutput,
    SignatureOutput,
    ObligationOutput,
    AxiomOutput,
    AnalysisStage,
    SignatureStage,
    ObligationStage,
    AxiomStage,
    StageError,
)

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
    error_stage: str | None

    # Timing & usage
    stage_usages: tuple[StageUsage, ...]
    total_latency_ms: int

    # Skip Reasons
    axioms_skip_reason: str | None = None

    # Structured compilation diagnostic (populated on Stage 2/4 code failures)
    compile_diagnostic: CompileDiagnostic | None = None

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
    compile_diagnostic: CompileDiagnostic | None = None,
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
        stage_usages=tuple(stage_usages),
        total_latency_ms=int((time.time() - start_time) * 1000),
        axioms_skip_reason=axioms_skip_reason,
        compile_diagnostic=compile_diagnostic,
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
    lens: str | None = None,
    sources: list[Path] | None = None,
    cached_analysis: AnalysisOutput | bool | None = None,
) -> PipelineResult:
    """Run Stage 1 (Analysis) + Stage 2 (Signature) only."""
    start_time = time.time()
    stage_usages: list[StageUsage] = []

    ctx = StageContext(
        client=client, model=model,
        domain_id=domain_id, domain_description=domain_description,
        lens=lens,
    )

    domain_analysis: str | None = None
    try:
        # Stage 1
        if isinstance(cached_analysis, AnalysisOutput):
            analysis_out = cached_analysis
        else:
            analysis_out = await AnalysisStage().run(ctx, sources=sources, use_cache_bool=bool(cached_analysis))
        stage_usages.append(StageUsage("analysis", analysis_out.usage))
        domain_analysis = analysis_out.analysis_text

        # Stage 2
        signature_out = await SignatureStage().run(ctx, analysis=analysis_out)
        stage_usages.append(StageUsage("signature", signature_out.usage))

        return PipelineResult(
            success=True,
            domain_analysis=domain_analysis,
            signature=signature_out.signature,
            signature_code=signature_out.code,
            signature_analysis=signature_out.analysis,
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
    except StageError as e:
        return _error_result(
            error=e.message,
            error_stage=e.stage,
            stage_usages=stage_usages,
            start_time=start_time,
            domain_analysis=domain_analysis,
            compile_diagnostic=e.diagnostic,
        )


async def run_pipeline(
    client: AsyncLLMClient,
    domain_id: str,
    domain_description: str,
    model: str,
    *,
    lens: str | None = None,
    sources: list[Path] | None = None,
    cached_analysis: AnalysisOutput | bool | None = None,
    cached_signature: SignatureOutput | None = None,
) -> PipelineResult:
    """Run the complete 4-stage pipeline."""
    start_time = time.time()
    stage_usages: list[StageUsage] = []
    
    ctx = StageContext(
        client=client, model=model,
        domain_id=domain_id, domain_description=domain_description,
        lens=lens,
    )
    
    an_out: AnalysisOutput | None = None
    sig_out: SignatureOutput | None = None
    ob_out: ObligationOutput | None = None
    ax_out: AxiomOutput | None = None
    
    try:
        # Stage 1
        if isinstance(cached_analysis, AnalysisOutput):
            analysis_out = cached_analysis
        else:
            analysis_out = await AnalysisStage().run(ctx, sources=sources, use_cache_bool=bool(cached_analysis))
        stage_usages.append(StageUsage("analysis", analysis_out.usage))
        an_out = analysis_out
        
        # Stage 2
        if cached_signature is not None:
            sig_out = cached_signature
        else:
            sig_out = await SignatureStage().run(ctx, analysis=an_out)
        stage_usages.append(StageUsage("signature", sig_out.usage))
        
        # Stage 3
        ob_out = await ObligationStage().run(ctx, signature=sig_out)
        
        # Stage 4
        ax_out = await AxiomStage().run(ctx, analysis=an_out, signature=sig_out, obligation=ob_out)
        stage_usages.append(StageUsage("axiom", ax_out.usage))
        
        return PipelineResult(
            success=True,
            domain_analysis=an_out.analysis_text,
            signature=sig_out.signature,
            signature_code=sig_out.code,
            signature_analysis=sig_out.analysis,
            obligation_table=ob_out.table,
            obligation_table_rendered=ob_out.rendered_prompt,
            spec=ax_out.spec,
            spec_code=ax_out.code,
            spec_analysis=ax_out.analysis,
            score=ax_out.score,
            error=None, error_stage=None,
            stage_usages=tuple(stage_usages),
            total_latency_ms=int((time.time() - start_time) * 1000),
        )
    except StageError as e:
        return _error_result(
            error=e.message,
            error_stage=e.stage,
            stage_usages=stage_usages,
            start_time=start_time,
            domain_analysis=an_out.analysis_text if an_out else None,
            signature=sig_out.signature if sig_out else None,
            signature_code=sig_out.code if sig_out else None,
            signature_analysis=sig_out.analysis if sig_out else None,
            obligation_table=ob_out.table if ob_out else None,
            obligation_table_rendered=ob_out.rendered_prompt if ob_out else None,
            spec=ax_out.spec if ax_out else None,
            spec_code=ax_out.code if ax_out else None,
            spec_analysis=ax_out.analysis if ax_out else None,
            axioms_skip_reason="Stage failed" if not ax_out else None,
            compile_diagnostic=e.diagnostic,
        )
