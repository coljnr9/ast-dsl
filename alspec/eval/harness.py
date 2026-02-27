import time
from dataclasses import dataclass
from typing import Any

from langfuse import Langfuse
from langfuse.types import TraceContext

from alspec.eval.domains import DomainPrompt
from alspec.llm import AsyncLLMClient
from alspec.prompt import render
from alspec.reference import (
    api_reference,
    basis_catalog,
    formal_frame,
    methodology,
    type_grammar,
    worked_example,
)
from alspec.result import Err, Ok
from alspec.score import SpecScore, score_spec
from alspec.spec import Spec


@dataclass(frozen=True)
class EvalResult:
    domain_id: str
    model: str
    success: bool
    parse_error: str | None
    score: SpecScore | None
    raw_response: str
    latency_ms: int
    token_count: int | None


@dataclass(frozen=True)
class EvalRun:
    timestamp: str
    models: tuple[str, ...]
    prompt_version: str
    results: tuple[EvalResult, ...]


def build_prompt(domain: DomainPrompt) -> list[dict[str, str]]:
    """Build chat messages from templates. No hardcoded prompt content."""
    system = render(
        "system.md.j2",
        formal_frame=formal_frame.render(),
        type_grammar=type_grammar.render(),
        api_reference=api_reference.render(),
        basis_catalog=basis_catalog.render(),
        methodology=methodology.render(),
        worked_example=worked_example.render(),
    )
    user = render(
        "generate_spec.md.j2",
        domain=domain,
        fn_name=domain.id.replace("-", "_") + "_spec",
        methodology_steps=methodology.render_steps(),
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def extract_code(response: str) -> str | None:
    """Extract Python code from a markdown block, or return original if no block found."""
    if "```python" in response:
        parts = response.split("```python")
        match parts:
            case [_, code_part, *_]:
                return code_part.split("```")[0].strip()
            case _:
                return None
    elif "```" in response:
        parts = response.split("```")
        match parts:
            case [_, code_part, *_]:
                return code_part.split("```")[0].strip()
            case _:
                return None
    return response.strip()


def execute_spec_code(code: str, fn_name: str) -> Spec | str:
    """Execute LLM-generated code and call the spec function."""
    namespace: dict[str, Any] = {}

    # Provide alspec imports in the namespace
    exec("from alspec import *", namespace)
    exec("from alspec.helpers import *", namespace)

    try:
        exec(code, namespace)
    except Exception as e:
        return f"Code execution failed: {e}"

    if fn_name not in namespace:
        return f"Function '{fn_name}' not found in generated code"

    try:
        spec = namespace[fn_name]()
    except Exception as e:
        return f"Spec function raised: {e}"

    match spec:
        case Spec():
            return spec
        case _:
            return f"Function returned {type(spec).__name__}, expected Spec"


async def run_domain_eval(
    client: AsyncLLMClient, domain: DomainPrompt, model: str
) -> EvalResult:
    """Run extraction and evaluation for a single domain and model."""
    messages = build_prompt(domain)
    fn_name = domain.id.replace("-", "_") + "_spec"
    model_short = model.split("/")[-1]
    trace_name = f"eval/{domain.id}/{model_short}"

    # The langfuse.openai wrapper is wrapt-based: passing trace_id into
    # completions.create() is the correct way to parent the generation under
    # a specific trace. The wrapper strips it before forwarding to OpenAI.
    langfuse = Langfuse()
    trace_id = langfuse.create_trace_id()

    # Create the trace record with name, metadata, and tags up front.
    # start_observation creates a root span under the trace; update_trace then
    # sets the trace-level fields. We end it immediately — it's just a setup hook
    # so the trace record exists with the right metadata before the generation lands.
    from langfuse._client.get_client import get_client as _get_lf_client  # noqa: PLC0415
    _root = _get_lf_client().start_observation(
        as_type="span",
        name=trace_name,
        trace_context=TraceContext(trace_id=trace_id),
    )
    _root.update_trace(
        name=trace_name,
        metadata={
            "domain_id": domain.id,
            "complexity": domain.complexity,
            "model": model,
        },
        tags=[
            f"tier:{domain.complexity}",
            *sorted(domain.expected_features),
        ],
    )
    _root.end()

    raw_response = ""
    parse_error = None
    success = False
    score = None
    start_time = time.time()

    result = await client.generate_messages(
        messages,
        model=model,
        trace_id=trace_id,
        generation_name=f"generate_spec/{domain.id}",
    )

    match result:
        case Err(e):
            parse_error = f"API Error: {e}"
        case Ok(content):
            raw_response = content
            extracted_code = extract_code(content) or ""
            spec_or_err = execute_spec_code(extracted_code, fn_name)

            match spec_or_err:
                case str(err):
                    parse_error = err
                case Spec() as s:
                    success = True
                    score = score_spec(s, strict=False)

    latency_ms = int((time.time() - start_time) * 1000)

    # Log quality scores. We always log, even on parse failures, so every trace
    # appears in score-based dashboard filters (missing scores = invisible rows).
    if score is not None:
        langfuse.create_score(
            trace_id=trace_id,
            name="spec_health",
            value=score.health,
            comment=f"errors={score.error_count} warnings={score.warning_count}",
        )
        langfuse.create_score(
            trace_id=trace_id,
            name="obligation_coverage",
            value=score.obligation_ratio,
            comment=f"{score.obligation_covered}/{score.obligation_total} pairs covered",
        )
        langfuse.create_score(
            trace_id=trace_id,
            name="well_formed",
            value=1.0 if score.well_formed else 0.0,
        )
    else:
        # Hard zeros keep failed traces visible in the dashboard.
        langfuse.create_score(
            trace_id=trace_id,
            name="spec_health",
            value=0.0,
            comment=parse_error or "parse failed",
        )
        langfuse.create_score(
            trace_id=trace_id,
            name="obligation_coverage",
            value=0.0,
            comment="spec not parsed",
        )
        langfuse.create_score(trace_id=trace_id, name="well_formed", value=0.0)

    langfuse.flush()

    return EvalResult(
        domain_id=domain.id,
        model=model,
        success=success,
        parse_error=parse_error,
        score=score,
        raw_response=raw_response,
        latency_ms=latency_ms,
        token_count=None,
    )
