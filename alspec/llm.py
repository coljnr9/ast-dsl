import json
import os
from dataclasses import dataclass
from typing import Any

from dotenv import load_dotenv

# load_dotenv MUST run before get_client() so the LANGFUSE_* env vars
# are visible when the Langfuse client initializes.
load_dotenv()

from langfuse import propagate_attributes
from langfuse.openai import AsyncOpenAI  # type: ignore[attr-defined]

from alspec.result import Err, Ok, Result

_TOOL_CHOICE_AUTO_MODELS = ["inception/mercury-2"]
# ---------------------------------------------------------------------------
# Token usage metrics
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class UsageInfo:
    """Token usage metrics extracted from an OpenRouter response."""

    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cached_tokens: int
    cache_write_tokens: int

    @property
    def cache_hit_rate(self) -> float:
        """Fraction of prompt tokens served from cache."""
        if self.prompt_tokens == 0:
            return 0.0
        return self.cached_tokens / self.prompt_tokens


def _extract_usage(response: object) -> UsageInfo | None:
    """Extract token usage from an OpenAI-style response."""
    usage = getattr(response, "usage", None)
    if usage is None:
        return None
    details = getattr(usage, "prompt_tokens_details", None)
    cached = getattr(details, "cached_tokens", 0) or 0
    cache_write = getattr(details, "cache_write_tokens", 0) or 0
    return UsageInfo(
        prompt_tokens=usage.prompt_tokens or 0,
        completion_tokens=usage.completion_tokens or 0,
        total_tokens=usage.total_tokens or 0,
        cached_tokens=cached,
        cache_write_tokens=cache_write,
    )


# ---------------------------------------------------------------------------
# Tool schema — forces the model to emit structured analysis + code
# ---------------------------------------------------------------------------

SUBMIT_SPEC_TOOL: dict[str, object] = {
    "type": "function",
    "function": {
        "name": "submit_spec",
        "description": (
            "Submit the completed algebraic specification. "
            "The analysis should show your axiom design reasoning: "
            "walk through each obligation cell, note which pattern "
            "applies, and verify completeness against the provided table."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "analysis": {
                    "type": "string",
                    "description": (
                        "Your axiom design reasoning: for each obligation "
                        "cell, note which pattern applies (key dispatch, "
                        "preservation, selector extract, undefinedness, etc.), "
                        "identify guard polarity decisions, and verify "
                        "completeness against the provided obligation table. "
                        "Do NOT re-derive the signature or obligation table."
                    ),
                },
                "code": {
                    "type": "string",
                    "description": (
                        "Python code that assigns sig, axioms, and "
                        "spec = Spec(...) at top level. No function wrapper. "
                        "Must implement every row of the obligation table."
                    ),
                },
            },
            "required": ["analysis", "code"],
        },
    },
}

SUBMIT_SIGNATURE_TOOL: dict[str, object] = {
    "type": "function",
    "function": {
        "name": "submit_signature",
        "description": (
            "Submit the signature for an algebraic specification. "
            "A later stage will generate axioms from this signature. "
            "The analysis should show your reasoning: sort identification, "
            "function classification, and generated sort identification."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "analysis": {
                    "type": "string",
                    "description": (
                        "Your complete analysis: identify sorts, classify "
                        "functions, determine generated sorts and their "
                        "constructors, note design decisions."
                    ),
                },
                "code": {
                    "type": "string",
                    "description": (
                        "Python code that assigns sig = Signature(...) at "
                        "top level. No function wrapper. Include "
                        "generated_sorts inside the Signature constructor "
                        "using GeneratedSortInfo objects."
                    ),
                },
            },
            "required": ["analysis", "code"],
        },
    },
}

SUBMIT_ANALYSIS_TOOL: dict[str, object] = {
    "type": "function",
    "function": {
        "name": "submit_analysis",
        "description": (
            "Submit a structured domain analysis. The analysis identifies "
            "entities, their lifecycles, operations, preconditions, postconditions, "
            "what each operation preserves, and key invariants."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "analysis": {
                    "type": "string",
                    "description": (
                        "The structured domain analysis covering: entities and their data, "
                        "operations with preconditions and postconditions, what each operation "
                        "changes and what it preserves, relationships between entities, "
                        "and system invariants."
                    ),
                },
            },
            "required": ["analysis"],
        },
    },
}

