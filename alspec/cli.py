import argparse
import asyncio
import sys
from collections.abc import Sequence

from alspec.gen_reference import generate_reference
from alspec.load import load_spec_from_file
from alspec.llm import AsyncLLMClient
from alspec.result import Err, Ok
from alspec.score import score_spec
from alspec.score_report import ScoreResult, print_score_diagnostics, print_score_table
from alspec.spec import Spec


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


def handle_score(
    files: Sequence[str],
    *,
    verbose: bool,
    audit: bool,
    strict: bool,
) -> int:
    """Load, score, and report on a list of spec .py files."""
    results: list[ScoreResult] = []

    for path in files:
        if not path.endswith(".py"):
            continue

        spec_or_err = load_spec_from_file(path)
        match spec_or_err:
            case str(err):
                results.append(
                    ScoreResult(
                        file_path=path,
                        spec_name="",
                        success=False,
                        error=err,
                        score=None,
                    )
                )
            case Spec() as spec:
                score = score_spec(spec, strict=strict, audit=audit)
                results.append(
                    ScoreResult(
                        file_path=path,
                        spec_name=spec.name,
                        success=True,
                        error=None,
                        score=score,
                    )
                )

    print_score_table(results, sys.stdout)

    if verbose:
        print_score_diagnostics(results, sys.stdout)

    any_failure = any(not r.success for r in results)
    return 1 if any_failure else 0


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

    # Command: score
    score_parser = subparsers.add_parser(
        "score",
        help="Load one or more spec .py files and print a scoring summary table.",
    )
    score_parser.add_argument(
        "files",
        nargs="+",
        metavar="FILE",
        help="Spec .py file(s) to score. Shell globs are expanded by your shell.",
    )
    score_parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        default=False,
        help="Print per-file diagnostics after the table.",
    )
    score_parser.add_argument(
        "--audit",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Run adequacy audit checks (default: on).",
    )
    score_parser.add_argument(
        "--strict",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Strict scoring: health is 0 or 1 (default: smooth degradation).",
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
        case "score":
            return handle_score(
                args.files,
                verbose=args.verbose,
                audit=args.audit,
                strict=args.strict,
            )
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
