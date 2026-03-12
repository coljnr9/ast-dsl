from __future__ import annotations

import time
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .llm import AsyncLLMClient, UsageInfo
from .obligation import ObligationTable, build_obligation_table, ObligationTableError
from .axiom_gen import generate_mechanical_axioms
from .obligation_render import render_obligation_prompt
from .prompt import render
from .skeleton import generate_skeleton, splice_fills, SkeletonData
from .prompt_chunks import ChunkId, Stage, assemble_prompt, build_default_prompt
from .result import Err, Ok
from .score import SpecScore, score_spec
from .signature import GeneratedSortInfo, Signature
from .spec import Spec
from .compile_diagnostic import CompileDiagnostic

logger = logging.getLogger(__name__)

class StageError(Exception):
    """Base exception for pipeline stage failures."""
    def __init__(self, stage: str, message: str, *, cause: Exception | None = None, diagnostic: CompileDiagnostic | None = None):
        self.stage = stage
        self.message = message
        self.cause = cause
        self.diagnostic = diagnostic
        super().__init__(f"Stage '{stage}' failed: {message}")

class AnalysisError(StageError):
    def __init__(self, message: str, *, cause: Exception | None = None, diagnostic: CompileDiagnostic | None = None):
        super().__init__("analysis", message, cause=cause, diagnostic=diagnostic)

class SignatureError(StageError):
    def __init__(self, message: str, *, cause: Exception | None = None, diagnostic: CompileDiagnostic | None = None):
        super().__init__("signature", message, cause=cause, diagnostic=diagnostic)

class ObligationError(StageError):
    def __init__(self, message: str, *, cause: Exception | None = None, diagnostic: CompileDiagnostic | None = None):
        super().__init__("obligation", message, cause=cause, diagnostic=diagnostic)

class AxiomError(StageError):
    def __init__(self, message: str, *, cause: Exception | None = None, diagnostic: CompileDiagnostic | None = None):
        super().__init__("axiom", message, cause=cause, diagnostic=diagnostic)

@dataclass
class StageContext:
    """Shared context for a pipeline run."""
    client: AsyncLLMClient
    model: str
    domain_id: str
    domain_description: str
    session_id: str | None = None
    lens: str | None = None

@dataclass(frozen=True)
class AnalysisOutput:
    """Output from Stage 1 (Analysis)."""
    analysis_text: str | None  # None if no lens was used
    usage: UsageInfo | None

@dataclass(frozen=True)
class SignatureOutput:
    """Output from Stage 2 (Signature)."""
    signature: Signature
    code: str
    analysis: str  # LLM's design rationale
    usage: UsageInfo | None

@dataclass(frozen=True)
class ObligationOutput:
    """Output from Stage 3 (Obligation table + skeleton)."""
    table: ObligationTable
    skeleton: SkeletonData
    rendered_prompt: str  # Markdown for Stage 4 user prompt
    table_md: str  # Rendered table for display

@dataclass(frozen=True)
class AxiomOutput:
    """Output from Stage 4 (Axiom generation)."""
    spec: Spec
    code: str
    analysis: str  # LLM's axiom design reasoning
    score: SpecScore | None
    usage: UsageInfo | None


def _execute_signature_code(code: str) -> Signature | str:
    """Execute Stage 2 code and extract a Signature."""
    namespace: dict[str, Any] = {}
    exec("from alspec import *", namespace)
    exec("from alspec.helpers import *", namespace)

    try:
        exec(code, namespace)
    except Exception as e:
        return f"Stage 2 (Signature) code execution failed: {e}"

    sig = namespace.get("sig") or namespace.get("signature")
    if sig is None:
        for name, val in namespace.items():
            if isinstance(val, Signature):
                sig = val
                break

    if not isinstance(sig, Signature):
        return "Stage 2 code did not produce a Signature object (expected `sig = Signature(...)`)"

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


