"""Effect estimation and table rendering for DoE results.

Computes main effects and 2-factor interactions from a list of Stage1Score
objects + the design matrix (factor level assignments per trial).

Effect computation follows the standard two-level factorial contrast method:

    Main effect of X = mean(Y | X=+1) − mean(Y | X=−1)

    2FI of X×Y = 0.5 × [
        (mean(Y | X=+1, Y=+1) + mean(Y | X=−1, Y=−1))
      − (mean(Y | X=+1, Y=−1) + mean(Y | X=−1, Y=+1))
    ]

Standard error is estimated from replicate variance (pooled within-run variance).
p-values come from a two-sample t-test against zero effect.
"""

from __future__ import annotations

import csv
import json
import math
import statistics
from dataclasses import dataclass
from pathlib import Path

from alspec.eval.stage1_score import Stage1Score
from alspec.eval.stage4_score import Stage4Score


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MainEffect:
    """Estimated main effect of one factor on one response."""

    factor_label: str
    chunk_names: tuple[str, ...]
    response: str  # "health", "parse_rate", "wf_rate", "intrinsic_health", "coverage"
    effect: float
    se: float
    p_value: float | None


@dataclass(frozen=True)
class InteractionEffect:
    """Estimated 2-factor interaction effect on a response."""

    factor_a: str
    factor_b: str
    response: str
    effect: float
    se: float
    p_value: float | None


@dataclass(frozen=True)
class AnalysisResult:
    main_effects: tuple[MainEffect, ...]
    interactions: tuple[InteractionEffect, ...]


# ---------------------------------------------------------------------------
# Effect computation
# ---------------------------------------------------------------------------


def _p_value_from_t(effect: float, se: float, n_samples: int) -> float | None:
    """Two-sided p-value from a t-statistic.

    Returns None when se is essentially zero (no variance).
    """
    if se <= 1e-12:
        return None
    t_stat = abs(effect) / se
    # Degrees of freedom ≈ n_samples - 1 (Welch-style, pooled over levels)
    df = max(n_samples - 1, 1)
    # Use scipy if available for accuracy, otherwise normal approximation
    try:
        from scipy.stats import t as t_dist  # type: ignore[import-untyped]

        p = 2.0 * t_dist.sf(t_stat, df)
        return float(p)
    except ImportError:
        # Normal approximation (valid for large n)
        import math

        p = 2.0 * (1.0 - _normal_cdf(t_stat))
        return p


def _normal_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _extract_response(score: Stage1Score | Stage4Score, response: str) -> float:
    match response:
        case "health":
            if isinstance(score, Stage4Score):
                return score.intrinsic_health
            return score.health
        case "intrinsic_health":
            return score.intrinsic_health
        case "parse_rate":
            return 1.0 if score.parse_success else 0.0
        case "wf_rate":
            return 1.0 if score.well_formed else 0.0
        case "coverage":
            return getattr(score, "coverage_ratio", 0.0)
        case _:
            raise ValueError(f"Unknown response: {response!r}")


