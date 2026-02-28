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


async def handle_score(
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
                score = await score_spec(spec, strict=strict, audit=audit)
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


# ---------------------------------------------------------------------------
# DoE subcommands
# ---------------------------------------------------------------------------


async def handle_doe_run(config_path: Path, *, dry_run: bool) -> int:
    """Execute a DoE experiment from a TOML config file."""
    from alspec.eval.doe_config import load_doe_config
    from alspec.eval.doe_design import generate_design_matrix, generate_trials
    from alspec.eval.doe_runner import run_experiment, write_results

    # Resolve project root (alspec/ is inside project root)
    project_root = Path(__file__).parent.parent

    try:
        config = load_doe_config(config_path, project_root=project_root)
    except (ValueError, FileNotFoundError) as e:
        print(f"Config error: {e}", file=sys.stderr)
        return 1

    trials = generate_trials(config)
    n_design_points = len(trials) // config.replicates if config.replicates else len(trials)
    n_trials_total = len(trials) * len(config.domains)

    print(f"Experiment: {config.name}")
    print(f"  Description: {config.description}")
    print(f"  Stage:       {config.stage}")
    print(f"  Model:       {config.model}")
    print(f"  Resolution:  {config.resolution}")
    print(f"  Factors:     {len(config.factors)}  ({', '.join(lbl for lbl, _ in config.factors)})")
    print(f"  Design points (rows): {n_design_points}")
    print(f"  Replicates:  {config.replicates}")
    print(f"  Domains:     {len(config.domains)}")
    print(f"  Total LLM calls: {n_trials_total}  (= {n_design_points} × {config.replicates} × {len(config.domains)})")

    if dry_run:
        print("\n[DRY RUN] Design matrix preview:")
        matrix = generate_design_matrix(config)
        factor_labels = [lbl for lbl, _ in config.factors]
        header = "  trial | " + " | ".join(f" {lbl:>2}" for lbl in factor_labels)
        print(header)
        print("  " + "─" * (len(header) - 2))
        for i in range(min(5, matrix.shape[0])):
            row_str = " | ".join(
                (" -1" if v == -1 else " +1") for v in matrix[i]
            )
            print(f"  {i:>5} | {row_str}")
        if matrix.shape[0] > 5:
            print(f"  ... ({matrix.shape[0] - 5} more rows)")

        print("\n[DRY RUN] First 3 trial configs:")
        for t in trials[:3]:
            chunk_names = [c.name for c in t.chunk_ids]
            print(f"  trial={t.trial_id} rep={t.replicate} chunks={chunk_names}")
            print(f"    hash={t.config_hash[:12]}...")

        print("\n[DRY RUN] No LLM calls made.")
        return 0

    # Real run
    client_res = AsyncLLMClient.from_env()
    match client_res:
        case Err(e):
            print(f"Failed to initialize LLM client: {e}", file=sys.stderr)
            return 1
        case Ok(client):
            pass

    golden_dir = project_root / "golden"
    completed_count = 0

    def progress(done: int, total: int, score: object, elapsed: float = 0.0) -> None:
        nonlocal completed_count
        completed_count = done
        if hasattr(score, "domain") and hasattr(score, "trial_id"):
            print(
                f"  Trial {done:>4}/{total} "
                f"[domain={score.domain:<20} trial={score.trial_id} "  # type: ignore[union-attr]
                f"rep={score.replicate}] "  # type: ignore[union-attr]
                f"health={score.health:.3f}  {elapsed:.1f}s",  # type: ignore[union-attr]
                flush=True,
            )

    print(f"\nRunning {n_trials_total} total LLM calls (max_concurrent={config.max_concurrent})...")
    scores = await run_experiment(
        config, client, golden_dir=golden_dir, progress_cb=progress
    )

    write_results(config, scores, config_path=config_path)

    # Print summary effects
    try:
        from alspec.eval.doe_analyze import analyze_results, print_all_effects_tables

        result = analyze_results(config.output_dir)
        print_all_effects_tables(list(result.main_effects), list(result.interactions))
    except Exception as e:
        print(f"Warning: could not compute effects: {e}", file=sys.stderr)

    print(f"\nDone! Results written to {config.output_dir}")
    return 0


async def handle_doe_analyze(results_dir: Path) -> int:
    """Re-analyze an existing results directory."""
    from alspec.eval.doe_analyze import analyze_results, print_all_effects_tables

    if not results_dir.exists():
        print(f"Results directory not found: {results_dir}", file=sys.stderr)
        return 1

    try:
        result = analyze_results(results_dir)
    except (FileNotFoundError, ValueError) as e:
        print(f"Analysis error: {e}", file=sys.stderr)
        return 1

    print_all_effects_tables(list(result.main_effects), list(result.interactions))

    effects_path = results_dir / "effects.csv"
    print(f"\nFull effects written to {effects_path}")
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

    # Command group: doe
    doe_parser = subparsers.add_parser(
        "doe",
        help="Design-of-Experiments commands for prompt chunk ablation.",
    )
    doe_sub = doe_parser.add_subparsers(dest="doe_command", help="DoE sub-commands")

    # doe run
    doe_run_parser = doe_sub.add_parser(
        "run",
        help="Execute a DoE experiment from a TOML config file.",
    )
    doe_run_parser.add_argument(
        "config",
        metavar="CONFIG.TOML",
        help="Path to the experiment TOML config file.",
    )
    doe_run_parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Print design matrix and trial count without making LLM calls.",
    )

    # doe analyze
    doe_analyze_parser = doe_sub.add_parser(
        "analyze",
        help="Re-analyze an existing results directory (reads scores.jsonl).",
    )
    doe_analyze_parser.add_argument(
        "results_dir",
        metavar="RESULTS_DIR",
        help="Path to the results directory produced by 'doe run'.",
    )

    args = parser.parse_args()

    match args.command:
        case "reference":
            print(generate_reference())
            return 0
        case "score":
            return await handle_score(
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
        case "doe":
            match args.doe_command:
                case "run":
                    return await handle_doe_run(
                        Path(args.config).resolve(),
                        dry_run=args.dry_run,
                    )
                case "analyze":
                    return await handle_doe_analyze(
                        Path(args.results_dir).resolve()
                    )
                case None:
                    doe_parser.print_help()
                    return 1
                case other:
                    print(f"Unknown doe subcommand: {other}", file=sys.stderr)
                    return 1
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
