import argparse
import asyncio
import hashlib
import sys
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

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


def save_specs(results: list, directory: str) -> None:
    """Write each result's generated code to <directory>/<domain_id>.py."""
    out_dir = Path(directory)
    out_dir.mkdir(parents=True, exist_ok=True)
    saved = 0
    for result in results:
        if result.code is None:
            continue
        parts: list[str] = []
        if result.analysis:
            parts.append(f'"""\n{result.analysis}\n"""\n')
        parts.append(result.code)
        path = out_dir / f"{result.domain_id}.py"
        path.write_text("\n".join(parts))
        saved += 1
    print(f"Saved {saved} spec(s) to {out_dir}/")


async def handle_eval(
    domain_ids: list[str] | None,
    models: list[str],
    tier: int | None,
    csv_out: str | None,
    verbose: bool,
    save_specs_dir: str | None,
) -> int:
    from alspec.eval.domains import DOMAINS
    from alspec.eval.harness import EvalResult, EvalRun, run_domain_eval
    from alspec.eval.report import (
        export_csv,
        print_detailed_diagnostics,
        print_feature_coverage,
        print_multi_model_comparison,
        print_summary_table,
    )

    client_res = AsyncLLMClient.from_env()
    match client_res:
        case Err(e):
            print(f"Failed to initialize LLM client: {e}")
            return 1
        case Ok(client):
            pass

    domains = list(DOMAINS)
    if domain_ids:
        domains = [d for d in domains if d.id in domain_ids]
    if tier is not None:
        domains = [d for d in domains if d.complexity == tier]

    if not domains:
        print("No domains matched the criteria.")
        return 1

    ref_text = generate_reference()
    prompt_version = f"v3 (sha256: {hashlib.sha256(ref_text.encode()).hexdigest()[:8]})"

    timestamp = datetime.now().isoformat(timespec="seconds")
    session_id = f"eval-{timestamp}"
    print(f"Langfuse Session ID: {session_id}\n", flush=True)

    results: list[EvalResult] = []

    for model in models:
        for domain in domains:
            print(f"Evaluating {domain.id} on {model}...", flush=True)
            res = await run_domain_eval(
                client, domain, model,
                session_id=session_id,
            )
            results.append(res)

    run = EvalRun(
        timestamp=timestamp,
        models=tuple(models),
        prompt_version=prompt_version,
        results=tuple(results),
    )

    for model in models:
        print_summary_table(run, model, sys.stdout)

    if len(models) > 1:
        print_multi_model_comparison(run, sys.stdout)

    print_feature_coverage(run, sys.stdout)

    # Cache metrics summary
    total_prompt = sum(r.prompt_tokens or 0 for r in results)
    total_cached = sum(r.cached_tokens or 0 for r in results)
    total_cache_write = sum(r.cache_write_tokens or 0 for r in results)
    if total_prompt > 0:
        hit_rate = total_cached / total_prompt
        print(f"\n  Cache Summary")
        print(f"  Total prompt tokens:  {total_prompt:,}")
        print(f"  Cached tokens:        {total_cached:,} ({hit_rate:.1%})")
        print(f"  Cache write tokens:   {total_cache_write:,}")
        if verbose:
            print(f"\n  {'Domain':<25} {'Prompt':>8} {'Cached':>8} {'Hit%':>6}")
            print(f"  {'─'*25} {'─'*8} {'─'*8} {'─'*6}")
            for r in results:
                pt = r.prompt_tokens or 0
                ct = r.cached_tokens or 0
                rate = f"{ct/pt:.0%}" if pt > 0 else "—"
                print(f"  {r.domain_id:<25} {pt:>8} {ct:>8} {rate:>6}")

    if verbose:
        print_detailed_diagnostics(run, sys.stdout)

    if csv_out:
        export_csv(run, csv_out)
        print(f"Exported results to {csv_out}")

    if save_specs_dir:
        save_specs(list(results), save_specs_dir)

    return 0


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

    # Command: eval
    eval_parser = subparsers.add_parser(
        "eval",
        help="Run the evaluation pipeline across domains and models.",
    )
    eval_parser.add_argument(
        "--models",
        type=str,
        default="google/gemini-3-flash-preview",
        help="Comma-separated list of OpenRouter model identifiers.",
    )
    eval_parser.add_argument(
        "--domains",
        type=str,
        help="Comma-separated list of domain IDs. Default: all.",
    )
    eval_parser.add_argument(
        "--tier",
        type=int,
        choices=[1, 2, 3],
        help="Run only domains of a specific complexity tier.",
    )
    eval_parser.add_argument(
        "--csv",
        type=str,
        help="Export results to CSV file.",
    )
    eval_parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Print detailed diagnostics and per-domain cache stats.",
    )
    eval_parser.add_argument(
        "--save-specs",
        type=str,
        metavar="DIR",
        help="Save generated spec code to DIR/<domain-id>.py.",
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
        case "eval":
            return await handle_eval(
                domain_ids=[d.strip() for d in args.domains.split(",")] if args.domains else None,
                models=[m.strip() for m in args.models.split(",")],
                tier=args.tier,
                csv_out=args.csv,
                verbose=args.verbose,
                save_specs_dir=args.save_specs,
            )
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
