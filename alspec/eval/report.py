import csv
import math
from typing import TextIO

from alspec.check import Severity
from alspec.eval.domains import DOMAINS
from alspec.eval.harness import EvalResult, EvalRun


def print_summary_table(run: EvalRun, model: str, out: TextIO) -> None:
    """Print the summary table for a single model."""
    out.write(f"\n{'=' * 62}\n")
    out.write(f"  Eval Run: {run.timestamp}  |  Model: {model}\n")
    out.write(f"  Prompt: {run.prompt_version}\n")
    out.write(f"{'=' * 71}\n\n")

    out.write(
        "  Domain                  │ Parse │ WF  │ Health │ Intr  │ Axioms │ Errors │ Warnings │ Cov\n"
    )
    out.write(
        "  ────────────────────────┼───────┼─────┼────────┼───────┼────────┼────────┼──────────┼────────\n"
    )

    results = [r for r in run.results if r.model == model]

    total_parse = 0
    total_wf = 0
    total_health = 0.0
    total_axioms = 0
    total_errors = 0
    total_warnings = 0
    total_covered = 0
    total_cells = 0
    total_intrinsic = 0.0

    for domain in DOMAINS:
        for result in results:
            if result.domain_id == domain.id:
                break
        else:
            continue

        parse_mark = " ✓ " if result.success else " ✗ "
        if result.success:
            total_parse += 1

        wf_mark = " — "
        health_str = " —  "
        ax_str = " —  "
        err_str = " — "
        warn_str = " — "
        intr_str = f"{result.intrinsic_health:4.2f} "
        cov_str = "  —   "

        match result.score:
            case None:
                pass
            case score:
                wf_mark = " ✓ " if score.well_formed else " ✗ "
                if score.well_formed:
                    total_wf += 1
                health_str = f"{score.health:4.2f}"
                ax_str = f"{score.axiom_count:>3} "
                err_str = f" {score.error_count:>2} "
                warn_str = f" {score.warning_count:>2} "

                if score.obligation_cell_count > 0:
                    cov_str = f" {score.covered_cell_count:>2}/{score.obligation_cell_count:<2} "
                    total_covered += score.covered_cell_count
                    total_cells += score.obligation_cell_count

                total_health += score.health
                total_axioms += score.axiom_count
                total_errors += score.error_count
                total_warnings += score.warning_count
                total_intrinsic += result.intrinsic_health

        out.write(
            f"  {domain.id:<24}│  {parse_mark}  │ {wf_mark} │  {health_str}  │ {intr_str} │   {ax_str} │  {err_str}  │   {warn_str}   │ {cov_str}\n"
        )

    out.write(
        "  ────────────────────────┼───────┼─────┼────────┼───────┼────────┼────────┼──────────┼────────\n"
    )

    success_count = sum(1 for r in results if r.success)
    parse_pct = (total_parse / len(results)) * 100 if results else 0.0
    wf_pct = (total_wf / success_count) * 100 if success_count else 0.0
    mean_health = total_health / len(results) if results else 0.0
    mean_intrinsic = total_intrinsic / len(results) if results else 0.0

    total_cov_str = "—"
    if total_cells > 0:
        total_cov_str = f"{total_covered}/{total_cells}"

    out.write(
        f"  TOTALS                  │ {total_parse:>2}/{len(results):<2} │{total_wf:>2}/{success_count:<2}│  {mean_health:4.2f}  │  {mean_intrinsic:4.2f} │  {total_axioms:>3}   │  {total_errors:>2}   │  {total_warnings:>2}  │ {total_cov_str}\n\n"
    )

    out.write(f"  Parse rate:        {parse_pct:5.1f}%\n")
    out.write(f"  Well-formed rate:  {wf_pct:5.1f}%\n")
    out.write(f"  Mean health:       {mean_health:4.2f} (golden), {mean_intrinsic:4.2f} (intrinsic)\n")
    if total_cells > 0:
        mean_cov = (total_covered / total_cells) * 100
        out.write(f"  Mean coverage:     {mean_cov:5.1f}%  ({total_covered}/{total_cells} cells across {total_parse} parsed specs)\n")
    out.write("\n")


