#!/usr/bin/env python3
"""Saturation ladder experiment (Stage 1 only).

Measure how signature quality scales with example count, skipping Stage 2.
This is faster and cheaper than the full pipeline.

Usage:
    python experiments/saturation_ladder_s1.py [--model MODEL] [--output-dir DIR] [--dry-run]
    python experiments/saturation_ladder_s1.py --replicates 3 --dry-run
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

from alspec.eval.stage1_score import FailureCategory, score_stage1_output
from alspec.pipeline import run_pipeline_stage1_only
from alspec.prompt_chunks import ChunkId, Stage, assemble_prompt

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-5s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Rung definitions
# ---------------------------------------------------------------------------

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
    print("  Saturation Ladder S1 — DRY RUN")
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


def _make_s1_record(
    rung_name: str,
    domain_id: str,
    replicate: int,
    *,
    parse_ok: bool,
    well_formed: bool,
    failure_category: str,
    health: float,
    sort_overlap: float,
    function_overlap: float,
    predicate_overlap: float,
    constructor_overlap: float,
    cell_count_delta: int,
    error: str | None,
    latency_ms: int,
    tokens_est: int = 0,
) -> dict:
    return {
        "rung": rung_name,
        "domain_id": domain_id,
        "replicate": replicate,
        "parse_ok": parse_ok,
        "well_formed": well_formed,
        "failure_category": failure_category,
        "health": health,
        "sort_overlap": sort_overlap,
        "function_overlap": function_overlap,
        "predicate_overlap": predicate_overlap,
        "constructor_overlap": constructor_overlap,
        "cell_count_delta": cell_count_delta,
        "error": error,
        "latency_ms": latency_ms,
        "tokens_est": tokens_est,
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
    """Run Stage 1 only for a single domain. Never raises."""
    t0 = time.monotonic()
    tokens_est = _estimate_tokens(rung["chunks"])
    try:
        result = await run_pipeline_stage1_only(
            client,
            domain.id,
            domain.description,
            model,
            stage1_chunks=rung["chunks"],
        )
    except Exception as exc:
        latency_ms = int((time.monotonic() - t0) * 1000)
        return _make_s1_record(
            rung["name"],
            domain.id,
            replicate,
            parse_ok=False,
            well_formed=False,
            failure_category=FailureCategory.EXEC_ERROR.value,
            health=0.0,
            sort_overlap=0.0,
            function_overlap=0.0,
            predicate_overlap=0.0,
            constructor_overlap=0.0,
            cell_count_delta=0,
            error=str(exc),
            latency_ms=latency_ms,
            tokens_est=tokens_est,
        )

    latency_ms = int((time.monotonic() - t0) * 1000)

    # Score the output
    score = score_stage1_output(
        code=result.signature_code or "",
        domain=domain.id,
        replicate=replicate,
        model=model,
        golden_dir=Path("golden/"),
    )

    return _make_s1_record(
        rung["name"],
        domain.id,
        replicate,
        parse_ok=score.parse_success,
        well_formed=score.well_formed,
        failure_category=score.failure_category.value,
        health=score.health,
        sort_overlap=score.sort_overlap,
        function_overlap=score.function_overlap,
        predicate_overlap=score.predicate_overlap,
        constructor_overlap=score.constructor_overlap,
        cell_count_delta=score.cell_count_delta,
        error=score.error_message or result.error,
        latency_ms=latency_ms,
        tokens_est=tokens_est,
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
    """Run all domains for a single (rung, replicate) pair with bounded concurrency."""
    rung_name = rung["name"]
    semaphore = asyncio.Semaphore(max_concurrent)
    lock = asyncio.Lock()
    rung_records: list[dict] = []
    completed_in_batch = 0
    seen_errors: dict[str, int] = {}
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

            if record["failure_category"] != "ok":
                err_msg = record["error"] or "Unknown error"
                err_key = f"{record['failure_category']}:{err_msg[:80]}"

                if err_key not in seen_errors:
                    seen_errors[err_key] = 1
                    logger.error(
                        "  ✗ %-22s health=%s  (%.1fs)  [%s] %s",
                        domain.id,
                        health_str,
                        latency_s,
                        record["failure_category"],
                        err_msg[:120],
                    )
                else:
                    seen_errors[err_key] += 1
                    logger.info(
                        "  ✗ %-22s health=%s  (%.1fs)  [%s] (same error ×%d)",
                        domain.id,
                        health_str,
                        latency_s,
                        record["failure_category"],
                        seen_errors[err_key],
                    )
            else:
                wf_flag = "WF" if record["well_formed"] else "--"
                logger.info(
                    "  ✓ %-22s health=%s %s  (%.1fs)",
                    domain.id,
                    health_str,
                    wf_flag,
                    latency_s,
                )

            # Running ETA
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
                record = _make_s1_record(
                    rung_name,
                    domains[i].id,
                    replicate,
                    parse_ok=False,
                    well_formed=False,
                    failure_category="exec_error",
                    health=0.0,
                    sort_overlap=0.0,
                    function_overlap=0.0,
                    predicate_overlap=0.0,
                    constructor_overlap=0.0,
                    cell_count_delta=0,
                    error=str(exc),
                    latency_ms=0,
                )
                final_records.append(record)

    batch_elapsed = time.monotonic() - batch_start
    summary = _rung_summary(final_records)
    _print_rung_summary(rung_name, summary, replicate=replicate, replicates=replicates)
    logger.info("  Batch completed in %.1fs", batch_elapsed)

    if seen_errors:
        logger.warning("  Error summary for %s rep %d:", rung_name, replicate)
        for err_key, count in seen_errors.items():
            logger.warning("    [×%d] %s", count, err_key)

    return final_records


# ---------------------------------------------------------------------------
# Summary helpers
# ---------------------------------------------------------------------------


def _stddev(vals: list[float]) -> float:
    if len(vals) < 2:
        return 0.0
    mean = sum(vals) / len(vals)
    variance = sum((v - mean) ** 2 for v in vals) / len(vals)
    return math.sqrt(variance)


def _rung_summary(records: list[dict]) -> dict:
    total = len(records)
    parsed = [r for r in records if r["parse_ok"]]
    wf = [r for r in records if r["well_formed"]]
    health_vals = [r["health"] for r in records]
    cond_health_vals = [r["health"] for r in parsed]

    failures = {}
    for r in records:
        cat = r["failure_category"]
        if cat != "ok":
            failures[cat] = failures.get(cat, 0) + 1

    return {
        "total": total,
        "parse_count": len(parsed),
        "wf_count": len(wf),
        "health_mean": sum(health_vals) / total if total > 0 else 0.0,
        "health_std": _stddev(health_vals),
        "cond_health_mean": (
            sum(cond_health_vals) / len(cond_health_vals) if cond_health_vals else 0.0
        ),
        "cond_health_std": _stddev(cond_health_vals) if cond_health_vals else 0.0,
        "syntax_errors": failures.get("syntax", 0),
        "import_errors": failures.get("import", 0),
        "api_misuse_errors": failures.get("api_misuse", 0),
        "exec_errors": failures.get("exec_error", 0),
        "wrong_type_errors": failures.get("wrong_type", 0),
    }


def _print_rung_summary(
    rung_name: str,
    summary: dict,
    *,
    replicate: int | None = None,
    replicates: int = 1,
) -> None:
    total = summary["total"]
    parse = summary["parse_count"]
    health = summary["health_mean"]
    cond_health = summary["cond_health_mean"]

    syntax = summary["syntax_errors"]
    import_err = summary["import_errors"]
    api = summary["api_misuse_errors"]

    parse_pct = f"{100 * parse / total:.0f}%" if total > 0 else "0%"
    rep_tag = f"[rep {replicate + 1}/{replicates}] " if replicate is not None else ""

    print(
        f"  {rep_tag}{rung_name}: {parse_pct} parse | "
        f"health={health:.2f} | cond_health={cond_health:.2f} | "
        f"failures: {syntax} syntax, {import_err} import, {api} api"
    )


def _print_comparison_table(rungs: list[dict], all_records: list[dict]) -> None:
    print("\n" + "═" * 90)
    print("  Saturation Ladder S1 Results")
    print("═" * 90)
    header = (
        f"{'Rung':<6}  {'Ex':>2}  {'Parse':>6}  {'Health':>6}  {'±Std':>5}  "
        f"{'CondH':>6}  {'±Std':>5}  {'Syn':>3}  {'Imp':>3}  {'API':>3}  {'Tok':>5}"
    )
    print(header)
    print("─" * 90)

    for rung in rungs:
        rung_name = rung["name"]
        n_examples = len(rung["chunks"]) - len(FOUNDATION)
        tok = _estimate_tokens(rung["chunks"])
        tok_label = _tokens_label(tok)

        rung_records = [r for r in all_records if r["rung"] == rung_name]
        summary = _rung_summary(rung_records)

        total = summary["total"]
        parse_pct = (
            f"{100 * summary['parse_count'] / total:.0f}%" if total > 0 else "n/a"
        )

        short = rung_name[:6]
        print(
            f"{short:<6}  {n_examples:>2}  {parse_pct:>6}  "
            f"{summary['health_mean']:>6.2f}  {summary['health_std']:>5.2f}  "
            f"{summary['cond_health_mean']:>6.2f}  {summary['cond_health_std']:>5.2f}  "
            f"{summary['syntax_errors']:>3}  {summary['import_errors']:>3}  "
            f"{summary['api_misuse_errors']:>3}  {tok_label:>5}"
        )

    print("═" * 90 + "\n")


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

    jsonl_path = output_dir / "results.jsonl"
    with jsonl_path.open("w", encoding="utf-8") as fh:
        for rec in all_records:
            fh.write(json.dumps(rec) + "\n")

    summary_path = output_dir / "summary.csv"
    with summary_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(
            [
                "rung",
                "n_examples",
                "total",
                "parse_count",
                "wf_count",
                "health_mean",
                "health_std",
                "cond_health_mean",
                "cond_health_std",
                "syntax_errors",
                "import_errors",
                "api_misuse_errors",
                "exec_errors",
                "wrong_type_errors",
                "tokens_est",
            ]
        )
        for rung in rungs:
            rung_records = [r for r in all_records if r["rung"] == rung["name"]]
            s = _rung_summary(rung_records)
            writer.writerow(
                [
                    rung["name"],
                    len(rung["chunks"]) - len(FOUNDATION),
                    s["total"],
                    s["parse_count"],
                    s["wf_count"],
                    f"{s['health_mean']:.4f}",
                    f"{s['health_std']:.4f}",
                    f"{s['cond_health_mean']:.4f}",
                    f"{s['cond_health_std']:.4f}",
                    s["syntax_errors"],
                    s["import_errors"],
                    s["api_misuse_errors"],
                    s["exec_errors"],
                    s["wrong_type_errors"],
                    _estimate_tokens(rung["chunks"]),
                ]
            )

    domain_ids = sorted(list(set(r["domain_id"] for r in all_records)))

    per_domain_path = output_dir / "per_domain.csv"
    with per_domain_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["domain"] + [r["name"] + "_health" for r in rungs])
        for d_id in domain_ids:
            row = [d_id]
            for rung in rungs:
                recs = [
                    r
                    for r in all_records
                    if r["rung"] == rung["name"] and r["domain_id"] == d_id
                ]
                if recs:
                    h_vals = sorted([r["health"] for r in recs])
                    mid = len(h_vals) // 2
                    median = (
                        h_vals[mid]
                        if len(h_vals) % 2 == 1
                        else (h_vals[mid - 1] + h_vals[mid]) / 2.0
                    )
                    row.append(f"{median:.4f}")
                else:
                    row.append("")
            writer.writerow(row)

    config_path = output_dir / "config.json"
    config = {
        "model": model,
        "timestamp": timestamp,
        "replicates": replicates,
        "experiment_type": "stage1_only",
        "rungs": [
            {
                "name": r["name"],
                "n_examples": len(r["chunks"]) - len(FOUNDATION),
                "tokens_est": _estimate_tokens(r["chunks"]),
            }
            for r in rungs
        ],
    }
    with config_path.open("w", encoding="utf-8") as fh:
        json.dump(config, fh, indent=2)

    print(f"  Saved results to {output_dir}/")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def main() -> int:
    parser = argparse.ArgumentParser(description="Saturation ladder (Stage 1 only)")
    parser.add_argument(
        "--model",
        default="google/gemini-3-flash-preview",
        help="LLM model identifier",
    )
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--replicates", type=int, default=1)
    args = parser.parse_args()

    from alspec.eval.domains import DOMAINS

    if args.dry_run:
        _dry_run(RUNGS, DOMAINS, args.replicates)
        return 0

    timestamp = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_dir = Path(args.output_dir or f"results/saturation-s1-{timestamp}")

    from alspec.llm import AsyncLLMClient
    from alspec.result import Ok

    client_res = AsyncLLMClient.from_env()
    match client_res:
        case Ok(client):
            client._session_id = f"saturation-s1-{timestamp}"
        case _:
            print("Failed to init LLM client")
            return 1

    total_calls = len(RUNGS) * len(DOMAINS) * args.replicates
    all_records = []
    start = time.monotonic()

    for rung in RUNGS:
        logger.info("─" * 60)
        logger.info("  Rung: %s", rung["name"])
        logger.info("─" * 60)

        for rep in range(args.replicates):
            recs = await _run_rung_replicate(
                client,
                rung,
                DOMAINS,
                args.model,
                args.concurrency,
                rep,
                args.replicates,
                experiment_start=start,
                completed_before=len(all_records),
                total_calls=total_calls,
            )
            all_records.extend(recs)

    _print_comparison_table(RUNGS, all_records)
    _save_results(output_dir, all_records, RUNGS, args.model, timestamp, args.replicates)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
