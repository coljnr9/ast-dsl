"""Run the two-stage pipeline on selected domains.

Usage:
    uv run python scripts/run_pipeline.py --model MODEL --domains counter,stack,bank-account
    uv run python scripts/run_pipeline.py --model MODEL  # runs all 20
"""

import argparse
import asyncio
import sys

from dotenv import load_dotenv

load_dotenv()

from alspec.eval.domains import DOMAINS
from alspec.llm import AsyncLLMClient
from alspec.pipeline import run_pipeline
from alspec.result import Err, Ok


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--domains", default=None, help="Comma-separated domain IDs")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    match AsyncLLMClient.from_env():
        case Ok(client):
            pass
        case Err(e):
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)

    if args.domains:
        domain_ids = [d.strip() for d in args.domains.split(",")]
        domains = [d for d in DOMAINS if d.id in domain_ids]
        missing = set(domain_ids) - {d.id for d in domains}
        if missing:
            print(f"Unknown domains: {missing}", file=sys.stderr)
            sys.exit(1)
    else:
        domains = list(DOMAINS)

    print(f"Running pipeline on {len(domains)} domains with {args.model}\n")

    results = asyncio.run(_run_all(client, domains, args.model, args.verbose))

    # Summary
    successes = sum(1 for r in results if r.success)
    total = len(results)
    parse_rate = successes / total * 100 if total else 0

    perfect = sum(1 for r in results if r.score and r.score.health == 1.0)
    healths = [r.score.health for r in results if r.score]
    mean_health = sum(healths) / len(healths) if healths else 0

    print(f"\n{'='*60}")
    print(f"  Pipeline Results: {args.model}")
    print(f"{'='*60}")
    print(f"  Parse rate:    {successes}/{total} ({parse_rate:.0f}%)")
    print(f"  Perfect (1.0): {perfect}/{total}")
    print(f"  Mean health:   {mean_health:.2f}")

    # Token usage
    total_prompt = 0
    total_completion = 0
    total_cached = 0
    for r in results:
        for su in r.stage_usages:
            if su.usage:
                total_prompt += su.usage.prompt_tokens
                total_completion += su.usage.completion_tokens
                total_cached += su.usage.cached_tokens

    cache_rate = total_cached / total_prompt * 100 if total_prompt else 0
    print(f"\n  Total prompt tokens:     {total_prompt:,}")
    print(f"  Total completion tokens: {total_completion:,}")
    print(f"  Cached tokens:           {total_cached:,} ({cache_rate:.1f}%)")


async def _run_all(client, domains, model, verbose):
    results = []
    for domain in domains:
        result = await run_pipeline(
            client=client,
            domain_id=domain.id,
            domain_description=domain.description,
            model=model,
        )

        # Per-domain output
        if result.success:
            score = result.score
            health = f"{score.health:.2f}" if score else "?"
            axioms = len(result.spec.axioms) if result.spec else "?"
            errors = score.error_count if score else "?"
            warnings = score.warning_count if score else "?"
            cells = result.obligation_table.cell_count if result.obligation_table else "?"
            print(f"  ✓ {domain.id:25s} health={health} axioms={axioms} cells={cells} errors={errors} warnings={warnings} [{result.total_latency_ms}ms]")
        else:
            print(f"  ✗ {domain.id:25s} FAILED at {result.error_stage}: {result.error}")

        if verbose:
            if result.signature_analysis:
                print(f"    Stage 1 analysis: {result.signature_analysis[:200]}...")
            if result.obligation_table:
                print(f"    Obligation cells: {result.obligation_table.cell_count}")
            if result.spec_analysis:
                print(f"    Stage 2 analysis: {result.spec_analysis[:200]}...")
            if result.error:
                print(f"    Error: {result.error}")
            for su in result.stage_usages:
                if su.usage:
                    print(f"    {su.stage}: {su.usage.prompt_tokens} prompt, {su.usage.completion_tokens} completion, {su.usage.cached_tokens} cached")

        results.append(result)

    return results


if __name__ == "__main__":
    main()