def print_multi_model_comparison(run: EvalRun, out: TextIO) -> None:
    """Print a comparison table of health scores across models."""
    if len(run.models) < 2:
        return

    out.write("  Multi-Model Comparison\n")
    out.write("  " + "─" * 72 + "\n")

    header = f"  {'Domain':<20}"
    for m in run.models:
        header += f"│ {m.split('/')[-1][:12]:<12} "
    out.write(f"{header}\n")

    sep = "  " + "─" * 20
    for _ in run.models:
        sep += "┼" + "─" * 14
    out.write(f"{sep}\n")

    means: dict[str, float] = {m: 0.0 for m in run.models}

    for domain in DOMAINS:
        row = f"  {domain.id:<20}"
        has_result = False
        for m in run.models:
            for result in run.results:
                if result.domain_id == domain.id and result.model == m:
                    break
            else:
                result = None

            if result:
                has_result = True
                match result.score:
                    case None:
                        row += f"│ {'0.00':<12} "
                    case score:
                        row += f"│ {score.health:<12.2f} "
                        means[m] += score.health
            else:
                row += f"│ {'—':<12} "
        if has_result:
            out.write(f"{row}\n")

    out.write(f"{sep}\n")
    mean_row = f"  {'MEAN':<20}"
    for m in run.models:
        model_results = [r for r in run.results if r.model == m]
        mean = means[m] / len(model_results) if model_results else 0.0
        mean_row += f"│ {mean:<12.2f} "
    out.write(f"{mean_row}\n\n")


def print_feature_coverage(run: EvalRun, out: TextIO) -> None:
    """Print the feature coverage report across all models."""
    out.write("  Feature Coverage Report\n")
    out.write("  Feature          │ Domains │ Mean Health │ Worst Domain\n")
    out.write("  ─────────────────┼─────────┼────────────┼─────────────\n")

    all_features = set()
    for domain in DOMAINS:
        for feat in domain.expected_features:
            all_features.add(feat)

    for feat in sorted(list(all_features)):
        relevant_domains = [d for d in DOMAINS if feat in d.expected_features]
        num_domains = len(relevant_domains)

        domain_healths: dict[str, float] = {}
        for d in relevant_domains:
            domain_results = [r for r in run.results if r.domain_id == d.id]
            if not domain_results:
                domain_healths[d.id] = 0.0
            else:
                healths = [r.score.health if r.score else 0.0 for r in domain_results]
                domain_healths[d.id] = sum(healths) / len(healths)

        if not domain_healths:
            continue

        mean_health = sum(domain_healths.values()) / len(domain_healths)
        worst_domain = ""
        worst_health = 100.0
        for k, v in domain_healths.items():
            if v < worst_health:
                worst_health = v
                worst_domain = k

        out.write(
            f"  {feat:<17}│ {num_domains:>2}      │   {mean_health:4.2f}     │ {worst_domain} ({worst_health:.2f})\n"
        )
    out.write("\n")


def print_detailed_diagnostics(run: EvalRun, out: TextIO) -> None:
    """Print per-domain breakdown for verbose mode."""
    for model in run.models:
        out.write(f"\n--- Diagnostics for {model} ---\n")
        results = [r for r in run.results if r.model == model]
        if not results:
            continue

        for result in results:
            health = result.score.health if result.score else 0.0
            out.write(f"  {result.domain_id} (health: {health:.2f}, intrinsic: {result.intrinsic_health:.2f})\n")
            out.write(f"    Tiers: p={result.tier1_parse:.2f} s={result.tier2_sig:.2f} o={result.tier3_oblig:.2f} b={result.tier4_balance:.2f} c={result.tier5_complexity:.2f}\n")

            if not result.success:
                out.write(f"    ✗ Parse failed:   {result.parse_error}\n")
                match result.checker_error:
                    case str(err):
                        out.write(f"    ✗ Checker error: {err}\n")
                    case _:
                        pass
            else:
                match result.score:
                    case None:
                        out.write("    ✗ Missing score despite success\n")
                    case score:
                        for diag in score.diagnostics:
                            if diag.severity == Severity.ERROR:
                                out.write(f"    ✗ [{diag.check}] {diag.message}\n")
                            else:
                                out.write(f"    ⚠ [{diag.check}] {diag.message}\n")

            match result.analysis:
                case str(analysis):
                    truncated = analysis[:2000]
                    suffix = "... [truncated]" if len(analysis) > 2000 else ""
                    out.write(f"\n    --- Analysis ---\n")
                    for line in truncated.splitlines():
                        out.write(f"    {line}\n")
                    if suffix:
                        out.write(f"    {suffix}\n")
                case _:
                    pass

            out.write("\n")