SUBMIT_AXIOM_FILLS_TOOL: dict[str, object] = {
    "type": "function",
    "function": {
        "name": "submit_axiom_fills",
        "description": (
            "Submit formula fills for the remaining obligation table cells. "
            "Each fill is a Python DSL expression that becomes the formula "
            "argument to Axiom(label, formula). Multiple fills may target "
            "the same obligation cell (e.g., a priority chain with multiple "
            "guarded implications for a single observer x constructor pair)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "analysis": {
                    "type": "string",
                    "description": (
                        "Your axiom design reasoning: for each obligation "
                        "cell, note which pattern applies, identify guard "
                        "polarity decisions, and verify completeness against "
                        "the provided obligation table. "
                        "Do NOT re-derive the signature or obligation table."
                    ),
                },
                "variables": {
                    "type": "array",
                    "description": (
                        "Declare all variables used in your axiom formulas. "
                        "Each variable has a name and sort. These become "
                        "var(name, sort) declarations in the final spec. "
                        "Include every variable referenced in any formula."
                    ),
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {
                                "type": "string",
                                "description": "Variable name, e.g. 's', 'e2', 'key'",
                            },
                            "sort": {
                                "type": "string",
                                "description": "Sort name matching a sort in the signature, e.g. 'Stack', 'Elem'",
                            },
                        },
                        "required": ["name", "sort"],
                    },
                },
                "fills": {
                    "type": "array",
                    "description": (
                        "One entry per axiom. Multiple entries may target the "
                        "same obligation cell (e.g., 5 entries for get_cv x step "
                        "covering reset/load/count-up/count-down/preserve). "
                        "Use the variable names you declared in the variables field."
                    ),
                    "items": {
                        "type": "object",
                        "properties": {
                            "label": {
                                "type": "string",
                                "description": (
                                    "Axiom label, e.g. 'get_cv_step_reset'. "
                                    "Use snake_case: observer_constructor_variant."
                                ),
                            },
                            "formula": {
                                "type": "string",
                                "description": (
                                    "Complete Python DSL expression for the axiom formula. "
                                    "This becomes the second argument to Axiom(label, formula). "
                                    "Use the exact helper functions from the import block. "
                                    "Example: forall([s, cu], eq(app(\"get_cv\", app(\"init\")), const(\"zero\")))"
                                ),
                            },
                        },
                        "required": ["label", "formula"],
                    },
                },
            },
            "required": ["analysis", "variables", "fills"],
        },
    },
}

_TOOL_REGISTRY: dict[str, dict[str, object]] = {
    "submit_spec": SUBMIT_SPEC_TOOL,
    "submit_signature": SUBMIT_SIGNATURE_TOOL,
    "submit_analysis": SUBMIT_ANALYSIS_TOOL,
    "submit_axiom_fills": SUBMIT_AXIOM_FILLS_TOOL,
}


