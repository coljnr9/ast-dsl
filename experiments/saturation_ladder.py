#!/usr/bin/env python3
"""Saturation ladder experiment: measure how spec quality scales with example count.

Each rung adds one more worked example to the Stage 1 prompt.
Stage 2 prompt is held constant (default config).
All 20 eval domains are tested at each rung.

Usage:
    python experiments/saturation_ladder.py [--model MODEL] [--output-dir DIR] [--dry-run]
    python experiments/saturation_ladder.py --replicates 3 --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import logging
import math
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-5s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Rung definitions
# ---------------------------------------------------------------------------

from alspec.prompt_chunks import ChunkId, Stage, assemble_prompt

FOUNDATION = [
    ChunkId.ROLE_PREAMBLE,
    ChunkId.TYPE_GRAMMAR,
    ChunkId.API_HELPERS,
]

RUNGS: list[dict] = [
    {
        "name": "R0_stack_only",
        "label": "Stack only",
        "chunks": FOUNDATION + [ChunkId.EXAMPLE_STACK],
    },
    {
        "name": "R1_plus_bug_tracker",
        "label": "+ Bug Tracker Analysis",
        "chunks": FOUNDATION
        + [
            ChunkId.EXAMPLE_STACK,
            ChunkId.EXAMPLE_BUG_TRACKER_ANALYSIS,
        ],
    },
    {
        "name": "R2_plus_traffic_light",
        "label": "+ Traffic Light",
        "chunks": FOUNDATION
        + [
            ChunkId.EXAMPLE_STACK,
            ChunkId.EXAMPLE_BUG_TRACKER_ANALYSIS,
            ChunkId.EXAMPLE_BOUNDED_COUNTER,
        ],
    },
    {
        "name": "R3_plus_bounded_counter",
        "label": "+ Bounded Counter",
        "chunks": FOUNDATION
        + [
            ChunkId.EXAMPLE_STACK,
            ChunkId.EXAMPLE_BUG_TRACKER_ANALYSIS,
            ChunkId.EXAMPLE_BOUNDED_COUNTER,
            ChunkId.EXAMPLE_TRAFFIC_LIGHT,
        ],
    },
    {
        "name": "R4_plus_counter",
        "label": "+ Counter",
        "chunks": FOUNDATION
        + [
            ChunkId.EXAMPLE_STACK,
            ChunkId.EXAMPLE_BUG_TRACKER_ANALYSIS,
            ChunkId.EXAMPLE_BOUNDED_COUNTER,
            ChunkId.EXAMPLE_TRAFFIC_LIGHT,
            ChunkId.EXAMPLE_COUNTER,
        ],
    },
    {
        "name": "R5_plus_queue",
        "label": "+ Queue",
        "chunks": FOUNDATION
        + [
            ChunkId.EXAMPLE_STACK,
            ChunkId.EXAMPLE_BUG_TRACKER_ANALYSIS,
            ChunkId.EXAMPLE_BOUNDED_COUNTER,
            ChunkId.EXAMPLE_TRAFFIC_LIGHT,
            ChunkId.EXAMPLE_COUNTER,
            ChunkId.EXAMPLE_QUEUE,
        ],
    },
]


# ---------------------------------------------------------------------------
# Token estimation helper
# ---------------------------------------------------------------------------


def _estimate_tokens(chunks: list[ChunkId]) -> int:
    """Rough token estimate: assemble prompt, count chars, divide by 4."""
    text = assemble_prompt(
        chunks, Stage.STAGE1, validate_deps=False, validate_stage=False
    )
    return len(text) // 4


def _tokens_label(n: int) -> str:
    if n >= 1000:
        return f"~{n // 1000}k"
    return str(n)


# ---------------------------------------------------------------------------
# Dry-run display
# ---------------------------------------------------------------------------


def _dry_run(rungs: list[dict], domains: list, replicates: int) -> None:
    from alspec.eval.domains import DOMAINS

    total_calls = len(RUNGS) * len(DOMAINS) * replicates

    print("\n" + "═" * 70)
    print("  Saturation Ladder — DRY RUN")
    print("═" * 70)
    print(f"  Domains ({len(DOMAINS)}):")
    for d in DOMAINS:
        print(f"    {d.id}")

    print()
    for i, rung in enumerate(rungs):
        n_examples = len(rung["chunks"]) - len(FOUNDATION)
        tok = _estimate_tokens(rung["chunks"])
        chunk_names = ", ".join(c.name for c in rung["chunks"])
        print(
            f"  {rung['name']} ({n_examples} example{'s' if n_examples != 1 else ''})"
        )
        print(f"    label   : {rung['label']}")
        print(f"    tokens  : {_tokens_label(tok)} (est.)")
        print(f"    chunks  : {chunk_names}")
        print()

    rep_str = f"{len(RUNGS)} rungs × {len(DOMAINS)} domains × {replicates} replicates"
    print(f"  total calls: {rep_str} = {total_calls}")
    print()
    print("  (No LLM calls made — exiting.)")
    print("═" * 70 + "\n")


# ---------------------------------------------------------------------------
# Result record
# ---------------------------------------------------------------------------


def _make_record(
    rung_name: str,
    domain_id: str,
    replicate: int,
    *,
    parse_ok: bool,
    wf: bool,
    health: float,
    coverage_ratio: float | None,
    error_stage: str | None,
    error: str | None,
    latency_ms: int,
) -> dict:
    return {
        "rung": rung_name,
        "domain_id": domain_id,
        "replicate": replicate,
        "parse_ok": parse_ok,
        "wf": wf,
        "health": health,
        "coverage_ratio": coverage_ratio,
        "error_stage": error_stage,
        "error": error,
        "latency_ms": latency_ms,
    }


# ---------------------------------------------------------------------------
# One-domain runner
# ---------------------------------------------------------------------------


async def _run_domain(
    client,
    domain,
    rung: dict,
    model: str,
    replicate: int,
) -> dict:
    """Run the full pipeline for a single domain. Never raises."""
    from alspec.pipeline import run_pipeline

    t0 = time.monotonic()
    try:
        result = await run_pipeline(
            client,
            domain.id,
            domain.description,
            model,
            stage1_chunks=rung["chunks"],
        )
    except Exception as exc:
        latency_ms = int((time.monotonic() - t0) * 1000)
        return _make_record(
            rung["name"],
            domain.id,
            replicate,
            parse_ok=False,
            wf=False,
            health=0.0,
            coverage_ratio=None,
            error_stage="runner",
            error=str(exc),
            latency_ms=latency_ms,
        )

    latency_ms = int((time.monotonic() - t0) * 1000)

    parse_ok = result.spec is not None
    wf = False
    health = 0.0
    coverage_ratio = None

    if result.score is not None:
        wf = result.score.well_formed
        health = result.score.health
        coverage_ratio = result.score.coverage_ratio

    if not parse_ok:
        health = 0.0

    return _make_record(
        rung["name"],
        domain.id,
        replicate,
        parse_ok=parse_ok,
        wf=wf,
        health=health,
        coverage_ratio=coverage_ratio,
        error_stage=result.error_stage,
        error=result.error,
        latency_ms=latency_ms,
    )


# ---------------------------------------------------------------------------
# Parallel rung+replicate execution
# ---------------------------------------------------------------------------


async def _run_rung_replicate(
    client,
    rung: dict,
    domains: list,
    model: str,
    max_concurrent: int,
    replicate: int,
    replicates: int,
    *,
    experiment_start: float,
    completed_before: int,
    total_calls: int,
) -> list[dict]:
    """Run all domains for a single (rung, replicate) pair with bounded concurrency.

    Returns the list of result records (one per domain).
    Prints per-domain one-liners as results arrive, then a rung summary.
    Errors are printed loudly on first occurrence; repeats are counted.
    """
    rung_name = rung["name"]
    semaphore = asyncio.Semaphore(max_concurrent)
    lock = asyncio.Lock()
    rung_records: list[dict] = []
    completed_in_batch = 0
    seen_errors: dict[str, int] = {}  # error message → count
    batch_start = time.monotonic()

    async def _run_one(domain) -> dict:
        nonlocal completed_in_batch

        async with semaphore:
            record = await _run_domain(client, domain, rung, model, replicate)

        async with lock:
            completed_in_batch += 1
            rung_records.append(record)

            # One-liner progress
            health_str = f"{record['health']:.2f}"
            latency_s = record["latency_ms"] / 1000

            if record["error"] is not None:
                err_msg = record["error"]
                err_key = f"{record['error_stage']}:{err_msg[:80]}"

                if err_key not in seen_errors:
                    # First occurrence: print loud
                    seen_errors[err_key] = 1
                    logger.error(
                        "  ✗ %-22s health=%s  (%.1fs)  [%s] %s",
                        domain.id,
                        health_str,
                        latency_s,
                        record["error_stage"],
                        err_msg[:120],
                    )
                else:
                    seen_errors[err_key] += 1
                    logger.info(
                        "  ✗ %-22s health=%s  (%.1fs)  [%s] (same error ×%d)",
                        domain.id,
                        health_str,
                        latency_s,
                        record["error_stage"],
                        seen_errors[err_key],
                    )
            else:
                wf_flag = "WF" if record["wf"] else "--"
                logger.info(
                    "  ✓ %-22s health=%s %s  (%.1fs)",
                    domain.id,
                    health_str,
                    wf_flag,
                    latency_s,
                )

            # Running ETA (across entire experiment)
            global_completed = completed_before + completed_in_batch
            elapsed_total = time.monotonic() - experiment_start
            if elapsed_total > 0 and global_completed > 0:
                rate = global_completed / elapsed_total
                remaining = total_calls - global_completed
                eta_s = remaining / rate if rate > 0 else 0
                eta_min = eta_s / 60
                if completed_in_batch == len(domains) or completed_in_batch % 10 == 0:
                    logger.info(
                        "    [%d/%d global, %.1f calls/min, ETA ~%.0fm]",
                        global_completed,
                        total_calls,
                        rate * 60,
                        eta_min,
                    )

        return record

    tasks = [_run_one(domain) for domain in domains]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Handle any unexpected exceptions from gather
    final_records: list[dict] = []
    for i, r in enumerate(results):
        match r:
            case dict():
                final_records.append(r)
            case BaseException() as exc:
                logger.error(
                    "  ✗ %-22s UNEXPECTED EXCEPTION: %s",
                    domains[i].id,
                    "".join(traceback.format_exception_only(type(exc), exc)).strip(),
                )
                record = _make_record(
                    rung_name,
                    domains[i].id,
                    replicate,
                    parse_ok=False,
                    wf=False,
                    health=0.0,
                    coverage_ratio=None,
                    error_stage="gather",
                    error=str(exc),
                    latency_ms=0,
                )
                final_records.append(record)

    # Rung-replicate summary
    batch_elapsed = time.monotonic() - batch_start
    summary = _rung_summary(final_records)
    _print_rung_summary(rung_name, summary, replicate=replicate, replicates=replicates)
    logger.info("  Batch completed in %.1fs", batch_elapsed)

    # Report deduplicated error counts
    if seen_errors:
        logger.warning("  Error summary for %s rep %d:", rung_name, replicate)
        for err_key, count in seen_errors.items():
            logger.warning("    [×%d] %s", count, err_key)

    return final_records


# ---------------------------------------------------------------------------
# Summary helpers
# ---------------------------------------------------------------------------


def _median(vals: list[float]) -> float:
    """Return median of a non-empty list."""
    sorted_vals = sorted(vals)
    n = len(sorted_vals)
    mid = n // 2
    if n % 2 == 1:
        return sorted_vals[mid]
    return (sorted_vals[mid - 1] + sorted_vals[mid]) / 2.0


def _stddev(vals: list[float]) -> float:
    """Population standard deviation."""
    if len(vals) < 2:
        return 0.0
    mean = sum(vals) / len(vals)
    variance = sum((v - mean) ** 2 for v in vals) / len(vals)
    return math.sqrt(variance)


def _rung_summary(records: list[dict]) -> dict:
    """Aggregate metrics for a set of records (one rung, possibly multiple replicates)."""
    total = len(records)
    if total == 0:
        return {
            "total": 0,
            "parse": 0,
            "wf": 0,
            "health_mean": 0.0,
            "health_std": 0.0,
            "coverage_mean": None,
        }

    parsed = [r for r in records if r["parse_ok"]]
    wf_records = [r for r in records if r["wf"]]
    health_vals = [r["health"] for r in records]
    cov_vals = [r["coverage_ratio"] for r in records if r["coverage_ratio"] is not None]

    return {
        "total": total,
        "parse": len(parsed),
        "wf": len(wf_records),
        "health_mean": sum(health_vals) / total,
        "health_std": _stddev(health_vals),
        "coverage_mean": sum(cov_vals) / len(cov_vals) if cov_vals else None,
    }


def _print_rung_summary(
    rung_name: str,
    summary: dict,
    *,
    replicate: int | None = None,
    replicates: int = 1,
) -> None:
    total = summary["total"]
    parse = summary["parse"]
    wf = summary["wf"]
    health = summary["health_mean"]
    health_std = summary["health_std"]
    cov = summary["coverage_mean"]

    cov_str = f"{cov * 100:.1f}%" if cov is not None else "n/a"
    wf_denom = parse if parse > 0 else 1

    if replicate is not None and replicates > 1:
        rep_tag = f"[rep {replicate + 1}/{replicates}] "
    else:
        rep_tag = ""

    print(
        f"  {rep_tag}{rung_name}: {parse}/{total} parse  "
        f"{wf}/{wf_denom} WF  "
        f"health={health:.2f} ± {health_std:.2f}  "
        f"coverage={cov_str}"
    )


def _print_comparison_table(rungs: list[dict], all_records: list[dict]) -> None:
    print("\n" + "═" * 65)
    print("  Saturation Ladder Results")
    print("═" * 65)
    header = f"{'Rung':<6}  {'Examples':>8}  {'Parse':>7}  {'WF':>7}  {'Health':>6}  {'±Std':>5}  {'Coverage':>9}  {'Tokens':>10}"
    print(header)
    print("─" * 65)

    for rung in rungs:
        rung_name = rung["name"]
        n_examples = len(rung["chunks"]) - len(FOUNDATION)
        tok = _estimate_tokens(rung["chunks"])
        tok_label = _tokens_label(tok)

        rung_records = [r for r in all_records if r["rung"] == rung_name]
        summary = _rung_summary(rung_records)

        total = summary["total"]
        parse = summary["parse"]
        wf = summary["wf"]
        health = summary["health_mean"]
        health_std = summary["health_std"]
        cov = summary["coverage_mean"]

        parse_pct = f"{100 * parse / total:.1f}%" if total > 0 else "n/a"
        wf_denom = parse if parse > 0 else 1
        wf_pct = f"{100 * wf / wf_denom:.1f}%" if parse > 0 else "n/a"
        cov_str = f"{cov * 100:.1f}%" if cov is not None else "n/a"
        std_str = f"{health_std:.2f}"

        short = rung_name[:6]
        print(
            f"{short:<6}  {n_examples:>8}  {parse_pct:>7}  {wf_pct:>7}  {health:>6.2f}  {std_str:>5}  {cov_str:>9}  {tok_label:>10}"
        )

    print("═" * 65 + "\n")


# ---------------------------------------------------------------------------
# Output saving
# ---------------------------------------------------------------------------


def _save_results(
    output_dir: Path,
    all_records: list[dict],
    rungs: list[dict],
    model: str,
    timestamp: str,
    replicates: int,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    # results.jsonl — one record per (rung, domain, replicate)
    jsonl_path = output_dir / "results.jsonl"
    with jsonl_path.open("w", encoding="utf-8") as fh:
        for rec in all_records:
            fh.write(json.dumps(rec) + "\n")

    # summary.csv — one row per rung, pooling ALL replicates
    summary_path = output_dir / "summary.csv"
    with summary_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(
            [
                "rung",
                "n_examples",
                "total",
                "parse",
                "wf",
                "health_mean",
                "health_std",
                "coverage_mean",
                "tokens_est",
            ]
        )
        for rung in rungs:
            rung_name = rung["name"]
            n_examples = len(rung["chunks"]) - len(FOUNDATION)
            tok = _estimate_tokens(rung["chunks"])
            rung_records = [r for r in all_records if r["rung"] == rung_name]
            summary = _rung_summary(rung_records)
            writer.writerow(
                [
                    rung_name,
                    n_examples,
                    summary["total"],
                    summary["parse"],
                    summary["wf"],
                    f"{summary['health_mean']:.4f}",
                    f"{summary['health_std']:.4f}",
                    (
                        f"{summary['coverage_mean']:.4f}"
                        if summary["coverage_mean"] is not None
                        else ""
                    ),
                    tok,
                ]
            )

    # Collect all domain ids in stable order from records
    domain_ids: list[str] = []
    seen_ids: set[str] = set()
    for rec in all_records:
        if rec["domain_id"] not in seen_ids:
            domain_ids.append(rec["domain_id"])
            seen_ids.add(rec["domain_id"])

    # per_domain.csv — rows=domains, columns=rungs, values=MEDIAN health across replicates
    per_domain_path = output_dir / "per_domain.csv"
    with per_domain_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["domain"] + [r["name"] + "_health" for r in rungs])
        for domain_id in domain_ids:
            row = [domain_id]
            for rung in rungs:
                rung_name = rung["name"]
                cell_records = [
                    r
                    for r in all_records
                    if r["rung"] == rung_name and r["domain_id"] == domain_id
                ]
                if cell_records:
                    health_vals = [r["health"] for r in cell_records]
                    row.append(f"{_median(health_vals):.4f}")
                else:
                    row.append("")
            writer.writerow(row)

    # per_domain_raw.csv — one row per (domain, replicate) with all rung health values
    per_domain_raw_path = output_dir / "per_domain_raw.csv"
    with per_domain_raw_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["domain", "replicate"] + [r["name"] + "_health" for r in rungs])
        for domain_id in domain_ids:
            for rep in range(replicates):
                row: list = [domain_id, rep]
                for rung in rungs:
                    rung_name = rung["name"]
                    cell_records = [
                        r
                        for r in all_records
                        if r["rung"] == rung_name
                        and r["domain_id"] == domain_id
                        and r["replicate"] == rep
                    ]
                    if cell_records:
                        row.append(f"{cell_records[0]['health']:.4f}")
                    else:
                        row.append("")
                writer.writerow(row)

    # config.json
    config_path = output_dir / "config.json"
    config = {
        "model": model,
        "timestamp": timestamp,
        "replicates": replicates,
        "rungs": [
            {
                "name": rung["name"],
                "label": rung["label"],
                "n_examples": len(rung["chunks"]) - len(FOUNDATION),
                "chunks": [c.name for c in rung["chunks"]],
                "tokens_est": _estimate_tokens(rung["chunks"]),
            }
            for rung in rungs
        ],
    }
    with config_path.open("w", encoding="utf-8") as fh:
        json.dump(config, fh, indent=2)

    print(f"  Saved results to {output_dir}/")
    print(f"    results.jsonl      ({len(all_records)} records)")
    print(f"    summary.csv        (per-rung aggregates, pooled replicates)")
    print(f"    per_domain.csv     (median health matrix)")
    print(f"    per_domain_raw.csv (one row per domain×replicate)")
    print(f"    config.json        (run metadata)")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def main() -> int:
    parser = argparse.ArgumentParser(
        description="Saturation ladder experiment: sweep example count across all eval domains."
    )
    parser.add_argument(
        "--model",
        default="google/gemini-3-flash-preview",
        help="LLM model identifier (default: google/gemini-3-flash-preview)",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Directory to write results into (default: results/saturation-ladder-<timestamp>/)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print rung definitions and token estimates without making LLM calls",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=8,
        help="Max concurrent domain calls per rung (default: 8)",
    )
    parser.add_argument(
        "--replicates",
        type=int,
        default=1,
        help="Number of times to repeat each (rung, domain) pair (default: 1)",
    )
    args = parser.parse_args()

    from alspec.eval.domains import DOMAINS

    if args.dry_run:
        _dry_run(RUNGS, DOMAINS, args.replicates)
        return 0

    replicates: int = args.replicates

    # Build output dir
    timestamp = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    if args.output_dir is not None:
        output_dir = Path(args.output_dir)
    else:
        output_dir = Path("results") / f"saturation-ladder-{timestamp}"

    # Initialise LLM client
    from alspec.llm import AsyncLLMClient

    from alspec.result import Err, Ok

    client_res = AsyncLLMClient.from_env()
    match client_res:
        case Err(e):
            print(f"Failed to initialize LLM client: {e}", file=sys.stderr)
            return 1
        case Ok(client):
            pass

    model: str = args.model
    max_concurrent: int = args.concurrency
    total_calls = len(RUNGS) * len(DOMAINS) * replicates

    logger.info("Saturation Ladder Experiment")
    logger.info("  model       : %s", model)
    logger.info("  output-dir  : %s", output_dir)
    logger.info("  domains     : %d", len(DOMAINS))
    logger.info("  rungs       : %d", len(RUNGS))
    logger.info("  replicates  : %d", replicates)
    logger.info("  concurrency : %d", max_concurrent)
    logger.info(
        "  total calls : %d rungs × %d domains × %d replicates = %d",
        len(RUNGS),
        len(DOMAINS),
        replicates,
        total_calls,
    )
    logger.info("")

    all_records: list[dict] = []
    experiment_start = time.monotonic()

    # Outer loop: replicate index — so all domains for rep 0 run before rep 1
    for rung in RUNGS:
        rung_name = rung["name"]
        n_examples = len(rung["chunks"]) - len(FOUNDATION)
        tok = _estimate_tokens(rung["chunks"])

        logger.info("─" * 60)
        logger.info(
            "  Rung: %s  (%d example%s, %s tokens est.)",
            rung_name,
            n_examples,
            "s" if n_examples != 1 else "",
            _tokens_label(tok),
        )
        logger.info("─" * 60)

        for rep in range(replicates):
            if replicates > 1:
                logger.info(
                    "  [rep %d/%d] %s",
                    rep + 1,
                    replicates,
                    rung_name,
                )

            rung_rep_records = await _run_rung_replicate(
                client,
                rung,
                DOMAINS,
                model,
                max_concurrent,
                rep,
                replicates,
                experiment_start=experiment_start,
                completed_before=len(all_records),
                total_calls=total_calls,
            )
            all_records.extend(rung_rep_records)

        # Print pooled rung summary (across all replicates) when replicates > 1
        if replicates > 1:
            rung_all = [r for r in all_records if r["rung"] == rung_name]
            summary = _rung_summary(rung_all)
            print(
                f"  Rung total: {rung_name}: {summary['parse']}/{summary['total']} parse  "
                f"health={summary['health_mean']:.2f} ± {summary['health_std']:.2f}"
            )

    _print_comparison_table(RUNGS, all_records)
    _save_results(output_dir, all_records, RUNGS, model, timestamp, replicates)

    total_elapsed = time.monotonic() - experiment_start
    logger.info("Experiment completed in %.1fm", total_elapsed / 60)

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
