import os

from dotenv import load_dotenv
from langfuse.openai import AsyncOpenAI  # type: ignore[attr-defined]

from alspec.result import Err, Ok, Result

# -----------------
# Client
# -----------------


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
            response = await self._client.chat.completions.create(  # type: ignore[call-overload]
                name="generate_text",
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
        """Generates text from a list of messages using the specified model."""
        try:
            response = await self._client.chat.completions.create(  # type: ignore[call-overload]
                name="generate_messages",
                model=model,
                messages=messages,
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