def export_csv(run: EvalRun, path: str) -> None:
    """Export the evaluation run to a CSV file."""
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "timestamp",
                "model",
                "prompt_version",
                "domain_id",
                "domain_complexity",
                "success",
                "well_formed",
                "health",
                "intrinsic_health",
                "error_count",
                "warning_count",
                "axiom_count",
                "sort_count",
                "function_count",
                "predicate_count",
                "latency_ms",
                "failure_category",
            ]
        )

        for result in run.results:
            domain = None
            for d in DOMAINS:
                if d.id == result.domain_id:
                    domain = d
                    break

            complexity = domain.complexity if domain else 0

            if not result.success or result.score is None:
                writer.writerow(
                    [
                        run.timestamp,
                        result.model,
                        run.prompt_version,
                        result.domain_id,
                        complexity,
                        result.success,
                        False,
                        0.0,
                        result.intrinsic_health,
                        0,
                        0,
                        0,
                        0,
                        0,
                        0,
                        result.latency_ms,
                        result.failure_category,
                    ]
                )
            else:
                score = result.score
                writer.writerow(
                    [
                        run.timestamp,
                        result.model,
                        run.prompt_version,
                        result.domain_id,
                        complexity,
                        result.success,
                        score.well_formed,
                        score.health,
                        result.intrinsic_health,
                        score.error_count,
                        score.warning_count,
                        score.axiom_count,
                        score.sort_count,
                        score.function_count,
                        score.predicate_count,
                        result.latency_ms,
                        result.failure_category,
                    ]
                )


def _rep_aggregate(results: list[EvalResult]) -> dict[str, float]:
    """Compute aggregate metrics for a single replicate's results."""
    total = len(results)
    if total == 0:
        return {
            "parse_rate": 0.0,
            "wf_rate": 0.0,
            "mean_golden": 0.0,
            "mean_intrinsic": 0.0,
            "total_axioms": 0.0,
            "total_errors": 0.0,
            "coverage_ratio": None,
        }

    parsed = [r for r in results if r.success]
    wf = [r for r in parsed if r.score and r.score.well_formed]
    golden_sum = sum(r.score.health for r in parsed if r.score)
    intrinsic_sum = sum(r.intrinsic_health for r in results)
    axiom_sum = float(sum(r.score.axiom_count for r in parsed if r.score))
    error_sum = float(sum(r.score.error_count for r in parsed if r.score))

    cells_total = sum(r.obligation_cell_count for r in parsed if r.score)
    cells_covered = sum(r.covered_cell_count for r in parsed if r.score)
    cov_ratio = (cells_covered / cells_total) if cells_total > 0 else None

    return {
        "parse_rate": len(parsed) / total,
        "wf_rate": len(wf) / len(parsed) if parsed else 0.0,
        "mean_golden": golden_sum / len(parsed) if parsed else 0.0,
        "mean_intrinsic": intrinsic_sum / total,
        "total_axioms": axiom_sum,
        "total_errors": error_sum,
        "coverage_ratio": cov_ratio,
    }


def _stats(values: list[float]) -> tuple[float, float, float, float]:
    """Return (mean, stddev, min, max) for a list of floats."""
    n = len(values)
    if n == 0:
        return 0.0, 0.0, 0.0, 0.0
    mean = sum(values) / n
    variance = sum((v - mean) ** 2 for v in values) / n if n > 1 else 0.0
    stddev = math.sqrt(variance)
    return mean, stddev, min(values), max(values)


