import json
import os
from dataclasses import dataclass

from dotenv import load_dotenv

# load_dotenv MUST run before get_client() so the LANGFUSE_* env vars
# are visible when the Langfuse client initializes.
load_dotenv()

from langfuse.openai import AsyncOpenAI  # type: ignore[attr-defined]

from alspec.result import Err, Ok, Result

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
            "You MUST complete the full analysis before writing code. "
            "The analysis should show your reasoning: sort classification, "
            "function roles, the complete axiom obligation table, and a "
            "completeness count."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "analysis": {
                    "type": "string",
                    "description": (
                        "Your complete analysis: identify sorts, classify "
                        "functions as constructor/observer/uninterpreted, "
                        "build the axiom obligation table, note tricky cases "
                        "and design decisions, count expected axioms."
                    ),
                },
                "code": {
                    "type": "string",
                    "description": (
                        "Python code containing a single function that returns "
                        "a Spec. Must implement every row of the obligation "
                        "table from your analysis."
                    ),
                },
            },
            "required": ["analysis", "code"],
        },
    },
}

_TOOL_CHOICE: dict[str, object] = {
    "type": "function",
    "function": {"name": "submit_spec"},
}


class AsyncLLMClient:
    """An asynchronous LLM client that wraps the OpenAI SDK for OpenRouter.

    Uses ``from langfuse.openai import AsyncOpenAI`` as the drop-in replacement,
    which automatically instruments every ``completions.create()`` call as a
    Langfuse generation, capturing input messages and output text. No manual
    tracing code is needed in this class.
    """

    def __init__(self, api_key: str):
        self._client = AsyncOpenAI(
            api_key=api_key,
            base_url="https://openrouter.ai/api/v1",
        )

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
            response = await self._client.chat.completions.create(  # type: ignore[call-overload]
                model=model,
                messages=messages,
                tools=[SUBMIT_SPEC_TOOL],
                tool_choice=_TOOL_CHOICE,
            )

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
                        "submit_spec arguments missing 'analysis' or 'code' fields"
                    )
                )

    async def generate_messages(
        self,
        messages: list[dict[str, str]],
        model: str = "meta-llama/llama-3.1-8b-instruct",
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
            response = await self._client.chat.completions.create(
                model=model,
                messages=messages,  # type: ignore[arg-type]
            )

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
