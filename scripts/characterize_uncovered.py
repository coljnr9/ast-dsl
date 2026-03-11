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
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from langfuse import get_client, propagate_attributes

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

from alspec.axiom_gen import (  # noqa: E402
    MechanicalAxiomReport,
    generate_mechanical_axioms,
)
from alspec.skeleton import generate_skeleton, splice_fills
from alspec.axiom_match import CoverageStatus, match_spec  # noqa: E402
from alspec.cache import (  # noqa: E402
    DomainSnapshot,
    load_cache,
    restore_signature,
    save_cache,
    snapshot_from_pipeline_result,
)
from alspec.check import check_spec  # noqa: E402
from alspec.eval.domains import DOMAINS, DomainPrompt  # noqa: E402
from alspec.llm import AsyncLLMClient  # noqa: E402
from alspec.obligation import ObligationTable, build_obligation_table  # noqa: E402
from alspec.pipeline import (  # noqa: E402
    _build_axioms_user_prompt,
    run_pipeline_signature_only,
)
from alspec.obligation_render import render_obligation_prompt
from alspec.prompt_chunks import ChunkId, Stage, assemble_prompt  # noqa: E402
from alspec.result import Err, Ok  # noqa: E402
from alspec.signature import Signature  # noqa: E402
from alspec.spec import Spec  # noqa: E402

logger = logging.getLogger(__name__)

# Langfuse client
langfuse = get_client()

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
            f"Unknown domain {domain!r}. Available: {sorted(_DOMAIN_MAP.keys())}"
        )
    return d.description


# ---------------------------------------------------------------------------
# Upstream cache (mirrors _build_upstream_cache from doe_runner.py)
# ---------------------------------------------------------------------------

from dataclasses import dataclass  # noqa: E402


@dataclass(frozen=True)
class UpstreamCache:
    domain: str
    signature: Signature
    obligation_table: ObligationTable
    mech_report: MechanicalAxiomReport
    signature_code: str
    signature_analysis: str
    obligation_prompt_md: str
    analysis_text: str | None
    spec_name: str


def _upstream_cache_from_snapshot(
    snapshot: DomainSnapshot,
) -> UpstreamCache:
    """Convert a loaded DomainSnapshot into the runtime UpstreamCache.

    Regenerates deterministic stages (obligation table, rendered markdown)
    from the frozen signature.
    """
    sig = restore_signature(snapshot)

    table = build_obligation_table(sig)
    mech_report = generate_mechanical_axioms(sig, table)
    prompt_md = render_obligation_prompt(sig, table, mech_report)

    assert snapshot.stage2 is not None  # guaranteed by load validation

    return UpstreamCache(
        domain=snapshot.domain,
        signature=sig,
        obligation_table=table,
        mech_report=mech_report,
        signature_code=snapshot.stage2.signature_code,
        signature_analysis=snapshot.stage2.signature_analysis,
        obligation_prompt_md=prompt_md,
        analysis_text=snapshot.stage1.analysis_text if snapshot.stage1 else None,
        spec_name=snapshot.domain.replace("-", " ").title().replace(" ", ""),
    )


def _snapshot_from_upstream_cache(uc: UpstreamCache) -> DomainSnapshot:
    """Convert a runtime UpstreamCache to a DomainSnapshot for saving."""
    return snapshot_from_pipeline_result(
        domain=uc.domain,
        analysis_text=uc.analysis_text,
        signature=uc.signature,
        signature_code=uc.signature_code,
        signature_analysis=uc.signature_analysis,
    )