class PipelineStage(ABC):
    """Base class for all pipeline stages."""
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable stage name for logging and tracing, e.g. 'analysis', 'signature'."""
        ...
    
    async def run(self, ctx: StageContext, **kwargs) -> Any:
        """Template method: wraps _execute with tracing, logging, timing, error handling.
        
        Subclasses should NOT override this. Override _execute instead.
        """
        import time
        import contextlib
        try:
            from langfuse import get_client, propagate_attributes
            lf = get_client()
        except ImportError:
            lf = None
            
        logger.info("Stage '%s' starting for domain '%s'", self.name, ctx.domain_id)
        t0 = time.monotonic()
        
        observation_cm: Any
        if lf:
            observation_cm = lf.start_as_current_observation(
                as_type="span",
                name=f"Stage {self.name.title()} - {ctx.domain_id}",
            )
        else:
            observation_cm = contextlib.nullcontext()

        cm: Any
        if lf:
            cm = propagate_attributes(
                session_id=ctx.session_id,
                metadata={
                    "stage": self.name,
                    "domain_id": ctx.domain_id,
                    "model": ctx.model,
                }
            )
        else:
            cm = contextlib.nullcontext()
            
        try:
            with observation_cm, cm:
                result = await self._execute(ctx, **kwargs)
                elapsed = time.monotonic() - t0
                logger.info(
                    "Stage '%s' completed for domain '%s' in %.1fs",
                    self.name, ctx.domain_id, elapsed,
                )
                return result
        except StageError:
            raise  # Already wrapped
        except Exception as e:
            elapsed = time.monotonic() - t0
            import traceback
            tb = traceback.format_exc()
            logger.error(
                "Stage '%s' failed for domain '%s' after %.1fs: %s\n%s",
                self.name, ctx.domain_id, elapsed, e, tb
            )
            raise self._wrap_error(e) from e
    
    @abstractmethod
    async def _execute(self, ctx: StageContext, **kwargs) -> Any:
        """Subclasses implement the actual stage logic here."""
        ...
    
    @abstractmethod
    def _wrap_error(self, exc: Exception) -> StageError:
        """Wrap an unexpected exception into the appropriate StageError subclass."""
        ...


class AnalysisStage(PipelineStage):
    @property
    def name(self) -> str:
        return "analysis"
        
    def _wrap_error(self, exc: Exception) -> StageError:
        return AnalysisError(str(exc), cause=exc)
        
    async def _execute(self, ctx: StageContext, **kwargs) -> AnalysisOutput:
        sources: list[Path] | None = kwargs.get("sources")
        if not ctx.lens or ctx.lens == "none":
            return AnalysisOutput(analysis_text=None, usage=None)
            
        from .lenses import run_analysis
        domain_analysis, analysis_usage = await run_analysis(
            ctx.client, ctx.domain_id, ctx.domain_description, ctx.model,
            sources=sources, lens_name=ctx.lens, cached=False,
        )
        return AnalysisOutput(analysis_text=domain_analysis, usage=analysis_usage)


class SignatureStage(PipelineStage):
    @property
    def name(self) -> str:
        return "signature"
        
    def _wrap_error(self, exc: Exception) -> StageError:
        return SignatureError(str(exc), cause=exc)
        
    async def _execute(self, ctx: StageContext, **kwargs) -> SignatureOutput:
        analysis: AnalysisOutput = kwargs["analysis"]
        
        system_prompt = build_default_prompt(Stage.SIGNATURE)
        user_prompt = render(
            "generate_signature.md.j2",
            domain_description=ctx.domain_description,
            domain_analysis=analysis.analysis_text,
        )
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        
        result = await ctx.client.generate_with_tool_call(
            messages,
            model=ctx.model,
            tool_name="submit_signature",
            name=f"Stage 2 (Signature) - {ctx.domain_id}"
        )
        
        match result:
            case Err(e):
                raise SignatureError(f"LLM error: {result.error_value}")
            case Ok((analysis_text, code, usage)):
                pass
                
        sig_or_err = _execute_signature_code(code)
        match sig_or_err:
            case str(err):
                from .compile_diagnostic import diagnose_code
                diag = diagnose_code(code, stage="signature")
                raise SignatureError(
                    f"Code execution failed: {err}",
                    diagnostic=diag,
                )
            case Signature() as sig:
                return SignatureOutput(
                    signature=sig,
                    code=code,
                    analysis=analysis_text,
                    usage=usage,
                )


class ObligationStage(PipelineStage):
    @property
    def name(self) -> str:
        return "obligation"
        
    def _wrap_error(self, exc: Exception) -> StageError:
        return ObligationError(str(exc), cause=exc)
        
    async def _execute(self, ctx: StageContext, **kwargs) -> ObligationOutput:
        signature_out: SignatureOutput = kwargs["signature"]
        sig = signature_out.signature
        
        try:
            table = build_obligation_table(sig)
            mech_report = generate_mechanical_axioms(sig, table)
            table_md = render_obligation_prompt(sig, table, mech_report)
            
            spec_name = ctx.domain_id.replace("-", " ").title().replace(" ", "")
            skeleton = generate_skeleton(
                sig=sig,
                signature_code=signature_out.code,
                table=table,
                mechanical_report=mech_report,
                spec_name=spec_name,
            )
            
            return ObligationOutput(
                table=table,
                skeleton=skeleton,
                rendered_prompt=table_md,
                table_md=table_md,
            )
        except ObligationTableError as e:
            raise ObligationError(f"Obligation Table Validation Failed: {e}") from e


class AxiomStage(PipelineStage):
    @property
    def name(self) -> str:
        return "axiom"
        
    def _wrap_error(self, exc: Exception) -> StageError:
        return AxiomError(str(exc), cause=exc)
        
    async def _execute(self, ctx: StageContext, **kwargs) -> AxiomOutput:
        analysis_out: AnalysisOutput = kwargs["analysis"]
        signature_out: SignatureOutput = kwargs["signature"]
        obligation_out: ObligationOutput = kwargs["obligation"]
        
        skeleton = obligation_out.skeleton
        spec_name = ctx.domain_id.replace("-", " ").title().replace(" ", "")
        
        user_prompt = render(
            "generate_axiom_fills.md.j2",
            domain_description=ctx.domain_description,
            domain_analysis=analysis_out.analysis_text,
            spec_name=spec_name,
            skeleton_imports=skeleton.imports,
            skeleton_signature_code=skeleton.signature_code,
            mechanical_axioms="\n".join(
                f"    {line}," for line in skeleton.mechanical_axiom_lines
            ),
            remaining_cells=skeleton.remaining_cells_description,
            signature_analysis=signature_out.analysis,
            constructor_terms="\n".join(
                f"{abbrev} = {expr}" for _, abbrev, expr in skeleton.constructor_terms
            ),
            observer_reference=skeleton.observer_reference,
        )
        system_prompt = build_default_prompt(Stage.AXIOMS)
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        
        result = await ctx.client.generate_with_fills_tool(
            messages,
            model=ctx.model,
            name=f"Stage 4 (Axioms) - {ctx.domain_id}",
            metadata={
                "constructor_term_count": str(len(skeleton.constructor_terms)),
                "constructor_term_sorts": ", ".join(sorted(set(sort for sort, _, _ in skeleton.constructor_terms))),
            }
        )
        
        match result:
            case Err(e):
                raise AxiomError(f"LLM error: {e}")
            case Ok((analysis4, vars4, fills4, usage4)):
                code4 = splice_fills(skeleton, vars4, fills4)
                
        spec_or_err = _execute_spec_code(code4)
        match spec_or_err:
            case str(err):
                from .compile_diagnostic import diagnose_code
                diag = diagnose_code(code4, stage="axioms")
                raise AxiomError(
                    f"Code execution failed: {err}",
                    diagnostic=diag,
                )
            case Spec() as spec:
                combined_axioms = list(spec.axioms)
                spec = Spec(
                    name=spec.name,
                    signature=signature_out.signature,
                    axioms=tuple(combined_axioms),
                )
                
        score = await score_spec(spec, strict=False, audit=True)
        
        return AxiomOutput(
            spec=spec,
            code=code4,
            analysis=analysis4,
            score=score,
            usage=usage4,
        )
