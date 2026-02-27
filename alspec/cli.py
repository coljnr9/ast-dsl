import argparse
import asyncio
import sys

from alspec.examples import main as run_examples
from alspec.gen_reference import generate_reference
from alspec.llm import AsyncLLMClient
from alspec.result import Err, Ok


async def handle_generate(prompt: str) -> int:
    client_result = AsyncLLMClient.from_env()
    match client_result:
        case Ok(client):
            pass
        case Err(e):
            print(f"Error initializing LLM client: {e}", file=sys.stderr)
            return 1

    print("Generating reference documentation to use as context...", file=sys.stderr)
    reference = generate_reference()

    full_prompt = (
        f"You are an expert at writing many-sorted algebraic specifications.\n"
        f"Using the language reference provided below, write a spec for the following prompt:\n"
        f"PROMPT: {prompt}\n\n"
        f"LANGUAGE_REFERENCE:\n{reference}\n\n"
        f"Respond ONLY with valid Python code that returns the `Spec` object as described in the reference, nothing else. Do not format with markdown blocks, just the code."
    )

    print("Sending prompt to LLM...", file=sys.stderr)
    response_result = await client.generate_text(full_prompt)

    match response_result:
        case Ok(code):
            print(code)
            return 0
        case Err(e):
            print(f"Error generating text: {e}", file=sys.stderr)
            return 1


async def async_main() -> int:
    parser = argparse.ArgumentParser(
        prog="alspec",
        description="CLI for the many-sorted algebraic specification DSL",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Command: reference
    subparsers.add_parser(
        "reference",
        help="Generate and print the complete language reference (Markdown).",
    )

    # Command: examples
    subparsers.add_parser(
        "examples",
        help="Run textbook algebraic specification examples and print them as JSON.",
    )

    # Command: generate
    generate_parser = subparsers.add_parser(
        "generate", help="Generate a new spec from a prompt using an LLM."
    )
    generate_parser.add_argument(
        "--prompt", required=True, help="The desired specification description."
    )

    args = parser.parse_args()

    match args.command:
        case "reference":
            print(generate_reference())
            return 0
        case "examples":
            run_examples()
            return 0
        case "generate":
            return await handle_generate(args.prompt)
        case None:
            parser.print_help()
            return 1
        case _:
            print(f"Unknown command: {args.command}", file=sys.stderr)
            parser.print_help()
            return 1


def main() -> int:
    """Synchronous entry point for the console script."""
    try:
        return asyncio.run(async_main())
    except KeyboardInterrupt:
        print("\nOperation cancelled by user.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
