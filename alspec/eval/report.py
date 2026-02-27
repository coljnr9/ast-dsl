import csv
from typing import TextIO

from alspec.check import Severity
from alspec.eval.domains import DOMAINS
from alspec.eval.harness import EvalRun


def print_summary_table(run: EvalRun, model: str, out: TextIO) -> None:
    """Print the summary table for a single model."""
    out.write(f"\n{'=' * 74}\n")
    out.write(f"  Eval Run: {run.timestamp}  |  Model: {model}\n")
    out.write(f"  Prompt: {run.prompt_version}\n")
    out.write(f"{'=' * 74}\n\n")

    out.write(
        "  Domain                  │ Parse │ WF  │ Health │ Obligations │ Axioms │ Errors │ Warnings\n"
    )
    out.write(
        "  ────────────────────────┼───────┼─────┼────────┼─────────────┼────────┼────────┼─────────\n"
    )

    results = [r for r in run.results if r.model == model]

    total_parse = 0
    total_wf = 0
    total_health = 0.0
    total_obs_covered = 0
    total_obs_total = 0
    total_axioms = 0
    total_errors = 0
    total_warnings = 0

    for domain in DOMAINS:
        for result in results:
            if result.domain_id == domain.id:
                break
        else:
            continue

        parse_mark = " ✓  " if result.success else " ✗  "
        if result.success:
            total_parse += 1

        wf_mark = " — "
        health_str = " —  "
        obs_str = "   —   "
        ax_str = " —  "
        err_str = " — "
        warn_str = " — "

        match result.score:
            case None:
                pass
            case score:
                wf_mark = " ✓ " if score.well_formed else " ✗ "
                if score.well_formed:
                    total_wf += 1
                health_str = f"{score.health:4.2f}"
                obs_str = f"{score.obligation_covered:>3}/{score.obligation_total:<3}"
                ax_str = f"{score.axiom_count:>3} "
                err_str = f" {score.error_count:>2} "
                warn_str = f" {score.warning_count:>2} "

                total_health += score.health
                total_obs_covered += score.obligation_covered
                total_obs_total += score.obligation_total
                total_axioms += score.axiom_count
                total_errors += score.error_count
                total_warnings += score.warning_count

        out.write(
            f"  {domain.id:<24}│ {parse_mark}│ {wf_mark} │  {health_str}  │   {obs_str}   │   {ax_str} │  {err_str}  │  {warn_str}\n"
        )

    out.write(
        "  ────────────────────────┼───────┼─────┼────────┼─────────────┼────────┼────────┼─────────\n"
    )

    success_count = sum(1 for r in results if r.success)
    parse_pct = (total_parse / len(results)) * 100 if results else 0.0
    wf_pct = (total_wf / success_count) * 100 if success_count else 0.0
    mean_health = total_health / len(results) if results else 0.0
    mean_obs = (total_obs_covered / total_obs_total) * 100 if total_obs_total else 0.0

    out.write(
        f"  TOTALS                  │ {total_parse:>2}/{len(results):<2} │{total_wf:>2}/{success_count:<2}│  {mean_health:4.2f}  │ {total_obs_covered:>3}/{total_obs_total:<3}     │  {total_axioms:>3}   │  {total_errors:>2}   │  {total_warnings:>2}\n\n"
    )

    out.write(f"  Parse rate:        {parse_pct:5.1f}%\n")
    out.write(f"  Well-formed rate:  {wf_pct:5.1f}%\n")
    out.write(f"  Mean health:       {mean_health:4.2f}\n")
    out.write(f"  Mean obligation:   {mean_obs:5.1f}%\n\n")


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
        # Handle ties or empty
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
            out.write(f"  {result.domain_id} (health: {health:.2f})\n")
            if not result.success:
                out.write(f"    ✗ Parse failed: {result.parse_error}\n")
                continue

            match result.score:
                case None:
                    out.write("    ✗ Missing score despite success\n")
                case score:
                    for diag in score.diagnostics:
                        if diag.severity == Severity.ERROR:
                            out.write(f"    ✗ [{diag.check}] {diag.message}\\n")
                        else:
                            out.write(f"    ⚠ [{diag.check}] {diag.message}\\n")
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
                "obligation_ratio",
                "error_count",
                "warning_count",
                "axiom_count",
                "sort_count",
                "function_count",
                "predicate_count",
                "latency_ms",
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
                        0.0,
                        0,
                        0,
                        0,
                        0,
                        0,
                        0,
                        result.latency_ms,
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
                        score.obligation_ratio,
                        score.error_count,
                        score.warning_count,
                        score.axiom_count,
                        score.sort_count,
                        score.function_count,
                        score.predicate_count,
                        result.latency_ms,
                    ]
                )
