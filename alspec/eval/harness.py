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
    analysis: str | None  # The model's chain-of-thought (from submit_spec tool)
    code: str | None      # Extracted / tool-provided code
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
    """Extract Python code from a markdown block. Fallback for non-tool-call runs."""
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
    *,
    session_id: str | None = None,
    use_tool_call: bool = True,
) -> EvalResult:
    """Run extraction and evaluation for a single domain and model.

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
    messages = build_prompt(domain, use_tool_call=use_tool_call)
    fn_name = domain.id.replace("-", "_") + "_spec"
    model_short = model.split("/")[-1]
    trace_name = f"eval/{domain.id}/{model_short}"

    parse_error: str | None = None
    checker_error: str | None = None
    analysis: str | None = None
    extracted_code: str | None = None
    success = False
    score = None
    start_time = time.time()

    with propagate_attributes(
        trace_name=trace_name,
        session_id=session_id,
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
        # Set trace Input to the human-readable domain description so the
        # Langfuse UI shows what task this eval run was solving.
        langfuse.update_current_trace(input=domain.description)

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
                    extracted_code = extract_code(content)
                    match extracted_code:
                        case None:
                            parse_error = "Could not extract code from response"
                        case _:
                            pass

        if extracted_code is not None and parse_error is None:
            spec_or_err = execute_spec_code(extracted_code, fn_name)

            match spec_or_err:
                case str(err):
                    checker_error = err
                case Spec() as s:
                    success = True
                    score = score_spec(s, strict=False, audit=True)

        # Set trace Output to a concise result summary — visible at the trace
        # list level in the Langfuse UI without clicking into the trace.
        if score is not None:
            # Count dead-symbol warnings before building the output dict.
            unconstrained_count = sum(
                1 for d in score.diagnostics
                if d.check in ("unconstrained_fn", "unconstrained_pred", "orphan_sort")
            )
            langfuse.update_current_trace(
                output={
                    "success": True,
                    "health": round(score.health, 3),
                    "well_formed": score.well_formed,
                    "unconstrained_symbols": unconstrained_count,
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
        else:
            error_msg = parse_error or checker_error or "unknown failure"
            langfuse.update_current_trace(
                output={"success": False, "error": error_msg}
            )
            # Log hard zeros so failed traces are visible in score-based filters.
            langfuse.score_current_trace(
                name="spec_health", value=0.0, comment=error_msg
            )
            langfuse.score_current_trace(name="well_formed", value=0.0)

    langfuse.flush()

    latency_ms = int((time.time() - start_time) * 1000)

    return EvalResult(
        domain_id=domain.id,
        model=model,
        success=success,
        parse_error=parse_error,
        checker_error=checker_error,
        score=score,
        analysis=analysis,
        code=extracted_code,
        latency_ms=latency_ms,
        token_count=None,
    )
