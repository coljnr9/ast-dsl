import os

from dotenv import load_dotenv
from langfuse import get_client, observe
from langfuse.openai import AsyncOpenAI  # type: ignore[attr-defined]

from alspec.result import Err, Ok, Result

# -----------------
# Client
# -----------------

langfuse = get_client()


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

    @observe(as_type="generation")
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

    @observe(as_type="generation")
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