async def _build_upstream_cache(
    client: AsyncLLMClient,
    domains: list[str],
    semaphore: asyncio.Semaphore,
    session_id: str,
) -> dict[str, UpstreamCache]:
    """Run Stages 1-2-3 for each domain and cache results."""
    logger.info("Building upstream cache (Stages 1-3) for %d domains...", len(domains))
    cache: dict[str, UpstreamCache] = {}
    lock = asyncio.Lock()

    async def run_one(domain: str) -> None:
        async with semaphore:
            desc = _get_domain_description(domain)

            with langfuse.start_as_current_observation(
                as_type="span",
                name=f"characterize/upstream/{domain}",
            ):
                with propagate_attributes(
                    trace_name=f"characterize/upstream/{domain}",
                    session_id=session_id,
                    metadata={
                        "domain": domain,
                        "model": UPSTREAM_MODEL,
                        "lens": UPSTREAM_LENS,
                        "session_id": session_id,
                    },
                    tags=[
                        f"domain:{domain}",
                        "phase:upstream",
                        f"session:{session_id}",
                    ],
                ):
                    result = await run_pipeline_signature_only(
                        client=client,
                        domain_id=domain,
                        domain_description=desc,
                        model=UPSTREAM_MODEL,
                        lens=UPSTREAM_LENS,
                    )

            if not result.success:
                logger.warning(
                    "Upstream failed for domain %s: %s", domain, result.error
                )
                return

            sig = result.signature
            if sig is None:
                logger.warning("Upstream returned no signature for domain %s", domain)
                return

            try:
                table = build_obligation_table(sig)
                mech_report = generate_mechanical_axioms(sig, table)
                prompt_md = render_obligation_prompt(sig, table, mech_report)
            except Exception as e:
                logger.warning("Obligation table failed for domain %s: %s", domain, e)
                return

            entry = UpstreamCache(
                domain=domain,
                signature=sig,
                obligation_table=table,
                mech_report=mech_report,
                signature_code=result.signature_code or "",
                signature_analysis=result.signature_analysis or "",
                obligation_prompt_md=prompt_md,
                analysis_text=result.domain_analysis,
                spec_name=domain.replace("-", " ").title().replace(" ", ""),
            )
            async with lock:
                cache[domain] = entry

    await asyncio.gather(*[run_one(d) for d in domains])
    logger.info("Upstream cache: %d/%d succeeded", len(cache), len(domains))
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
    coverage_ratio: float | None
    covered_cells: int
    total_cells: int
    error: str
    spec_code: str | None = None


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
    session_id: str,
    cache_id: str,
) -> TrialResult:
    """Run one (domain, replicate) trial. Returns a TrialResult.

    Inlines scoring logic from score_stage4_output so we can capture the
    MatchReport and extract per-cell detail without a double exec.
    Never raises — all errors surface as failed TrialResult.
    """
    desc = _get_domain_description(domain)

    # Generate skeleton for this trial
    skeleton = generate_skeleton(
        sig=upstream.signature,
        signature_code=upstream.signature_code,
        table=upstream.obligation_table,
        mechanical_report=upstream.mech_report,
        spec_name=upstream.spec_name,
    )

    user_prompt = _build_axioms_user_prompt(
        domain_description=desc,
        spec_name=upstream.spec_name,
        skeleton=skeleton,
        signature_analysis=upstream.signature_analysis,
        domain_analysis=upstream.analysis_text,
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    trace_name = f"characterize/trial/{domain}/rep{replicate}"
    with langfuse.start_as_current_observation(
        as_type="span",
        name=trace_name,
    ):
        with propagate_attributes(
            trace_name=trace_name,
            session_id=session_id,
            metadata={
                "cache_id": cache_id,
                "domain": domain,
                "replicate": str(replicate),
                "session_id": session_id,
            },
            tags=[
                f"domain:{domain}",
                f"session:{session_id}",
                f"cache:{cache_id}",
            ],
        ):
            result = await client.generate_with_fills_tool(
                messages, model=MODEL, name=f"characterize/{domain}/rep{replicate}"
            )

    match result:
        case Err(exc):
            return TrialResult(
                domain=domain,
                replicate=replicate,
                parse_success=False,
                well_formed=False,
                coverage_ratio=None,
                covered_cells=0,
                total_cells=0,
                error=f"LLM error: {exc}",
                spec_code=None,
            )
        case Ok((_, vars_list, fills, _)):
            code = splice_fills(skeleton, vars_list, fills)

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
            spec_code=code,
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
            spec_code=code,
        )

    # 2. Merge mechanical axioms (Stage 3.5)
    mech_report = upstream.mech_report
    mech_labels = {a.label for a in mech_report.axioms}
    # Keep LLM axioms that don't collide with mechanical labels
    combined_axioms = list(mech_report.axioms) + [
        a for a in spec.axioms if a.label not in mech_labels
    ]
    spec = Spec(
        name=spec.name,
        signature=upstream.signature,
        axioms=tuple(combined_axioms),
    )
    n_mech = len(mech_report.axioms)
    n_merged = len(combined_axioms)
    logger.debug(
        "domain=%s rep=%d: merged %d mechanical axioms (%d total)",
        domain,
        replicate,
        n_mech,
        n_merged,
    )

    # 3. Well-formedness
    try:
        checker_report = check_spec(spec)
    except Exception as e:
        return TrialResult(domain=domain, replicate=replicate, parse_success=False, parse_error=f"check_spec crashed: {e}", coverage_ratio=0.0, uncovered_cells=[], spec_code=spec_code)
    well_formed = checker_report.is_well_formed

    # 4. Match — uses upstream sig NOT spec.signature (consistent with doe_runner)
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
            spec_code=code,
        )

    # 5. Coverage metrics
    total_cells = len(match_report.coverage)
    covered_cells = sum(
        1 for c in match_report.coverage if c.status != CoverageStatus.UNCOVERED
    )
    coverage_ratio = (covered_cells / total_cells) if total_cells > 0 else None

    # 6. Extract uncovered cell rows (only for parse-successful trials)
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
        spec_code=code,
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
    parser.add_argument(
        "--save-specs",
        action="store_true",
        default=False,
        help="Save generated spec code to {output-dir}/specs/{domain}-rep{N}.py",
    )

    cache_group = parser.add_mutually_exclusive_group()
    cache_group.add_argument(
        "--cache",
        type=str,
        default=None,
        help="Load a saved pipeline cache (skip Stages 1-3). PATH must be a directory containing manifest.json.",
    )
    cache_group.add_argument(
        "--save-cache",
        type=str,
        default=None,
        help="After running Stages 1-3, save the upstream outputs to PATH for future reuse. Fails if PATH already exists.",
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

    # Langfuse session setup
    timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    session_id = f"characterize-{timestamp}"
    logger.info("Langfuse Session ID: %s", session_id)

    # Phase A: upstream cache
    upstream_cache: dict[str, UpstreamCache] = {}
    cache_id = "fresh"

    if args.cache:
        cache_dir = Path(args.cache)
        logger.info("Loading cache from %s...", cache_dir)
        manifest, snapshots = load_cache(cache_dir)

        if manifest.cache_through.value < Stage.SIGNATURE.value:
            logger.error(
                "Cache only goes through %s, but we need at least SIGNATURE.",
                manifest.cache_through.name,
            )
            sys.exit(1)

        cache_id = manifest.content_hash[:12]

        # Use a main trace for cache loading
        trace_name = "characterize/cache-load"
        with langfuse.start_as_current_observation(
            as_type="span",
            name=trace_name,
        ):
            with propagate_attributes(
                trace_name=trace_name,
                session_id=session_id,
                metadata={
                    "cache_dir": str(cache_dir),
                    "cache_id": cache_id,
                    "cache_through": manifest.cache_through.name,
                    "model": manifest.model,
                    "lens": manifest.lens or "none",
                    "domains": ",".join(manifest.domains),
                },
                tags=["phase:cache-load", f"cache:{cache_id}"],
            ):
                for domain, snap in snapshots.items():
                    if domains and domain not in domains:
                        continue

                    # Regeneration as a child span
                    span_name = f"characterize/regenerate/{domain}"
                    with langfuse.start_as_current_observation(
                        as_type="span",
                        name=span_name,
                    ):
                        with propagate_attributes(
                            trace_name=span_name,
                            metadata={
                                "domain": domain,
                                "cache_id": cache_id,
                            },
                        ):
                            uc = _upstream_cache_from_snapshot(snap)
                            upstream_cache[domain] = uc
                            # Tags are added via propagate_attributes if supported,
                            # but we can't easily add tags to nested observations
                            # through propagate_attributes in this logic.
                            # The metadata is enough for now.

    else:
        upstream_cache = await _build_upstream_cache(
            client, domains, semaphore, session_id
        )

        if args.save_cache:
            save_dir = Path(args.save_cache)
            logger.info("Saving cache to %s...", save_dir)
            snapshots = {
                domain: _snapshot_from_upstream_cache(uc)
                for domain, uc in upstream_cache.items()
            }
            manifest = save_cache(
                save_dir,
                snapshots,
                model=UPSTREAM_MODEL,
                lens=UPSTREAM_LENS,
                cache_through=Stage.SIGNATURE,
            )
            cache_id = manifest.content_hash[:12]

            cache_save_trace = "characterize/cache-save"
            with langfuse.start_as_current_observation(
                as_type="span",
                name=cache_save_trace,
            ):
                with propagate_attributes(
                    trace_name=cache_save_trace,
                    session_id=session_id,
                    metadata={
                        "cache_dir": str(save_dir),
                        "cache_id": cache_id,
                        "domains_saved": str(len(snapshots)),
                    },
                    tags=["phase:cache-save", f"cache:{cache_id}"],
                ):
                    pass

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
                session_id=session_id,
                cache_id=cache_id,
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
                    "code": trial_result.spec_code or "",
                }
            )

            if args.save_specs and trial_result.spec_code:
                specs_dir = output_dir / "specs"
                specs_dir.mkdir(parents=True, exist_ok=True)
                spec_path = specs_dir / f"{domain}-rep{replicate}.py"
                spec_path.write_text(trial_result.spec_code)

            uncovered_count = trial_result.total_cells - trial_result.covered_cells
            cov_str = (
                "N/A"
                if trial_result.coverage_ratio is None
                else f"{trial_result.coverage_ratio:.2f}"
            )
            logger.info(
                "domain=%-22s rep=%2d  parse=%-5s  coverage=%-6s  uncovered=%d  [%d/%d]",
                domain,
                replicate,
                trial_result.parse_success,
                cov_str,
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
        run_one(domain, rep) for domain in usable_domains for rep in range(replicates)
    ]
    await asyncio.gather(*tasks)

    # Write outputs
    output_dir.mkdir(parents=True, exist_ok=True)  # noqa: ASYNC240

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
    covs = [
        r["coverage_ratio"]
        for r in score_records
        if r["parse_success"] and r["coverage_ratio"] is not None
    ]
    if covs:
        mean_cov = sum(covs) / len(covs)
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