def compute_main_effects(
    scores: list[Stage1Score | Stage4Score],
    factor_labels: list[str],
    chunk_names_by_label: dict[str, list[str]],
    responses: list[str] | None = None,
) -> list[MainEffect]:
    """Compute all main effects for each factor × response combination.

    Parameters
    ----------
    scores:
        All Stage1Score or Stage4Score objects from the experiment.
    factor_labels:
        Ordered list of factor labels (e.g. ["A", "B", ...]).
    chunk_names_by_label:
        Maps factor label → list of chunk names it controls.
    responses:
        List of response names to estimate effects for.
        Defaults to ["health", "intrinsic_health", "parse_rate", "wf_rate", "coverage"].
    """
    if responses is None:
        responses = ["health", "intrinsic_health", "parse_rate", "wf_rate", "coverage"]
        # Remove responses that don't exist on the score objects
        if responses:
            first = scores[0]
            valid = []
            for r in responses:
                try:
                    _extract_response(first, r)
                    valid.append(r)
                except (ValueError, AttributeError):
                    pass
            responses = valid

    effects: list[MainEffect] = []

    for factor in factor_labels:
        chunks = chunk_names_by_label.get(factor, [])
        chunk_tuple = tuple(chunks)

        for response in responses:
            high_vals: list[float] = []
            low_vals: list[float] = []

            for s in scores:
                level = s.factor_levels.get(factor)
                if level is None:
                    continue
                y = _extract_response(s, response)
                if level == 1:
                    high_vals.append(y)
                else:
                    low_vals.append(y)

            if not high_vals or not low_vals:
                continue

            mean_high = statistics.mean(high_vals)
            mean_low = statistics.mean(low_vals)
            eff = mean_high - mean_low

            # Pooled standard error
            var_high = statistics.variance(high_vals) if len(high_vals) > 1 else 0.0
            var_low = statistics.variance(low_vals) if len(low_vals) > 1 else 0.0
            n = len(high_vals) + len(low_vals)
            pooled_var = (var_high / len(high_vals) + var_low / len(low_vals))
            se = math.sqrt(max(pooled_var, 0.0))

            p_val = _p_value_from_t(eff, se, n)

            effects.append(
                MainEffect(
                    factor_label=factor,
                    chunk_names=chunk_tuple,
                    response=response,
                    effect=eff,
                    se=se,
                    p_value=p_val,
                )
            )

    return effects


def compute_interactions(
    scores: list[Stage1Score | Stage4Score],
    factor_labels: list[str],
    responses: list[str] | None = None,
) -> list[InteractionEffect]:
    """Compute all 2-factor interaction effects."""
    if responses is None:
        responses = ["health", "intrinsic_health", "parse_rate", "wf_rate", "coverage"]
        # Remove responses that don't exist on the score objects
        if responses:
            first = scores[0]
            valid = []
            for r in responses:
                try:
                    _extract_response(first, r)
                    valid.append(r)
                except (ValueError, AttributeError):
                    pass
            responses = valid

    interactions: list[InteractionEffect] = []
    n = len(factor_labels)

    for i in range(n):
        for j in range(i + 1, n):
            fa, fb = factor_labels[i], factor_labels[j]

            for response in responses:
                # Collect (Y, level_a, level_b) triples
                pp: list[float] = []  # A=+1, B=+1
                pm: list[float] = []  # A=+1, B=-1
                mp: list[float] = []  # A=-1, B=+1
                mm: list[float] = []  # A=-1, B=-1

                for s in scores:
                    la = s.factor_levels.get(fa)
                    lb = s.factor_levels.get(fb)
                    if la is None or lb is None:
                        continue
                    y = _extract_response(s, response)

                    match (la, lb):
                        case (1, 1):
                            pp.append(y)
                        case (1, -1):
                            pm.append(y)
                        case (-1, 1):
                            mp.append(y)
                        case (-1, -1):
                            mm.append(y)

                if not (pp and pm and mp and mm):
                    continue

                eff = 0.5 * (
                    (statistics.mean(pp) + statistics.mean(mm))
                    - (statistics.mean(pm) + statistics.mean(mp))
                )

                # Variance estimate (pooled across cells)
                all_vars = []
                for group in (pp, pm, mp, mm):
                    if len(group) > 1:
                        all_vars.append(statistics.variance(group) / len(group))
                pooled = sum(all_vars) / len(all_vars) if all_vars else 0.0
                se = math.sqrt(max(pooled, 0.0))
                total_n = len(pp) + len(pm) + len(mp) + len(mm)
                p_val = _p_value_from_t(eff, se, total_n)

                interactions.append(
                    InteractionEffect(
                        factor_a=fa,
                        factor_b=fb,
                        response=response,
                        effect=eff,
                        se=se,
                        p_value=p_val,
                    )
                )

    return interactions


