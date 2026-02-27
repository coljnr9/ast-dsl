import sys
from pathlib import Path

# Add project root to sys.path so 'alspec' and 'pipeline' are found when run as a script
sys.path.append(str(Path(__file__).parent.parent))

import asyncio

from alspec.llm import AsyncLLMClient
from alspec.result import Err, Ok


async def main() -> None:
    print("Initializing AsyncLLMClient from environment...")
    client_result = AsyncLLMClient.from_env()

    match client_result:
        case Ok(client):
            print("Successfully initialized client. Generating text...")
            # We explicitly handle the error so we do not unwrap!
            response_result = await client.generate_text(
                "What is 2 + 2?", model="meta-llama/llama-3.1-8b-instruct"
            )

            match response_result:
                case Ok(content):
                    print(f"\\nResponse:\\n{content}")
                case Err(e):
                    print(f"\\nError generating text: {e}")

        case Err(e):
            print(f"Failed to initialize client: {e}")


if __name__ == "__main__":
    asyncio.run(main())