def print_replicate_summary(
    all_results: list[EvalResult],
    replicates: int,
    out: TextIO,
) -> None:
    """Print aggregate stats across all replicates."""
    out.write(f"\n  {'\u2550' * 62}\n")
    out.write(f"  Aggregate Summary ({replicates} replicates)\n")
    out.write(f"  {'\u2550' * 62}\n\n")

    # Partition results by replicate number.
    by_rep: dict[int, list[EvalResult]] = {}
    for r in all_results:
        by_rep.setdefault(r.replicate, []).append(r)

    rep_aggs = [_rep_aggregate(by_rep[rep]) for rep in sorted(by_rep)]

    metrics: list[tuple[str, list[float], bool]] = [
        ("Parse rate",           [a["parse_rate"] for a in rep_aggs],       True),
        ("Well-formed rate",     [a["wf_rate"] for a in rep_aggs],          True),
        ("Golden health (mean)", [a["mean_golden"] for a in rep_aggs],      False),
        ("Intrinsic health",     [a["mean_intrinsic"] for a in rep_aggs],   False),
        ("Total axioms",         [a["total_axioms"] for a in rep_aggs],     False),
        ("Total errors",         [a["total_errors"] for a in rep_aggs],     False),
        ("Coverage ratio",       [a["coverage_ratio"] for a in rep_aggs],   True),
    ]

    out.write(f"  {'Metric':<22}│ {'Mean':>7} │ {'Stddev':>6} │ {'Min':>6} │ {'Max':>6}\n")
    out.write(f"  {'─' * 22}┼{'─' * 9}┼{'─' * 8}┼{'─' * 8}┼{'─' * 8}\n")

    for label, raw_values, is_pct in metrics:
        values = [v for v in raw_values if v is not None]
        mean, stddev, vmin, vmax = _stats(values)
        if is_pct:
            out.write(
                f"  {label:<22}│ {mean*100:6.1f}% │ {stddev*100:5.1f}% │ {vmin*100:5.1f}% │ {vmax*100:5.1f}%\n"
            )
        else:
            out.write(
                f"  {label:<22}│ {mean:>7.2f} │ {stddev:>6.2f} │ {vmin:>6.2f} │ {vmax:>6.2f}\n"
            )

    out.write(f"  {'─' * 22}┼{'─' * 9}┼{'─' * 8}┼{'─' * 8}┼{'─' * 8}\n")

    # Per-domain parse stability across replicates.
    all_domain_ids = sorted({r.domain_id for r in all_results})
    unstable: list[tuple[str, int, int]] = []  # (domain_id, parsed_count, n)
    for did in all_domain_ids:
        domain_results = [r for r in all_results if r.domain_id == did]
        n = max(r.replicate for r in domain_results)
        parsed_count = sum(1 for r in domain_results if r.success)
        if parsed_count != 0 and parsed_count != n:
            unstable.append((did, parsed_count, n))

    out.write("\n")
    if unstable:
        out.write("  Per-domain parse stability (domains with variance across replicates):\n")
        for did, parsed_count, n in unstable:
            out.write(f"    {did}: {parsed_count}/{n}\n")
    else:
        out.write("  All domains parsed consistently across all replicates.\n")
    out.write("\n")

    # Failure category breakdown across all replicates.
    from collections import Counter
    category_counts = Counter(r.failure_category for r in all_results)
    total_runs = len(all_results)

    out.write("  Failure taxonomy:\n")
    # Sort: 'pass' first, then alphabetical
    for cat in sorted(category_counts.keys(), key=lambda c: ("" if c == "pass" else c)):
        count = category_counts[cat]
        pct = count / total_runs * 100 if total_runs > 0 else 0.0
        out.write(f"    {cat:<35} {count:>3} ({pct:5.1f}%)\n")
    out.write("\n")


def export_combined_csv(
    all_results: list[EvalResult],
    run_timestamp: str,
    prompt_version: str,
    path: str,
) -> None:
    """Export all replicates into a single CSV with a 'replicate' column."""
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "timestamp",
                "replicate",
                "model",
                "prompt_version",
                "domain_id",
                "domain_complexity",
                "success",
                "well_formed",
                "health",
                "intrinsic_health",
                "error_count",
                "warning_count",
                "axiom_count",
                "sort_count",
                "function_count",
                "predicate_count",
                "latency_ms",
                "failure_category",
            ]
        )

        for result in all_results:
            domain = None
            for d in DOMAINS:
                if d.id == result.domain_id:
                    domain = d
                    break

            complexity = domain.complexity if domain else 0

            if not result.success or result.score is None:
                writer.writerow(
                    [
                        run_timestamp,
                        result.replicate,
                        result.model,
                        prompt_version,
                        result.domain_id,
                        complexity,
                        result.success,
                        False,
                        0.0,
                        result.intrinsic_health,
                        0,
                        0,
                        0,
                        0,
                        0,
                        0,
                        result.latency_ms,
                        result.failure_category,
                    ]
                )
            else:
                score = result.score
                writer.writerow(
                    [
                        run_timestamp,
                        result.replicate,
                        result.model,
                        prompt_version,
                        result.domain_id,
                        complexity,
                        result.success,
                        score.well_formed,
                        score.health,
                        result.intrinsic_health,
                        score.error_count,
                        score.warning_count,
                        score.axiom_count,
                        score.sort_count,
                        score.function_count,
                        score.predicate_count,
                        result.latency_ms,
                        result.failure_category,
                    ]
                )