# ---------------------------------------------------------------------------
# File I/O
# ---------------------------------------------------------------------------


def load_scores_from_jsonl(path: Path) -> list[Stage1Score | Stage4Score]:
    """Load all score objects from a scores.jsonl file."""
    scores: list[Stage1Score | Stage4Score] = []
    with path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            data = json.loads(line)
            if "intrinsic_health" in data and "coverage_ratio" in data:
                scores.append(Stage4Score(**data))
            else:
                scores.append(Stage1Score(**data))
    return scores


def load_design_matrix(path: Path) -> dict[int, dict[str, int]]:
    """Load the design matrix CSV → {trial_id: {factor_label: level}}."""
    result: dict[int, dict[str, int]] = {}
    with path.open() as f:
        reader = csv.DictReader(f)
        for row in reader:
            tid = int(row["trial_id"])
            levels = {k: int(v) for k, v in row.items() if k != "trial_id"}
            result[tid] = levels
    return result


def write_effects_csv(
    main_effects: list[MainEffect],
    interactions: list[InteractionEffect],
    path: Path,
) -> None:
    """Write effects.csv with all main effects and interactions."""
    with path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            ["type", "factors", "chunks", "response", "effect", "se", "p_value"]
        )
        for me in sorted(main_effects, key=lambda x: -abs(x.effect)):
            p_str = f"{me.p_value:.4f}" if me.p_value is not None else "NA"
            writer.writerow([
                "main",
                me.factor_label,
                "+".join(me.chunk_names),
                me.response,
                f"{me.effect:.6f}",
                f"{me.se:.6f}",
                p_str,
            ])
        for ie in sorted(interactions, key=lambda x: -abs(x.effect)):
            p_str = f"{ie.p_value:.4f}" if ie.p_value is not None else "NA"
            writer.writerow([
                "interaction",
                f"{ie.factor_a}x{ie.factor_b}",
                "",
                ie.response,
                f"{ie.effect:.6f}",
                f"{ie.se:.6f}",
                p_str,
            ])


# ---------------------------------------------------------------------------
# Console table rendering
# ---------------------------------------------------------------------------


def _p_str(p: float | None) -> str:
    if p is None:
        return "    NA"
    if p < 0.001:
        return "<0.001"
    return f"{p:.3f}"


def print_effects_table(
    main_effects: list[MainEffect],
    interactions: list[InteractionEffect],
    *,
    response: str = "health",
    interaction_threshold: float = 0.02,
) -> None:
    """Print a formatted effects table to stdout for a single response variable."""
    mes = [m for m in main_effects if m.response == response]
    ies = [i for i in interactions if i.response == response]

    mes = sorted(mes, key=lambda x: -abs(x.effect))
    ies = sorted(ies, key=lambda x: -abs(x.effect))

    title = f" Effects on {response} "
    bar = "═" * max(len(title) + 4, 50)
    print(f"\n╔{bar}╗")
    print(f"║  {title.center(len(bar) - 2)}  ║")
    print(f"╚{bar}╝")

    if not mes:
        print("  (no effects computed)")
        return

    print(
        f"  {'Factor':<8} {'Chunk(s)':<40} {'Effect':>8} {'SE':>7} {'p-value':>8}"
    )
    print(f"  {'─'*8} {'─'*40} {'─'*8} {'─'*7} {'─'*8}")

    for m in mes:
        chunk_str = ", ".join(m.chunk_names)
        if len(chunk_str) > 38:
            chunk_str = chunk_str[:35] + "..."
        sign = "+" if m.effect >= 0 else ""
        sig_marker = " *" if (m.p_value is not None and m.p_value < 0.05) else "  "
        print(
            f"  {m.factor_label:<8} {chunk_str:<40} "
            f"{sign}{m.effect:>7.4f} {m.se:>7.4f} {_p_str(m.p_value):>8}{sig_marker}"
        )

    sig_ies = [i for i in ies if abs(i.effect) > interaction_threshold]
    if sig_ies:
        print(
            f"\n  Key 2-Factor Interactions (|effect| > {interaction_threshold:.2f} on {response}):"
        )
        print(
            f"  {'Factors':<10} {'Effect':>8} {'SE':>7} {'p-value':>8}"
        )
        print(f"  {'─'*10} {'─'*8} {'─'*7} {'─'*8}")
        for ie in sig_ies:
            sign = "+" if ie.effect >= 0 else ""
            sig_marker = " *" if (ie.p_value is not None and ie.p_value < 0.05) else "  "
            print(
                f"  {ie.factor_a}×{ie.factor_b:<8} "
                f"{sign}{ie.effect:>7.4f} {ie.se:>7.4f} {_p_str(ie.p_value):>8}{sig_marker}"
            )
    elif ies:
        print(
            f"\n  No 2-factor interactions exceed |effect| > {interaction_threshold:.2f}."
        )