class AsyncLLMClient:
    """An asynchronous LLM client that wraps the OpenAI SDK for OpenRouter.

    Uses ``from langfuse.openai import AsyncOpenAI`` as the drop-in replacement,
    which automatically instruments every ``completions.create()`` call as a
    Langfuse generation, capturing input messages and output text. No manual
    tracing code is needed in this class.
    """

    def __init__(self, api_key: str, session_id: str | None = None):
        self._client = AsyncOpenAI(
            api_key=api_key,
            base_url="https://openrouter.ai/api/v1",
        )
        self._session_id = session_id

    @classmethod
    def from_env(cls) -> Result["AsyncLLMClient", Exception]:
        """Creates a client by loading the OPENROUTER_API_KEY from the .env file."""
        load_dotenv()
        api_key = os.getenv("OPENROUTER_API_KEY")

        match api_key:
            case str(key) if key.strip():
                return Ok(cls(api_key=key.strip()))
            case _:
                return Err(
                    ValueError("OPENROUTER_API_KEY not found or empty in environment.")
                )

    async def generate_with_tool_call(
        self,
        messages: list[dict[str, str]],
        model: str = "meta-llama/llama-3.1-8b-instruct",
        tool_name: str = "submit_spec",
        name: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Result[tuple[str, str, UsageInfo | None], Exception]:
        """Call the model with the submit_spec tool and return (analysis, code, usage).

        Forces the model to call ``submit_spec`` via ``tool_choice``, which
        eliminates brittle code-fence extraction and requires the model to show
        its reasoning in the ``analysis`` field before writing code.

        The ``langfuse.openai`` wrapper automatically captures this call as a
        generation span (input messages + tool response output) nested under
        whatever trace is active in the caller.

        Returns ``Ok((analysis, code, usage))`` on success or ``Err(...)`` on failure.
        """
        try:
            messages = self._prepare_messages(messages)
            tool_schema = _TOOL_REGISTRY[tool_name]
            if model in _TOOL_CHOICE_AUTO_MODELS:
                tool_choice: str | dict[str, object] = "auto"
            else:
                tool_choice: str | dict[str, object] = {
                    "type": "function",
                    "function": {"name": tool_name},
                }
            extra_body: dict[str, object] = {}
            match self._session_id:
                case str(sid):
                    extra_body["langfuse_session_id"] = sid
                case _:
                    pass

            with propagate_attributes(session_id=self._session_id, metadata=metadata):
                kwargs: dict[str, Any] = {
                    "model": model,
                    "messages": messages,
                    "tools": [tool_schema],
                    "tool_choice": tool_choice,
                    "extra_body": extra_body,
                }
                match name:
                    case str(n):
                        kwargs["name"] = n
                    case _:
                        pass

                response = await self._client.chat.completions.create(**kwargs)  # type: ignore[call-overload]

            match response.choices:
                case []:
                    return Err(RuntimeError("Model returned no choices."))
                case [choice, *_]:
                    pass
                case _:
                    return Err(RuntimeError("Unexpected response format from model."))

        except Exception as e:
            return Err(e)

        usage = _extract_usage(response)

        tool_calls = choice.message.tool_calls
        match tool_calls:
            case None | []:
                return Err(RuntimeError("Model did not use submit_spec tool"))
            case [call, *_]:
                pass

        try:
            args: dict[str, object] = json.loads(call.function.arguments)
        except Exception as e:
            return Err(RuntimeError(f"Failed to parse tool call arguments: {e}"))

        analysis = args.get("analysis")
        code = args.get("code")

        match (analysis, code):
            case (str(a), str(c)):
                return Ok((a, c, usage))
            case _:
                return Err(
                    RuntimeError(
                        f"{tool_name} arguments missing 'analysis' or 'code' fields"
                    )
                )

    async def generate_with_analysis_tool(
        self,
        messages: list[dict[str, str]],
        model: str = "meta-llama/llama-3.1-8b-instruct",
        name: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Result[tuple[str, UsageInfo | None], Exception]:
        """Call the model with submit_analysis tool. Returns (analysis_text, usage).

        Similar to generate_with_tool_call but uses SUBMIT_ANALYSIS_TOOL
        and only extracts the 'analysis' field (no 'code').
        """
        try:
            messages = self._prepare_messages(messages)
            tool_schema = _TOOL_REGISTRY["submit_analysis"]
            if model in _TOOL_CHOICE_AUTO_MODELS:
                tool_choice: str | dict[str, object] = "auto"
            else:
                tool_choice: str | dict[str, object] = {
                    "type": "function",
                    "function": {"name": "submit_analysis"},
                }
            extra_body: dict[str, object] = {}
            match self._session_id:
                case str(sid):
                    extra_body["langfuse_session_id"] = sid
                case _:
                    pass

            with propagate_attributes(session_id=self._session_id, metadata=metadata):
                kwargs: dict[str, Any] = {
                    "model": model,
                    "messages": messages,
                    "tools": [tool_schema],
                    "tool_choice": tool_choice,
                    "extra_body": extra_body,
                }
                match name:
                    case str(n):
                        kwargs["name"] = n
                    case _:
                        pass

                response = await self._client.chat.completions.create(**kwargs)  # type: ignore[call-overload]

            match response.choices:
                case []:
                    return Err(RuntimeError("Model returned no choices."))
                case [choice, *_]:
                    pass
                case _:
                    return Err(RuntimeError("Unexpected response format from model."))

        except Exception as e:
            return Err(e)

        usage = _extract_usage(response)

        tool_calls = choice.message.tool_calls
        match tool_calls:
            case None | []:
                return Err(RuntimeError("Model did not use submit_analysis tool"))
            case [call, *_]:
                pass

        try:
            args: dict[str, object] = json.loads(call.function.arguments)
        except Exception as e:
            return Err(RuntimeError(f"Failed to parse tool call arguments: {e}"))

        analysis = args.get("analysis")
        match analysis:
            case str(a):
                return Ok((a, usage))
            case _:
                return Err(
                    RuntimeError("submit_analysis arguments missing 'analysis' field")
                )
    async def generate_with_fills_tool(
        self,
        messages: list[dict[str, str]],
        model: str = "meta-llama/llama-3.1-8b-instruct",
        name: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Result[tuple[str, list[dict[str, str]], list[dict[str, str]], UsageInfo | None], Exception]:
        """Call the model with submit_axiom_fills and return (analysis, fills, usage).

        fills is a list of dicts, each with 'label' and 'formula' string keys.
        """
        try:
            messages = self._prepare_messages(messages)
            tool_schema = _TOOL_REGISTRY["submit_axiom_fills"]
            if model in _TOOL_CHOICE_AUTO_MODELS:
                tool_choice: str | dict[str, object] = "auto"
            else:
                tool_choice: str | dict[str, object] = {
                    "type": "function",
                    "function": {"name": "submit_axiom_fills"},
                }
            extra_body: dict[str, object] = {}
            match self._session_id:
                case str(sid):
                    extra_body["langfuse_session_id"] = sid
                case _:
                    pass

            with propagate_attributes(session_id=self._session_id, metadata=metadata):
                kwargs: dict[str, Any] = {
                    "model": model,
                    "messages": messages,
                    "tools": [tool_schema],
                    "tool_choice": tool_choice,
                    "extra_body": extra_body,
                }
                match name:
                    case str(n):
                        kwargs["name"] = n
                    case _:
                        pass

                response = await self._client.chat.completions.create(**kwargs)  # type: ignore[call-overload]

            match response.choices:
                case []:
                    return Err(RuntimeError("Model returned no choices."))
                case [choice, *_]:
                    pass
                case _:
                    return Err(RuntimeError("Unexpected response format from model."))

        except Exception as e:
            return Err(e)

        usage = _extract_usage(response)

        tool_calls = choice.message.tool_calls
        match tool_calls:
            case None | []:
                return Err(RuntimeError("Model did not use submit_axiom_fills tool"))
            case [call, *_]:
                pass

        try:
            args: dict[str, object] = json.loads(call.function.arguments)
        except Exception as e:
            return Err(RuntimeError(f"Failed to parse tool call arguments: {e}"))

        analysis = args.get("analysis")
        variables = args.get("variables")
        fills = args.get("fills")

        match (analysis, variables, fills):
            case (str(a), list(v), list(f)):
                # Validate variables structure
                validated_vars = []
                for entry in v:
                    if not isinstance(entry, dict) or "name" not in entry or "sort" not in entry:
                        return Err(RuntimeError(f"Malformed variable entry: {entry}"))
                    validated_vars.append({
                        "name": str(entry["name"]),
                        "sort": str(entry["sort"]),
                    })
                # Validate fills structure
                validated_fills = []
                for entry in f:
                    if not isinstance(entry, dict) or "label" not in entry or "formula" not in entry:
                         return Err(RuntimeError(f"Malformed fill entry: {entry}"))
                    validated_fills.append({
                        "label": str(entry["label"]),
                        "formula": str(entry["formula"])
                    })
                return Ok((a, validated_vars, validated_fills, usage))
            case _:
                return Err(
                    RuntimeError("submit_axiom_fills arguments missing 'analysis', 'variables', or 'fills' fields")
                )

    async def generate_text(
        self,
        prompt: str,
        model: str = "meta-llama/llama-3.1-8b-instruct",
        name: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Result[str, Exception]:
        """Simple wrapper for plain text generation from a single prompt string."""
        messages: list[dict[str, str]] = [{"role": "user", "content": prompt}]
        result = await self.generate_messages(
            messages=messages, model=model, name=name, metadata=metadata
        )
        match result:
            case Ok((content, _usage)):
                return Ok(content)
            case Err(e):
                return Err(e)

    async def generate_messages(
        self,
        messages: list[dict[str, str]],
        model: str = "meta-llama/llama-3.1-8b-instruct",
        name: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Result[tuple[str, UsageInfo | None], Exception]:
        """Fallback: plain chat completion without tool forcing.

        Used only when ``use_tool_call=False`` is passed to ``run_domain_eval``.
        Output is raw text that requires code-fence extraction. Prefer
        ``generate_with_tool_call`` for all normal eval runs.

        The ``langfuse.openai`` wrapper automatically captures this call as a
        generation span nested under the active trace.
        """
        try:
            messages = self._prepare_messages(messages)
            extra_body: dict[str, object] = {}
            match self._session_id:
                case str(sid):
                    extra_body["langfuse_session_id"] = sid
                case _:
                    pass

            with propagate_attributes(session_id=self._session_id, metadata=metadata):
                kwargs: dict[str, Any] = {
                    "model": model,
                    "messages": messages,  # type: ignore[arg-type]
                    "extra_body": extra_body,
                }
                match name:
                    case str(n):
                        kwargs["name"] = n
                    case _:
                        pass

                response = await self._client.chat.completions.create(**kwargs)

            match response.choices:
                case [choice, *_]:
                    match choice.message.content:
                        case str(content):
                            return Ok((content, _extract_usage(response)))
                        case _:
                            return Err(
                                RuntimeError("Model response content was not a string.")
                            )
                case []:
                    return Err(RuntimeError("Model returned no choices."))
                case _:
                    return Err(RuntimeError("Unexpected response format from model."))

        except Exception as e:
            return Err(e)

    def _prepare_messages(self, messages: list[dict[str, str]]) -> list[dict]:
        """Convert messages to multipart format with cache_control on system messages."""
        prepared = []
        for msg in messages:
            if msg["role"] == "system":
                prepared.append(
                    {
                        "role": "system",
                        "content": [
                            {
                                "type": "text",
                                "text": msg["content"],
                                "cache_control": {"type": "ephemeral"},
                            }
                        ],
                    }
                )
            else:
                prepared.append(msg)
        return prepared
