"""analyze_uncovered.py — Analyze uncovered-cell characterization output.

Reads results/stage4-characterize-v1/uncovered_cells.csv (or a path passed as
argv[1]) and prints four tables to stdout:

  Table 1 — By tier (fork-point decision table)
  Table 2 — By domain (sorted by uncovered count descending)
  Table 3 — By (observer, tier) — top 20 occurrences
  Table 4 — By dispatch

Ends with a fork-point summary: % of uncovered cells that are DOMAIN tier
(require genuine LLM reasoning) vs. mechanical (everything else).

Usage:
    python scripts/analyze_uncovered.py
    python scripts/analyze_uncovered.py results/stage4-characterize-v1/uncovered_cells.csv
"""

from __future__ import annotations

import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

# ---------------------------------------------------------------------------
# Load data
# ---------------------------------------------------------------------------

DEFAULT_CSV = Path("results/stage4-characterize-v1/uncovered_cells.csv")
DEFAULT_SCORES = Path("results/stage4-characterize-v1/scores.jsonl")


def _load_uncovered(csv_path: Path) -> list[dict[str, str]]:
    with csv_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader)


def _load_scores(scores_path: Path) -> list[dict]:
    records: list[dict] = []
    if not scores_path.exists():
        return records
    with scores_path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

_COL_SEP = " | "


def _pad(s: str, width: int) -> str:
    return s.ljust(width)


def _right(s: str, width: int) -> str:
    return s.rjust(width)


def _print_header(cols: list[tuple[str, int, str]]) -> None:
    """Print a table header row and separator.

    cols: list of (label, width, align) where align is 'l' or 'r'.
    """
    header = _COL_SEP.join(
        _pad(label, width) if align == "l" else _right(label, width)
        for label, width, align in cols
    )
    sep = "-+-".join("-" * width for _, width, _ in cols)
    print(header)
    print(sep)


def _print_row(values: list[str], cols: list[tuple[str, int, str]]) -> None:
    row = _COL_SEP.join(
        _pad(v, width) if align == "l" else _right(v, width)
        for v, (_, width, align) in zip(values, cols)
    )
    print(row)


# ---------------------------------------------------------------------------
# Table 1 — By tier
# ---------------------------------------------------------------------------

# Canonical tier order (from CellTier enum)
_TIER_ORDER = [
    "domain",
    "key_dispatch",
    "preservation",
    "base_case",
    "selector_extract",
    "selector_foreign",
]


def _table1(rows: list[dict[str, str]], total: int) -> None:
    print("=" * 80)
    print("Table 1 — Uncovered cells by tier (fork-point decision table)")
    print("=" * 80)

    tier_counts: Counter[str] = Counter()
    tier_triples: dict[str, set[tuple[str, str, str]]] = defaultdict(set)

    for row in rows:
        tier = row["tier"]
        tier_counts[tier] += 1
        tier_triples[tier].add(
            (row["domain"], row["observer_name"], row["constructor_name"])
        )

    cols: list[tuple[str, int, str]] = [
        ("Tier", 20, "l"),
        ("Total occurrences", 19, "r"),
        ("Unique (dom,obs,ctor) triples", 30, "r"),
        ("% of all uncovered", 20, "r"),
    ]
    _print_header(cols)

    for tier in _TIER_ORDER:
        count = tier_counts.get(tier, 0)
        unique = len(tier_triples.get(tier, set()))
        pct = (100.0 * count / total) if total > 0 else 0.0
        _print_row(
            [tier.upper(), str(count), str(unique), f"{pct:.1f}%"],
            cols,
        )

    # Any tiers not in the canonical list
    for tier in sorted(tier_counts):
        if tier not in _TIER_ORDER:
            count = tier_counts[tier]
            unique = len(tier_triples[tier])
            pct = (100.0 * count / total) if total > 0 else 0.0
            _print_row(
                [tier.upper(), str(count), str(unique), f"{pct:.1f}%"],
                cols,
            )

    print()


# ---------------------------------------------------------------------------
# Table 2 — By domain
# ---------------------------------------------------------------------------


def _table2(
    rows: list[dict[str, str]],
    score_records: list[dict],
) -> None:
    print("=" * 80)
    print("Table 2 — Uncovered cells by domain (sorted descending)")
    print("=" * 80)

    # Count uncovered per (domain, replicate)
    uncovered_per_trial: dict[tuple[str, str], int] = Counter()
    for row in rows:
        uncovered_per_trial[(row["domain"], row["replicate"])] += 1

    # Collect trial counts and coverage from scores
    trial_counts: Counter[str] = Counter()
    coverage_by_domain: dict[str, list[float]] = defaultdict(list)
    for rec in score_records:
        d = rec["domain"]
        trial_counts[d] += 1
        if rec["parse_success"]:
            coverage_by_domain[d].append(rec["coverage_ratio"])

    # Aggregate uncovered stats by domain
    all_domains: set[str] = set(rec["domain"] for rec in score_records)
    # Also include domains that appear in uncovered rows
    for row in rows:
        all_domains.add(row["domain"])

    domain_stats: list[tuple[str, int, float, int, float]] = []
    for domain in sorted(all_domains):
        # Get all (domain, replicate) pairs from score records
        replicate_ids = [
            rec["replicate"]
            for rec in score_records
            if rec["domain"] == domain and rec["parse_success"]
        ]
        uncovered_counts = [
            uncovered_per_trial.get((domain, str(rep)), 0) for rep in replicate_ids
        ]
        n_trials = trial_counts.get(domain, 0)
        mean_uncov = (
            sum(uncovered_counts) / len(uncovered_counts)
            if uncovered_counts
            else 0.0
        )
        max_uncov = max(uncovered_counts) if uncovered_counts else 0
        cov_rates = coverage_by_domain.get(domain, [])
        mean_cov = sum(cov_rates) / len(cov_rates) if cov_rates else 0.0
        domain_stats.append((domain, n_trials, mean_uncov, max_uncov, mean_cov))

    # Sort by mean_uncov descending
    domain_stats.sort(key=lambda x: x[2], reverse=True)

    cols: list[tuple[str, int, str]] = [
        ("Domain", 22, "l"),
        ("Trials", 8, "r"),
        ("Mean uncovered", 15, "r"),
        ("Max uncovered", 14, "r"),
        ("Coverage rate", 14, "r"),
    ]
    _print_header(cols)

    for domain, n_trials, mean_uncov, max_uncov, mean_cov in domain_stats:
        _print_row(
            [
                domain,
                str(n_trials),
                f"{mean_uncov:.2f}",
                str(max_uncov),
                f"{mean_cov:.3f}",
            ],
            cols,
        )

    print()


