import argparse
import asyncio
import sys
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

# Add project root to sys.path so 'alspec' is found when run as a script
sys.path.append(str(Path(__file__).parent.parent))

from alspec.eval.domains import DOMAINS
from alspec.eval.harness import EvalResult, EvalRun, run_domain_eval
from alspec.eval.report import (
    export_csv,
    print_detailed_diagnostics,
    print_feature_coverage,
    print_multi_model_comparison,
    print_summary_table,
)
from alspec.llm import AsyncLLMClient
from alspec.result import Err, Ok


def save_specs(results: list[EvalResult], directory: str) -> None:
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


async def run_evals(
    domain_ids: list[str] | None,
    models: list[str],
    tier: int | None,
    csv_out: str | None,
    verbose: bool,
    use_tool_call: bool,
    save_specs_dir: str | None,
) -> None:
    client_res = AsyncLLMClient.from_env()
    match client_res:
        case Err(e):
            print(f"Failed to initialize LLM client: {e}")
            sys.exit(1)
        case Ok(client):
            pass

    domains = DOMAINS
    if domain_ids:
        domains = [d for d in domains if d.id in domain_ids]
    if tier is not None:
        domains = [d for d in domains if d.complexity == tier]

    if not domains:
        print("No domains matched the criteria.")
        sys.exit(1)

    import hashlib

    from alspec.gen_reference import generate_reference

    ref_text = generate_reference()
    prompt_version = f"v3 (sha256: {hashlib.sha256(ref_text.encode()).hexdigest()[:8]})"

    timestamp = datetime.now().isoformat(timespec="seconds")
    session_id = f"eval-{timestamp}"
    print(f"Langfuse Session ID: {session_id}\n", flush=True)

    results = []

    for model in models:
        for domain in domains:
            print(f"Evaluating {domain.id} on {model}...", flush=True)
            res = await run_domain_eval(
                client, domain, model,
                session_id=session_id,
                use_tool_call=use_tool_call,
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

    if verbose:
        print_detailed_diagnostics(run, sys.stdout)

    if csv_out:
        export_csv(run, csv_out)
        print(f"Exported results to {csv_out}")

    if save_specs_dir:
        save_specs(list(results), save_specs_dir)


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run alspec evaluations.")
    parser.add_argument(
        "--domains",
        type=str,
        help="Comma-separated list of domain IDs to run.",
    )
    parser.add_argument(
        "--models",
        type=str,
        default="google/gemini-3-flash-preview",
        help="Comma-separated list of OpenRouter model instances.",
    )
    parser.add_argument(
        "--tier",
        type=int,
        choices=[1, 2, 3],
        help="Run only domains of a specific complexity tier.",
    )
    parser.add_argument(
        "--csv",
        type=str,
        help="Export results to CSV file.",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Print detailed diagnostics.",
    )
    parser.add_argument(
        "--no-tool-call",
        action="store_true",
        default=False,
        help=(
            "Disable tool-call structured output and fall back to markdown "
            "code-fence extraction. Use when the target model does not support "
            "tool calling via OpenRouter."
        ),
    )
    parser.add_argument(
        "--save-specs",
        type=str,
        metavar="DIR",
        help=(
            "Save each domain's generated spec code to DIR/<domain-id>.py. "
            "The directory is created if it does not exist. Only results with "
            "successfully extracted code are written."
        ),
    )

    args = parser.parse_args(argv)

    domain_ids = [d.strip() for d in args.domains.split(",")] if args.domains else None
    models = [m.strip() for m in args.models.split(",")]

    asyncio.run(
        run_evals(
            domain_ids=domain_ids,
            models=models,
            tier=args.tier,
            csv_out=args.csv,
            verbose=args.verbose,
            use_tool_call=not args.no_tool_call,
            save_specs_dir=args.save_specs,
        )
    )


if __name__ == "__main__":
    main()
