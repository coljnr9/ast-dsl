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
from .reference import (
    api_reference,
    basis_catalog,
    formal_frame,
    methodology,
    type_grammar,
    worked_example,
)
from .result import Err, Ok, Result
from .score import SpecScore, score_spec
from .signature import Signature
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


def _build_system_prompt() -> str:
    """Build the full system prompt (shared across both stages for Phase 1)."""
    return render(
        "system.md.j2",
        formal_frame=formal_frame.render(),
        type_grammar=type_grammar.render(),
        api_reference=api_reference.render(),
        basis_catalog=basis_catalog.render(),
        methodology=methodology.render(),
        worked_example=worked_example.render(),
    )


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

    The code should define variables that we can use to construct a Signature,
    or define a function that returns one. We look for:
      1. A `sig` or `signature` variable of type Signature
      2. A `generated_sorts` variable (dict)
    """
    namespace: dict[str, Any] = {}
    exec("from alspec import *", namespace)
    exec("from alspec.helpers import *", namespace)

    try:
        exec(code, namespace)
    except Exception as e:
        return f"Stage 1 code execution failed: {e}"

    # Look for signature
    sig = namespace.get("sig") or namespace.get("signature")
    if sig is None:
        # Maybe they defined it inside a function
        for name, val in namespace.items():
            if isinstance(val, Signature):
                sig = val
                break

    if not isinstance(sig, Signature):
        return "Stage 1 code did not produce a Signature object (expected `sig = Signature(...))`"

    # Look for generated_sorts
    gen_sorts = namespace.get("generated_sorts")
    if gen_sorts is None:
        return "Stage 1 code did not define `generated_sorts` dict"

    if not isinstance(gen_sorts, dict):
        return f"generated_sorts should be a dict, got {type(gen_sorts).__name__}"

    # Patch generated_sorts onto the signature
    patched = Signature(
        sorts=sig.sorts,
        functions=sig.functions,
        predicates=sig.predicates,
        generated_sorts=gen_sorts,
    )

    return patched


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


async def run_pipeline(
    client: AsyncLLMClient,
    domain_id: str,
    domain_description: str,
    model: str,
) -> PipelineResult:
    """Run the full two-stage pipeline for a domain.

    Stage 1: Generate Signature + generated_sorts
    Deterministic: Build obligation table
    Stage 2: Generate complete Spec with axioms
    Validation: Score the spec
    """
    fn_name = domain_id.replace("-", "_") + "_spec"
    system_prompt = _build_system_prompt()
    start_time = time.time()
    stage_usages: list[StageUsage] = []

    # ---- Stage 1: Signature generation ----
    stage1_user = _build_stage1_user_prompt(domain_description, fn_name)
    stage1_messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": stage1_user},
    ]

    result1 = await client.generate_with_tool_call(
        stage1_messages, model=model, tool_name="submit_signature"
    )

    match result1:
        case Err(e):
            return PipelineResult(
                success=False,
                signature=None, signature_code=None, signature_analysis=None,
                obligation_table=None, obligation_table_rendered=None,
                spec=None, spec_code=None, spec_analysis=None,
                score=None,
                error=f"Stage 1 LLM error: {e}", error_stage="stage1",
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
                signature=None, signature_code=code1, signature_analysis=analysis1,
                obligation_table=None, obligation_table_rendered=None,
                spec=None, spec_code=None, spec_analysis=None,
                score=None,
                error=err, error_stage="stage1",
                stage_usages=tuple(stage_usages),
                total_latency_ms=int((time.time() - start_time) * 1000),
            )
        case Signature() as sig:
            pass

    # ---- Deterministic: Obligation table ----
    try:
        table = build_obligation_table(sig)
        table_md = render_obligation_table(sig, table)
    except Exception as e:
        return PipelineResult(
            success=False,
            signature=sig, signature_code=code1, signature_analysis=analysis1,
            obligation_table=None, obligation_table_rendered=None,
            spec=None, spec_code=None, spec_analysis=None,
            score=None,
            error=f"Obligation table error: {e}", error_stage="obligation",
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
    stage2_messages = [
        {"role": "system", "content": system_prompt},
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

    score = score_spec(spec, strict=False, audit=True)

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
