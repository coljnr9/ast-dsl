import json
import os

from dotenv import load_dotenv

# load_dotenv MUST run before get_client() so the LANGFUSE_* env vars
# are visible when the Langfuse client initializes.
load_dotenv()

from langfuse.openai import AsyncOpenAI  # type: ignore[attr-defined]

from alspec.result import Err, Ok, Result

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

# tool_choice that forces the model to call submit_spec and nothing else
_TOOL_CHOICE: dict[str, object] = {"type": "function", "function": {"name": "submit_spec"}}


class AsyncLLMClient:
    """An asynchronous LLM client that wraps the OpenAI SDK for OpenRouter."""

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

    async def generate_text(
        self, prompt: str, model: str = "meta-llama/llama-3.1-8b-instruct"
    ) -> Result[str, Exception]:
        """Generates text from the given prompt using the specified model."""
        try:
            response = await self._client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
            )

            match response.choices:
                case [choice, *_]:
                    match choice.message.content:
                        case str(content):
                            return Ok(content)
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

    async def generate_messages(
        self,
        messages: list[dict[str, str]],
        model: str = "meta-llama/llama-3.1-8b-instruct",
    ) -> Result[str, Exception]:
        """Generates text from a list of messages using the specified model.

        The ``@observe(as_type="generation")`` decorator creates a proper child
        span in the Langfuse trace hierarchy. When called from inside an
        ``@observe()``-decorated function, the generation is automatically nested
        under the parent trace — no manual ``trace_id`` threading required.
        """
        try:
            response = await self._client.chat.completions.create(
                model=model,
                messages=messages,  # type: ignore[arg-type]
            )

            match response.choices:
                case [choice, *_]:
                    match choice.message.content:
                        case str(content):
                            return Ok(content)
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

    async def generate_with_tool_call(
        self,
        messages: list[dict[str, str]],
        model: str = "meta-llama/llama-3.1-8b-instruct",
    ) -> Result[tuple[str, str], Exception]:
        """Call the model with the submit_spec tool and return (analysis, code).

        Forces the model to call ``submit_spec`` via ``tool_choice``, which
        eliminates brittle code-fence extraction and requires the model to show
        its reasoning in the ``analysis`` field before writing code.

        Returns ``Ok((analysis, code))`` on success or ``Err(...)`` on failure.
        The error message is a human-readable string suitable for storing in
        ``EvalResult.parse_error``.
        """
        try:
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

        # Validate tool_calls presence
        tool_calls = choice.message.tool_calls
        match tool_calls:
            case None | []:
                return Err(RuntimeError("Model did not use submit_spec tool"))
            case [call, *_]:
                pass

        # Parse JSON arguments
        try:
            args: dict[str, object] = json.loads(call.function.arguments)
        except Exception as e:
            return Err(RuntimeError(f"Failed to parse tool call arguments: {e}"))

        analysis = args.get("analysis")
        code = args.get("code")

        match (analysis, code):
            case (str(a), str(c)):
                return Ok((a, c))
            case _:
                return Err(
                    RuntimeError(
                        "submit_spec arguments missing 'analysis' or 'code' fields"
                    )
                )
