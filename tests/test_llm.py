# mypy: ignore-errors
import pytest

from alspec.llm import AsyncLLMClient
from alspec.result import Err, Ok


class MockChoice:
    def __init__(self, content):
        self.message = type("MockMessage", (), {"content": content})


class MockChatCompletions:
    def __init__(self, choices):
        self._choices = choices

    async def create(self, **kwargs):
        return type("MockResponse", (), {"choices": self._choices})


class MockChat:
    def __init__(self, choices):
        self.completions = MockChatCompletions(choices)


class MockAsyncOpenAI:
    def __init__(self, choices):
        self.chat = MockChat(choices)


@pytest.mark.asyncio
async def test_llm_client_success() -> None:
    client = AsyncLLMClient("fake_key")
    client._client = MockAsyncOpenAI([MockChoice("Hello, world!")])

    messages = [{"role": "user", "content": "Say hello"}]
    result = await client.generate_messages(messages)

    match result:
        case Ok(content):
            assert content == "Hello, world!"
        case Err(e):
            pytest.fail(f"Expected Ok, got Err: {e}")


@pytest.mark.asyncio
async def test_llm_client_empty_choices() -> None:
    client = AsyncLLMClient("fake_key")
    client._client = MockAsyncOpenAI([])

    messages = [{"role": "user", "content": "Say hello"}]
    result = await client.generate_messages(messages)

    match result:
        case Ok(content):
            pytest.fail(f"Expected Err, got Ok: {content}")
        case Err(e):
            assert isinstance(e, RuntimeError)
            assert str(e) == "Model returned no choices."


@pytest.mark.asyncio
async def test_llm_client_exception_handling() -> None:
    client = AsyncLLMClient("fake_key")

    class BrokenMockChatCompletions:
        async def create(self, **kwargs):
            raise ConnectionError("API is down")

    client._client.chat.completions = BrokenMockChatCompletions()

    messages = [{"role": "user", "content": "Say hello"}]
    result = await client.generate_messages(messages)

    match result:
        case Ok(content):
            pytest.fail(f"Expected Err, got Ok: {content}")
        case Err(e):
            assert isinstance(e, ConnectionError)
            assert str(e) == "API is down"