def print_all_effects_tables(
    main_effects: list[MainEffect],
    interactions: list[InteractionEffect],
    *,
    health_threshold: float = 0.02,
    parse_threshold: float = 0.03,
) -> None:
    """Print three ranked tables: parse_rate, wf_rate, and health.

    This is the main analysis output — one table per response variable, ordered
    from coarse (parse success) to fine (composite health score).
    """
    print_effects_table(
        main_effects, interactions,
        response="parse_rate",
        interaction_threshold=parse_threshold,
    )
    print_effects_table(
        main_effects, interactions,
        response="wf_rate",
        interaction_threshold=parse_threshold,
    )
    print_effects_table(
        main_effects, interactions,
        response="health",
        interaction_threshold=health_threshold,
    )



# ---------------------------------------------------------------------------
# High-level analysis entrypoint
# ---------------------------------------------------------------------------


def analyze_results(results_dir: Path) -> AnalysisResult:
    """Load scores.jsonl and compute all effects.

    Returns an AnalysisResult with all main effects and interactions.
    Also writes effects.csv to results_dir.
    """
    scores_path = results_dir / "scores.jsonl"

    if not scores_path.exists():
        raise FileNotFoundError(f"scores.jsonl not found in {results_dir}")

    scores = load_scores_from_jsonl(scores_path)

    if not scores:
        raise ValueError(f"No scores found in {scores_path}")

    # Determine factor labels from the scores themselves (first populated score)
    factor_labels: list[str] = []
    for s in scores:
        if s.factor_levels:
            factor_labels = sorted(s.factor_levels.keys())
            break

    if not factor_labels:
        raise ValueError(
            "No factor_levels found in any score. "
            "Was the experiment run with factor-level tracking enabled?"
        )

    # Build a simple chunk_names_by_label from the frozen config if available
    chunk_names_by_label: dict[str, list[str]] = {
        lbl: [lbl] for lbl in factor_labels
    }
    config_toml = results_dir / "config.toml"
    if config_toml.exists():
        try:
            import tomllib
            from alspec.prompt_chunks import ChunkId

            with config_toml.open("rb") as f:
                raw = tomllib.load(f)
            factors_raw = raw.get("chunks", {}).get("factors", {})
            for lbl, chunk_names in factors_raw.items():
                if isinstance(chunk_names, list):
                    # Validate and resolve names
                    resolved = []
                    for name in chunk_names:
                        if isinstance(name, str):
                            try:
                                ChunkId[name]
                                resolved.append(name)
                            except KeyError:
                                pass
                    if resolved:
                        chunk_names_by_label[lbl] = resolved
        except Exception:
            pass  # Use default label-based names

    main_effects = compute_main_effects(
        scores, factor_labels, chunk_names_by_label
    )
    interactions = compute_interactions(scores, factor_labels)

    # Write effects.csv
    write_effects_csv(main_effects, interactions, results_dir / "effects.csv")

    return AnalysisResult(
        main_effects=tuple(main_effects),
        interactions=tuple(interactions),
    )

