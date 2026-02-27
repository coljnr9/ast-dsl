import time
from dataclasses import dataclass
from typing import Any

from dotenv import load_dotenv

# load_dotenv MUST run before get_client() so the LANGFUSE_* env vars
# are visible when the Langfuse client initializes.
load_dotenv()

from langfuse import get_client, observe, propagate_attributes

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

langfuse = get_client()


@dataclass(frozen=True)
class EvalResult:
    domain_id: str
    model: str
    success: bool
    parse_error: str | None
    checker_error: str | None
    score: SpecScore | None
    analysis: str | None  # The model's reasoning (from submit_spec tool call)
    raw_response: str     # Raw text response (empty string when tool call used)
    code: str | None      # Extracted / tool-provided code (for debugging)
    latency_ms: int
    token_count: int | None


@dataclass(frozen=True)
class EvalRun:
    timestamp: str
    models: tuple[str, ...]
    prompt_version: str
    results: tuple[EvalResult, ...]


def build_prompt(domain: DomainPrompt, use_tool_call: bool) -> list[dict[str, str]]:
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
        use_tool_call=use_tool_call,
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def extract_code(response: str) -> str | None:
    """Extract Python code from a markdown block, or return original if no block found.

    Legacy fallback used only when --no-tool-call is set.
    """
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


@observe(capture_input=False, capture_output=False)
async def run_domain_eval(
    client: AsyncLLMClient,
    domain: DomainPrompt,
    model: str,
    use_tool_call: bool = True,
) -> EvalResult:
    """Run extraction and evaluation for a single domain and model.

    The ``@observe()`` decorator creates a root trace in Langfuse. The
    ``propagate_attributes`` context manager attaches the trace name, metadata,
    and tags to that trace via OTel baggage. The nested ``generate_messages``
    call (also decorated with ``@observe``) becomes a child span automatically.

    When ``use_tool_call=True`` (default), the model is forced to call the
    ``submit_spec`` tool, returning structured ``analysis`` and ``code`` fields.
    When ``use_tool_call=False``, falls back to markdown code-fence extraction.
    """
    messages = build_prompt(domain, use_tool_call=use_tool_call)
    fn_name = domain.id.replace("-", "_") + "_spec"
    model_short = model.split("/")[-1]
    trace_name = f"eval/{domain.id}/{model_short}"

    raw_response = ""
    parse_error: str | None = None
    checker_error: str | None = None
    analysis: str | None = None
    extracted_code: str | None = None
    success = False
    score = None
    start_time = time.time()

    with propagate_attributes(
        trace_name=trace_name,
        metadata={
            "domain_id": domain.id,
            "complexity": str(domain.complexity),
            "model": model,
            "use_tool_call": str(use_tool_call),
        },
        tags=[
            f"tier:{domain.complexity}",
            *sorted(domain.expected_features),
        ],
    ):
        if use_tool_call:
            result = await client.generate_with_tool_call(messages, model=model)

            match result:
                case Err(e):
                    parse_error = str(e)
                case Ok((a, c)):
                    analysis = a
                    extracted_code = c
        else:
            text_result = await client.generate_messages(messages, model=model)

            match text_result:
                case Err(e):
                    parse_error = f"API Error: {e}"
                case Ok(content):
                    raw_response = content
                    extracted_code = extract_code(content)
                    match extracted_code:
                        case None:
                            parse_error = "Could not extract code from response"
                        case _:
                            pass

        # Execute whatever code we extracted (tool-call or legacy)
        if extracted_code is not None and parse_error is None:
            spec_or_err = execute_spec_code(extracted_code, fn_name)

            match spec_or_err:
                case str(err):
                    checker_error = err
                case Spec() as s:
                    success = True
                    score = score_spec(s, strict=False)

    latency_ms = int((time.time() - start_time) * 1000)

    # Log quality scores to the current trace via get_current_trace_id().
    # We always log, even on parse failures — hard zeros keep failed traces
    # visible in score-based dashboard filters (missing scores = invisible rows).
    if score is not None:
        langfuse.score_current_trace(
            name="spec_health",
            value=score.health,
            comment=f"errors={score.error_count} warnings={score.warning_count}",
        )
        langfuse.score_current_trace(
            name="obligation_coverage",
            value=score.obligation_ratio,
            comment=f"{score.obligation_covered}/{score.obligation_total} pairs covered",
        )
        langfuse.score_current_trace(
            name="well_formed",
            value=1.0 if score.well_formed else 0.0,
        )
    else:
        error_comment = parse_error or checker_error or "parse failed"
        langfuse.score_current_trace(
            name="spec_health",
            value=0.0,
            comment=error_comment,
        )
        langfuse.score_current_trace(
            name="obligation_coverage",
            value=0.0,
            comment="spec not parsed",
        )
        langfuse.score_current_trace(name="well_formed", value=0.0)

    langfuse.flush()

    return EvalResult(
        domain_id=domain.id,
        model=model,
        success=success,
        parse_error=parse_error,
        checker_error=checker_error,
        score=score,
        analysis=analysis,
        raw_response=raw_response,
        code=extracted_code,
        latency_ms=latency_ms,
        token_count=None,
    )
