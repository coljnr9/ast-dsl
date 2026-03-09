#!/usr/bin/env python3
"""Run a battery of novel domains through the full pipeline with structured reporting.

Usage:
    uv run python scripts/run_novel_battery.py
    uv run python scripts/run_novel_battery.py --reps 3
    uv run python scripts/run_novel_battery.py --domains env-sensor,thermocouple
    uv run python scripts/run_novel_battery.py --desc-dir sensor-descs --ref-dir sensor-refs
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

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-5s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

DEFAULT_DOMAINS = [
    "env-sensor",
    "color-sensor",
    "thermocouple",
    "adc-channel",
    "moisture-controller",
]
DEFAULT_MODEL = "google/gemini-3-flash-preview"
DEFAULT_LENS = "entity_lifecycle"
DEFAULT_DESC_DIR = "sensor-descs"
DEFAULT_REF_DIR = "sensor-refs"


async def run_one(
    client,
    domain: str,
    description: str,
    sources: list[Path] | None,
    model: str,
    lens: str,
    rep: int,
) -> dict:
    """Run one (domain, rep) trial. Returns a structured result dict."""
    from alspec.pipeline import run_pipeline

    start = time.time()
    result = await run_pipeline(
        client=client,
        domain_id=domain,
        domain_description=description,
        model=model,
        lens=lens,
        sources=sources,
    )
    elapsed = time.time() - start

    row = {
        "domain": domain,
        "rep": rep,
        "success": result.success,
        "error_stage": result.error_stage or "",
        "error": (result.error or "")[:200],
        "elapsed_s": round(elapsed, 1),
        # Signature info
        "sorts": len(result.signature.sorts) if result.signature else 0,
        "functions": len(result.signature.functions) if result.signature else 0,
        "predicates": len(result.signature.predicates) if result.signature else 0,
        "generated_sorts": (
            list(result.signature.generated_sorts.keys()) if result.signature else []
        ),
        # Score info
        "well_formed": False,
        "health": 0.0,
        "coverage_ratio": None,
        "covered_cells": 0,
        "total_cells": 0,
        "unmatched_axioms": 0,
        "axiom_count": 0,
        "error_count": 0,
        "warning_count": 0,
    }

    if result.score:
        s = result.score
        row.update({
            "well_formed": s.well_formed,
            "health": round(s.health, 3),
            "coverage_ratio": round(s.coverage_ratio, 3) if s.coverage_ratio is not None else None,
            "covered_cells": s.covered_cell_count,
            "total_cells": s.obligation_cell_count,
            "unmatched_axioms": s.unmatched_axiom_count,
            "axiom_count": s.axiom_count,
            "error_count": s.error_count,
            "warning_count": s.warning_count,
        })

    return row, result


def print_row(row: dict) -> None:
    """Print a single result row."""
    d = row["domain"]
    rep = row["rep"]

    if not row["success"]:
        stage = row["error_stage"]
        err = row["error"][:80]
        print(f"  ✗ {d} rep={rep}  FAILED at {stage}: {err}")
        return

    wf = "✓" if row["well_formed"] else "✗"
    cov = row["coverage_ratio"]
    cov_str = f"{cov:.1%}" if cov is not None else "n/a"
    cells = f"{row['covered_cells']}/{row['total_cells']}"
    health = row["health"]
    ax = row["axiom_count"]
    errs = row["error_count"]
    elapsed = row["elapsed_s"]

    status = "✓" if row["well_formed"] and (cov is None or cov > 0.9) else "⚠"
    print(f"  {status} {d} rep={rep}  WF:{wf}  coverage:{cov_str} ({cells})  health:{health}  axioms:{ax}  errors:{errs}  {elapsed}s")


def print_summary(rows: list[dict]) -> None:
    """Print a summary table."""
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)

    # Per-domain aggregation
    domains = sorted(set(r["domain"] for r in rows))
    print(f"\n{'domain':<25} {'success':>8} {'WF':>5} {'coverage':>10} {'cells':>10} {'axioms':>8} {'errors':>7}")
    print("-" * 80)

    for domain in domains:
        drows = [r for r in rows if r["domain"] == domain]
        n = len(drows)
        n_ok = sum(1 for r in drows if r["success"])
        n_wf = sum(1 for r in drows if r["well_formed"])

        covs = [r["coverage_ratio"] for r in drows if r["coverage_ratio"] is not None]
        cov_str = f"{sum(covs)/len(covs):.1%}" if covs else "n/a"

        cells = [f"{r['covered_cells']}/{r['total_cells']}" for r in drows if r["total_cells"] > 0]
        cells_str = cells[0] if len(set(cells)) == 1 else ",".join(cells)

        axs = [r["axiom_count"] for r in drows if r["success"]]
        ax_str = str(axs[0]) if len(set(axs)) == 1 else f"{min(axs)}-{max(axs)}" if axs else "0"

        errs = [r["error_count"] for r in drows if r["success"]]
        err_str = str(errs[0]) if len(set(errs)) == 1 else f"{min(errs)}-{max(errs)}" if errs else "-"

        print(f"{domain:<25} {n_ok}/{n:>5} {n_wf}/{n:>3} {cov_str:>10} {cells_str:>10} {ax_str:>8} {err_str:>7}")

    # Totals
    total = len(rows)
    ok = sum(1 for r in rows if r["success"])
    wf = sum(1 for r in rows if r["well_formed"])
    all_covs = [r["coverage_ratio"] for r in rows if r["coverage_ratio"] is not None]
    mean_cov = sum(all_covs) / len(all_covs) if all_covs else 0

    print("-" * 80)
    print(f"{'TOTAL':<25} {ok}/{total:>5} {wf}/{total:>3} {mean_cov:>9.1%}")


async def main() -> int:
    parser = argparse.ArgumentParser(description="Run novel domain battery through alspec pipeline")
    parser.add_argument("--domains", type=str, default=None, help="Comma-separated domain list")
    parser.add_argument("--reps", type=int, default=1, help="Replicates per domain")
    parser.add_argument("--model", type=str, default=DEFAULT_MODEL)
    parser.add_argument("--lens", type=str, default=DEFAULT_LENS)
    parser.add_argument("--desc-dir", type=str, default=DEFAULT_DESC_DIR)
    parser.add_argument("--ref-dir", type=str, default=DEFAULT_REF_DIR)
    parser.add_argument("--output-dir", type=str, default=None)
    args = parser.parse_args()

    domains = args.domains.split(",") if args.domains else DEFAULT_DOMAINS
    desc_dir = Path(args.desc_dir)
    ref_dir = Path(args.ref_dir)

    timestamp = datetime.now(tz=timezone.utc).strftime("%Y%m%d-%H%M%S")
    outdir = Path(args.output_dir) if args.output_dir else Path(f"results/novel-battery-{timestamp}")
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "specs").mkdir(exist_ok=True)

    # LLM client
    from alspec.llm import AsyncLLMClient
    from alspec.result import Err, Ok

    client_res = AsyncLLMClient.from_env()
    match client_res:
        case Ok(client):
            pass
        case Err(e):
            print(f"Error creating LLM client: {e}", file=sys.stderr)
            return 1

    session_id = f"novel-battery-{timestamp}"
    try:
        client._session_id = session_id
    except AttributeError:
        pass

    print(f"Session: {session_id}")
    print(f"Output:  {outdir}")
    print(f"Domains: {', '.join(domains)}")
    print(f"Reps:    {args.reps}")
    print(f"Model:   {args.model}")
    print()

    all_rows: list[dict] = []

    for domain in domains:
        # Load description
        desc_file = desc_dir / f"{domain}.txt"
        if not desc_file.exists():
            print(f"⚠ Skipping {domain} — no {desc_file}")
            continue
        description = desc_file.read_text().strip()

        # Load source references
        sources = None
        ref_file = ref_dir / f"{domain}.txt"
        if ref_file.exists():
            sources = [ref_file]

        for rep in range(args.reps):
            row, result = await run_one(
                client=client,
                domain=domain,
                description=description,
                sources=sources,
                model=args.model,
                lens=args.lens,
                rep=rep,
            )
            all_rows.append(row)
            print_row(row)

            # Save spec code if available
            if result.spec_code:
                spec_path = outdir / "specs" / f"{domain}-rep{rep}.py"
                spec_path.write_text(result.spec_code)

            # Save signature code if available (even on Stage 4 failure)
            if result.signature_code and not result.spec_code:
                sig_path = outdir / "specs" / f"{domain}-rep{rep}-sig-only.py"
                sig_path.write_text(result.signature_code)

    # Write CSV
    csv_path = outdir / "summary.csv"
    if all_rows:
        fieldnames = list(all_rows[0].keys())
        with open(csv_path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
            for row in all_rows:
                # Serialize lists for CSV
                row_copy = dict(row)
                for k, v in row_copy.items():
                    if isinstance(v, list):
                        row_copy[k] = ";".join(v)
                w.writerow(row_copy)

    # Write JSON for full detail
    json_path = outdir / "results.json"
    with open(json_path, "w") as f:
        json.dump(all_rows, f, indent=2, default=str)

    print_summary(all_rows)
    print(f"\nCSV:   {csv_path}")
    print(f"JSON:  {json_path}")
    print(f"Specs: {outdir / 'specs'}/")

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
