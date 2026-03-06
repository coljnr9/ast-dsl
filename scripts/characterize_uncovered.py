"""characterize_uncovered.py — Stage 4 uncovered-cell characterization run.

Runs the fixed optimal configuration (mandatory chunks + G + H) on every
registered domain over REPLICATES replicate runs and writes:

  results/stage4-characterize-v1/
  ├── scores.jsonl          one JSON line per trial
  └── uncovered_cells.csv   one row per uncovered cell (parse-successful only)

Unlike the DoE runner this script is NOT an experiment — there is no design
matrix.  It runs a single fixed config and captures the full MatchReport so
that uncovered cell detail (tier, dispatch, observer, constructor) that the
DoE scorer discards is preserved.

Usage:
    python scripts/characterize_uncovered.py
    python scripts/characterize_uncovered.py --domains counter,stack
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Config constants
# ---------------------------------------------------------------------------

MODEL = "google/gemini-3-flash-preview"
REPLICATES = 10
MAX_CONCURRENT = 10
UPSTREAM_MODEL = "google/gemini-3-flash-preview"
UPSTREAM_LENS = "entity_lifecycle"
OUTPUT_DIR = Path("results/stage4-characterize-v1")

# All 20 registered domain IDs (from alspec/eval/domains.py)
ALL_DOMAINS = [
    "counter",
    "traffic-light",
    "boolean-flag",
    "temperature-sensor",
    "stack",
    "bank-account",
    "todo-list",
    "door-lock",
    "queue",
    "bounded-counter",
    "phone-book",
    "inventory",
    "access-control",
    "library-lending",
    "bug-tracker",
    "shopping-cart",
    "thermostat",
    "email-inbox",
    "version-history",
    "auction",
]

# ---------------------------------------------------------------------------
# Imports after path setup
# ---------------------------------------------------------------------------

from alspec.axiom_match import match_spec, CoverageStatus
from alspec.check import check_spec
from alspec.eval.domains import DOMAINS, DomainPrompt
from alspec.eval.stage1_score import (
    compute_intrinsic_health,
    _constructor_names,
    _observer_count,
    _check_well_formed,
)
from alspec.llm import AsyncLLMClient
from alspec.obligation import build_obligation_table, ObligationTable
from alspec.obligation_render import render_obligation_table
from alspec.pipeline import (
    _build_axioms_user_prompt,
    _build_signature_user_prompt,
    run_pipeline_signature_only,
)
from alspec.prompt_chunks import ChunkId, Stage, assemble_prompt
from alspec.result import Err, Ok
from alspec.signature import Signature
from alspec.spec import Spec

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Fixed chunk config: mandatory + G + H (from stage4_screen.toml optimal)
# ---------------------------------------------------------------------------

CHUNK_IDS = [
    ChunkId.ROLE_PREAMBLE,
    ChunkId.TYPE_GRAMMAR,
    ChunkId.API_HELPERS,
    ChunkId.OBLIGATION_PATTERN,
    ChunkId.AXIOMS_METHODOLOGY,
    ChunkId.WF_CHECKLIST,
    # G: primary examples
    ChunkId.EXAMPLE_SESSION_STORE_SPEC,
    ChunkId.EXAMPLE_RATE_LIMITER_SPEC,
    ChunkId.EXAMPLE_DNS_ZONE_SPEC,
    # H: secondary examples
    ChunkId.EXAMPLE_COUNTER,
    ChunkId.EXAMPLE_STACK,
    ChunkId.EXAMPLE_BOUNDED_COUNTER,
]

# ---------------------------------------------------------------------------
# Domain description helper
# ---------------------------------------------------------------------------

_DOMAIN_MAP: dict[str, DomainPrompt] = {d.id: d for d in DOMAINS}


def _get_domain_description(domain: str) -> str:
    d = _DOMAIN_MAP.get(domain)
    if d is None:
        raise ValueError(
            f"Unknown domain {domain!r}. "
            f"Available: {sorted(_DOMAIN_MAP.keys())}"
        )
    return d.description


# ---------------------------------------------------------------------------
# Upstream cache (mirrors _build_upstream_cache from doe_runner.py)
# ---------------------------------------------------------------------------

from dataclasses import dataclass


@dataclass(frozen=True)
class UpstreamCache:
    domain: str
    signature: Signature
    obligation_table: ObligationTable
    signature_code: str
    signature_analysis: str
    obligation_table_rendered: str
    analysis_text: str | None
    spec_name: str


async def _build_upstream_cache(
    client: AsyncLLMClient,
    domains: list[str],
    semaphore: asyncio.Semaphore,
) -> dict[str, UpstreamCache]:
    """Run Stages 1-2-3 for each domain and cache results."""
    logger.info("Building upstream cache (Stages 1-3) for %d domains...", len(domains))
    cache: dict[str, UpstreamCache] = {}
    lock = asyncio.Lock()

    async def run_one(domain: str) -> None:
        async with semaphore:
            desc = _get_domain_description(domain)
            result = await run_pipeline_signature_only(
                client=client,
                domain_id=domain,
                domain_description=desc,
                model=UPSTREAM_MODEL,
                lens=UPSTREAM_LENS,
            )

            if not result.success:
                logger.warning("Upstream failed for domain %s: %s", domain, result.error)
                return

            sig = result.signature
            if sig is None:
                logger.warning("Upstream returned no signature for domain %s", domain)
                return

            try:
                table = build_obligation_table(sig)
                table_md = render_obligation_table(sig, table)
            except Exception as e:
                logger.warning("Obligation table failed for domain %s: %s", domain, e)
                return

            entry = UpstreamCache(
                domain=domain,
                signature=sig,
                obligation_table=table,
                signature_code=result.signature_code or "",
                signature_analysis=result.signature_analysis or "",
                obligation_table_rendered=table_md,
                analysis_text=result.domain_analysis,
                spec_name=domain.replace("-", " ").title().replace(" ", ""),
            )
            async with lock:
                cache[domain] = entry

    await asyncio.gather(*[run_one(d) for d in domains])
    logger.info(
        "Upstream cache: %d/%d succeeded", len(cache), len(domains)
    )
    return cache


# ---------------------------------------------------------------------------
# Trial result dataclass
# ---------------------------------------------------------------------------


@dataclass
class TrialResult:
    domain: str
    replicate: int
    parse_success: bool
    well_formed: bool
    coverage_ratio: float
    covered_cells: int
    total_cells: int
    error: str


# ---------------------------------------------------------------------------
# A single Stage 4 trial with inline scoring (Option B — no double-exec)
# ---------------------------------------------------------------------------


async def _run_trial(
    client: AsyncLLMClient,
    domain: str,
    replicate: int,
    upstream: UpstreamCache,
    system_prompt: str,
    uncovered_rows: list[dict[str, str]],
    lock: asyncio.Lock,
) -> TrialResult:
    """Run one (domain, replicate) trial. Returns a TrialResult.

    Inlines scoring logic from score_stage4_output so we can capture the
    MatchReport and extract per-cell detail without a double exec.
    Never raises — all errors surface as failed TrialResult.
    """
    desc = _get_domain_description(domain)

    user_prompt = _build_axioms_user_prompt(
        domain_description=desc,
        spec_name=upstream.spec_name,
        signature_code=upstream.signature_code,
        signature_analysis=upstream.signature_analysis,
        obligation_table_md=upstream.obligation_table_rendered,
        domain_analysis=upstream.analysis_text,
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    result = await client.generate_with_tool_call(
        messages, model=MODEL, tool_name="submit_spec"
    )

    match result:
        case Err(exc):
            return TrialResult(
                domain=domain,
                replicate=replicate,
                parse_success=False,
                well_formed=False,
                coverage_ratio=0.0,
                covered_cells=0,
                total_cells=0,
                error=f"LLM error: {exc}",
            )
        case Ok((_, code, _)):
            pass

    # ---- Inline scoring (Option B) ----

    # 1. Parse
    namespace: dict[str, Any] = {}
    try:
        exec("from alspec import *", namespace)
        exec("from alspec.helpers import *", namespace)
        exec(code, namespace)
    except Exception as e:
        return TrialResult(
            domain=domain,
            replicate=replicate,
            parse_success=False,
            well_formed=False,
            coverage_ratio=0.0,
            covered_cells=0,
            total_cells=0,
            error=f"Exec failed: {e}",
        )

    spec = namespace.get("spec")
    if not isinstance(spec, Spec):
        got = type(spec).__name__ if spec is not None else "nothing"
        return TrialResult(
            domain=domain,
            replicate=replicate,
            parse_success=False,
            well_formed=False,
            coverage_ratio=0.0,
            covered_cells=0,
            total_cells=0,
            error=f"No `spec` variable of type Spec (got {got})",
        )

    # 2. Well-formedness
    checker_report = check_spec(spec)
    well_formed = checker_report.is_well_formed

    # 3. Match — uses upstream sig NOT spec.signature (consistent with doe_runner)
    try:
        table = build_obligation_table(upstream.signature)
        match_report = await match_spec(spec, table, upstream.signature)
    except Exception as e:
        return TrialResult(
            domain=domain,
            replicate=replicate,
            parse_success=True,
            well_formed=well_formed,
            coverage_ratio=0.0,
            covered_cells=0,
            total_cells=0,
            error=f"Scoring/matching failed: {e}",
        )

    # 4. Coverage metrics
    total_cells = len(match_report.coverage)
    covered_cells = sum(
        1 for c in match_report.coverage if c.status != CoverageStatus.UNCOVERED
    )
    coverage_ratio = (covered_cells / total_cells) if total_cells > 0 else 0.0

    # 5. Extract uncovered cell rows (only for parse-successful trials)
    new_rows: list[dict[str, str]] = []
    for cell in match_report.uncovered_cells:
        new_rows.append(
            {
                "domain": domain,
                "replicate": str(replicate),
                "observer_name": cell.observer_name,
                "observer_is_predicate": str(cell.observer_is_predicate),
                "constructor_name": cell.constructor_name,
                "generated_sort": cell.generated_sort,
                "dispatch": cell.dispatch.value,
                "tier": cell.tier.value,
            }
        )

    async with lock:
        uncovered_rows.extend(new_rows)

    return TrialResult(
        domain=domain,
        replicate=replicate,
        parse_success=True,
        well_formed=well_formed,
        coverage_ratio=coverage_ratio,
        covered_cells=covered_cells,
        total_cells=total_cells,
        error="",
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    parser = argparse.ArgumentParser(
        description="Run the fixed optimal Stage 4 config and capture uncovered cell details."
    )
    parser.add_argument(
        "--domains",
        type=str,
        default=None,
        help="Comma-separated list of domain IDs to run (default: all 20)",
    )
    parser.add_argument(
        "--replicates",
        type=int,
        default=REPLICATES,
        help=f"Number of replicates per domain (default: {REPLICATES})",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=str(OUTPUT_DIR),
        help=f"Output directory (default: {OUTPUT_DIR})",
    )
    args = parser.parse_args()

    if args.domains is not None:
        domains = [d.strip() for d in args.domains.split(",") if d.strip()]
    else:
        domains = list(ALL_DOMAINS)

    replicates = args.replicates
    output_dir = Path(args.output_dir)

    logger.info("Domains: %s", domains)
    logger.info("Replicates: %d", replicates)
    logger.info("Model: %s", MODEL)
    logger.info("Output: %s", output_dir)

    # Build system prompt (single fixed config)
    system_prompt = assemble_prompt(
        CHUNK_IDS,
        Stage.AXIOMS,
        validate_deps=False,
        validate_stage=False,
    )
    logger.info("System prompt assembled (%d chars)", len(system_prompt))

    # LLM client
    client_res = AsyncLLMClient.from_env()
    match client_res:
        case Ok(client):
            pass
        case Err(e):
            logger.error("Failed to create LLM client: %s", e)
            sys.exit(1)

    semaphore = asyncio.Semaphore(MAX_CONCURRENT)

    # Phase A: upstream cache
    upstream_cache = await _build_upstream_cache(client, domains, semaphore)
    if not upstream_cache:
        logger.error("All upstream runs failed. Aborting.")
        sys.exit(1)

    usable_domains = sorted(upstream_cache.keys())
    logger.info(
        "Upstream succeeded for %d/%d domains: %s",
        len(usable_domains),
        len(domains),
        usable_domains,
    )

    # Phase B: Stage 4 trials
    total_trials = len(usable_domains) * replicates
    completed = 0
    score_records: list[dict[str, Any]] = []
    uncovered_rows: list[dict[str, str]] = []
    lock = asyncio.Lock()
    experiment_start = time.monotonic()

    async def run_one(domain: str, replicate: int) -> None:
        nonlocal completed
        upstream = upstream_cache[domain]
        async with semaphore:
            trial_result = await _run_trial(
                client=client,
                domain=domain,
                replicate=replicate,
                upstream=upstream,
                system_prompt=system_prompt,
                uncovered_rows=uncovered_rows,
                lock=lock,
            )

        async with lock:
            completed += 1
            score_records.append(
                {
                    "domain": trial_result.domain,
                    "replicate": trial_result.replicate,
                    "parse_success": trial_result.parse_success,
                    "well_formed": trial_result.well_formed,
                    "coverage_ratio": trial_result.coverage_ratio,
                    "covered_cells": trial_result.covered_cells,
                    "total_cells": trial_result.total_cells,
                    "error": trial_result.error,
                }
            )

            uncovered_count = trial_result.total_cells - trial_result.covered_cells
            logger.info(
                "domain=%-22s rep=%2d  parse=%-5s  coverage=%.2f  uncovered=%d  [%d/%d]",
                domain,
                replicate,
                trial_result.parse_success,
                trial_result.coverage_ratio,
                uncovered_count,
                completed,
                total_trials,
            )

            if completed % 20 == 0:
                elapsed = time.monotonic() - experiment_start
                rate = completed / elapsed
                eta = (total_trials - completed) / rate if rate > 0 else 0
                logger.info(
                    "  --- Progress %d/%d | %.1f/min | ETA %.0fm ---",
                    completed,
                    total_trials,
                    rate * 60,
                    eta / 60,
                )

    tasks = [
        run_one(domain, rep)
        for domain in usable_domains
        for rep in range(replicates)
    ]
    await asyncio.gather(*tasks)

    # Write outputs
    output_dir.mkdir(parents=True, exist_ok=True)

    scores_path = output_dir / "scores.jsonl"
    with scores_path.open("w", encoding="utf-8") as f:
        for rec in score_records:
            f.write(json.dumps(rec) + "\n")
    logger.info("Wrote %d score records to %s", len(score_records), scores_path)

    csv_path = output_dir / "uncovered_cells.csv"
    csv_columns = [
        "domain",
        "replicate",
        "observer_name",
        "observer_is_predicate",
        "constructor_name",
        "generated_sort",
        "dispatch",
        "tier",
    ]
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=csv_columns)
        writer.writeheader()
        writer.writerows(uncovered_rows)
    logger.info("Wrote %d uncovered cell rows to %s", len(uncovered_rows), csv_path)

    # Summary
    parse_ok = sum(1 for r in score_records if r["parse_success"])
    if parse_ok > 0:
        mean_cov = sum(
            r["coverage_ratio"] for r in score_records if r["parse_success"]
        ) / parse_ok
    else:
        mean_cov = 0.0

    logger.info(
        "Done. Trials=%d  parse_ok=%d (%.1f%%)  mean_coverage=%.3f  uncovered_rows=%d",
        len(score_records),
        parse_ok,
        100 * parse_ok / len(score_records) if score_records else 0,
        mean_cov,
        len(uncovered_rows),
    )


if __name__ == "__main__":
    asyncio.run(main())
