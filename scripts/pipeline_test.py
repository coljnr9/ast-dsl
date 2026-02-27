"""End-to-end pipeline test.

Exercises:
  - alspec.gen_reference.generate_reference()  (full AST API + stdlib docs)
  - pipeline.render()                           (Jinja2 prompt templating)
  - alspec.llm.AsyncLLMClient                  (OpenRouter → Langfuse → LLM)

Run with:
    uv run python scripts/pipeline_test.py
"""

import sys
from pathlib import Path

# Allow running as a plain script from the repo root
sys.path.append(str(Path(__file__).parent.parent))

import asyncio

from alspec.gen_reference import generate_reference
from alspec.llm import AsyncLLMClient
from alspec.result import Err, Ok
from pipeline import render

MODEL = "google/gemini-3-flash-preview"

_DIVIDER = "=" * 72


async def main() -> None:
    # ── 1. Build the full API reference ─────────────────────────────────
    print(_DIVIDER)
    print("STEP 1 — Generating full AST API reference …")
    print(_DIVIDER)

    api_reference = generate_reference()
    print(f"(reference is {len(api_reference):,} characters)\n")

    # ── 2. Render the prompt template ────────────────────────────────────
    print(_DIVIDER)
    print("STEP 2 — Rendering prompt template …")
    print(_DIVIDER)

    prompt = render("full_api_test.md.j2", api_reference=api_reference)
    print(prompt)
    print()

    # ── 3. Send to LLM via AsyncLLMClient (goes through Langfuse) ───────
    print(_DIVIDER)
    print(f"STEP 3 — Sending prompt to model: {MODEL!r} …")
    print(_DIVIDER)

    client_result = AsyncLLMClient.from_env()

    match client_result:
        case Ok(client):
            response_result = await client.generate_text(prompt, model=MODEL)

            match response_result:
                case Ok(content):
                    print("\nLLM RESPONSE:\n")
                    print(content)
                case Err(e):
                    print(f"\nError generating text: {e}", file=sys.stderr)
                    sys.exit(1)

        case Err(e):
            print(f"Failed to initialise LLM client: {e}", file=sys.stderr)
            sys.exit(1)

    print()
    print(_DIVIDER)
    print("Done.")
    print(_DIVIDER)


if __name__ == "__main__":
    asyncio.run(main())