# ---------------------------------------------------------------------------
# Table 3 — By (observer, tier), top 20
# ---------------------------------------------------------------------------


def _table3(rows: list[dict[str, str]]) -> None:
    print("=" * 80)
    print("Table 3 — By (observer, tier) — top 20 occurrences")
    print("=" * 80)

    counts: Counter[tuple[str, str]] = Counter()
    domains_for: dict[tuple[str, str], set[str]] = defaultdict(set)

    for row in rows:
        key = (row["observer_name"], row["tier"])
        counts[key] += 1
        domains_for[key].add(row["domain"])

    top20 = counts.most_common(20)

    cols: list[tuple[str, int, str]] = [
        ("Observer", 24, "l"),
        ("Tier", 18, "l"),
        ("Occurrences", 13, "r"),
        ("Domains affected", 30, "l"),
    ]
    _print_header(cols)

    for (observer, tier), count in top20:
        domains_str = ", ".join(sorted(domains_for[(observer, tier)]))
        if len(domains_str) > 28:
            domains_str = domains_str[:25] + "..."
        _print_row(
            [observer, tier, str(count), domains_str],
            cols,
        )

    print()


# ---------------------------------------------------------------------------
# Table 4 — By dispatch
# ---------------------------------------------------------------------------

_DISPATCH_ORDER = ["plain", "hit", "miss"]


def _table4(rows: list[dict[str, str]], total: int) -> None:
    print("=" * 80)
    print("Table 4 — Uncovered cells by dispatch")
    print("=" * 80)

    counts: Counter[str] = Counter(row["dispatch"] for row in rows)

    cols: list[tuple[str, int, str]] = [
        ("Dispatch", 12, "l"),
        ("Total occurrences", 19, "r"),
        ("% of all uncovered", 20, "r"),
    ]
    _print_header(cols)

    for dispatch in _DISPATCH_ORDER:
        count = counts.get(dispatch, 0)
        pct = (100.0 * count / total) if total > 0 else 0.0
        _print_row([dispatch, str(count), f"{pct:.1f}%"], cols)

    # Any extra dispatch values
    for dispatch in sorted(counts):
        if dispatch not in _DISPATCH_ORDER:
            count = counts[dispatch]
            pct = (100.0 * count / total) if total > 0 else 0.0
            _print_row([dispatch, str(count), f"{pct:.1f}%"], cols)

    print()


# ---------------------------------------------------------------------------
# Fork-point summary
# ---------------------------------------------------------------------------


def _fork_point_summary(rows: list[dict[str, str]], total: int) -> None:
    print("=" * 80)
    print("Fork-point summary")
    print("=" * 80)

    domain_count = sum(1 for row in rows if row["tier"] == "domain")
    mechanical_count = total - domain_count
    domain_pct = (100.0 * domain_count / total) if total > 0 else 0.0
    mechanical_pct = (100.0 * mechanical_count / total) if total > 0 else 0.0

    print(f"Total uncovered cells       : {total}")
    print(
        f"  DOMAIN tier (LLM required): {domain_count:5d}  ({domain_pct:.1f}%)"
    )
    print(
        f"  Mechanical (other tiers)  : {mechanical_count:5d}  ({mechanical_pct:.1f}%)"
    )
    print()

    if total == 0:
        print("Decision: No uncovered cells — perfect coverage!")
    elif domain_pct >= 80.0:
        print(
            "Decision: Predominantly DOMAIN tier — failure mode is genuine semantic "
            "errors by the LLM. Focus on better examples / methodology."
        )
    elif mechanical_pct >= 80.0:
        print(
            "Decision: Predominantly MECHANICAL failures — consider adding targeted "
            "rules or examples for the affected tiers."
        )
    else:
        print(
            f"Decision: Mixed ({domain_pct:.0f}% domain, {mechanical_pct:.0f}% mechanical). "
            "Both semantic and pattern-coverage improvements are needed."
        )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    if len(sys.argv) > 1:
        csv_path = Path(sys.argv[1])
    else:
        csv_path = DEFAULT_CSV

    if not csv_path.exists():
        print(f"Error: CSV not found at {csv_path}", file=sys.stderr)
        sys.exit(1)

    rows = _load_uncovered(csv_path)
    total = len(rows)

    # Try to load scores for Table 2 enrichment
    scores_path = csv_path.parent / "scores.jsonl"
    score_records = _load_scores(scores_path)

    print()
    print(f"Input: {csv_path}")
    print(f"Score records: {len(score_records)}")
    print(f"Uncovered cell rows: {total}")
    print()

    if total == 0:
        print("No uncovered cells found — all coverage is 100%.")
        if score_records:
            _table2([], score_records)
        return

    _table1(rows, total)
    _table2(rows, score_records)
    _table3(rows)
    _table4(rows, total)
    _fork_point_summary(rows, total)


if __name__ == "__main__":
    main()
