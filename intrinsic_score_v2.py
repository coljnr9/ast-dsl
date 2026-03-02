#!/usr/bin/env python3
"""Intrinsic health scoring v2 — tighter rubric, no re-exec needed.

Uses the structural fields already in results.jsonl from the existing scorer.
Scores across five tiers with more discriminating thresholds than v1.

  Tier 1 (0.20): Parse & Structure — parse_ok, well_formed, has_generated_sorts
  Tier 2 (0.20): Signature Richness — sorts, functions, predicates, constructors, observers
  Tier 3 (0.25): Obligation Completeness — cell count vs expected, axiom density
  Tier 4 (0.20): Balance & Proportion — constructor/observer ratio, predicate presence
  Tier 5 (0.15): Complexity Signal — multi-sort depth, function richness beyond minimum

Usage:
    uv run intrinsic_score_v2.py [results.jsonl]
"""

import json
import math
import statistics
import sys
from collections import defaultdict
from pathlib import Path


RESULTS = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(
    "results/lens_experiment_20260301_200456/results.jsonl"
)


def smooth_cap(value: float, target: float, steepness: float = 2.0) -> float:
    """Sigmoid-like scoring: full credit at target, diminishing returns above."""
    if target == 0:
        return 0.0
    ratio = value / target
    return min(1.0, 1.0 - math.exp(-steepness * ratio) + 0.05)


def intrinsic_health(r: dict) -> dict:
    """Compute tiered intrinsic health from structural fields."""
    result = {"tier1": 0.0, "tier2": 0.0, "tier3": 0.0, "tier4": 0.0, "tier5": 0.0}

    # ── Tier 1: Parse & Structure (0.20) ──────────────────────────
    parse_ok = r.get("parse_success", False)
    well_formed = r.get("well_formed", False)
    has_gen = r.get("has_generated_sorts", False)

    if not parse_ok:
        result["total"] = 0.05
        return result

    t1 = 0.0
    t1 += 0.08                         # parsed
    t1 += 0.06 if well_formed else 0   # well-formed
    t1 += 0.06 if has_gen else 0       # has generated sorts
    result["tier1"] = t1

    # ── Tier 2: Signature Richness (0.20) ──────────────────────────
    sorts = r.get("sort_count", 0)
    fns = r.get("function_count", 0)
    preds = r.get("predicate_count", 0)
    ctors = r.get("constructor_count", 0)
    obs = r.get("observer_count", 0)

    t2 = 0.0
    # Sorts: want >= 2, bonus for >= 3
    t2 += 0.04 * smooth_cap(sorts, 3)
    # Constructors: want >= 3
    t2 += 0.05 * smooth_cap(ctors, 3)
    # Observers: want >= 2
    t2 += 0.04 * smooth_cap(obs, 2)
    # Predicates: want >= 1
    t2 += 0.03 * smooth_cap(preds, 1)
    # Total functions: want >= 6 (ctors + obs + helpers)
    t2 += 0.02 * smooth_cap(fns, 6)
    # Balance bonus: both ctors and observers present in reasonable ratio
    if ctors >= 2 and obs >= 2:
        ratio = min(ctors, obs) / max(ctors, obs)
        t2 += 0.02 * ratio
    result["tier2"] = min(t2, 0.20)

    # ── Tier 3: Obligation Completeness (0.25) ─────────────────────
    cells = r.get("obligation_cell_count", 0)
    expected = ctors * obs  # before key dispatch

    t3 = 0.0
    if expected > 0:
        coverage = cells / expected
        # Base coverage (0.12): linear up to 1.0
        t3 += 0.12 * min(coverage, 1.0)
        # Key dispatch bonus (0.05): coverage > 1.0 means cells were split
        if coverage > 1.2:
            t3 += 0.05
        elif coverage > 1.0:
            t3 += 0.03
    # Cell count absolute (0.05): want at least 6 obligation cells
    t3 += 0.05 * smooth_cap(cells, 8)
    # Axiom headroom (0.03): total axioms should exceed obligation cells
    # (indicates helper axioms, definitions, equality bases)
    if cells > 0 and fns > cells:
        t3 += 0.03
    result["tier3"] = min(t3, 0.25)

    # ── Tier 4: Balance & Proportion (0.20) ────────────────────────
    t4 = 0.0

    # 4a: Constructor diversity — want both nullary (base case) and n-ary
    if sorts >= 2 and ctors >= 3:
        t4 += 0.05
    elif ctors >= 2:
        t4 += 0.03

    # 4b: Predicate richness
    if preds >= 2:
        t4 += 0.05
    elif preds >= 1:
        t4 += 0.03

    # 4c: Observer/constructor ratio
    if ctors > 0 and obs > 0:
        oc_ratio = obs / ctors
        if 0.4 <= oc_ratio <= 2.5:
            t4 += 0.05  # balanced
        elif 0.2 <= oc_ratio <= 4.0:
            t4 += 0.03  # acceptable
        else:
            t4 += 0.01  # skewed

    # 4d: Multi-sort design
    if has_gen and sorts >= 3:
        t4 += 0.05
    elif has_gen and sorts >= 2:
        t4 += 0.03

    result["tier4"] = min(t4, 0.20)

    # ── Tier 5: Complexity Signal (0.15) ───────────────────────────
    t5 = 0.0

    # 5a: Function richness beyond minimum (helpers, derived functions)
    helper_fns = fns - ctors - obs
    if helper_fns >= 3:
        t5 += 0.05
    elif helper_fns >= 1:
        t5 += 0.03

    # 5b: Obligation density — cells per constructor
    if ctors > 0:
        density = cells / ctors
        t5 += 0.05 * smooth_cap(density, 4)

    # 5c: Overall specification mass
    total_symbols = fns + preds
    if total_symbols >= 10:
        t5 += 0.05
    elif total_symbols >= 6:
        t5 += 0.03
    elif total_symbols >= 3:
        t5 += 0.01

    result["tier5"] = min(t5, 0.15)

    # ── Composite ──────────────────────────────────────────────────
    result["total"] = round(sum(result[f"tier{i}"] for i in range(1, 6)), 4)
    return result


def main():
    if not RESULTS.exists():
        print(f"File not found: {RESULTS}")
        sys.exit(1)

    rows = []
    with open(RESULTS) as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))

    print(f"Loaded {len(rows)} results from {RESULTS}\n")

    # Score each row
    for r in rows:
        r["iscore"] = intrinsic_health(r)

    # ── Aggregate by lens ──────────────────────────────────────────
    lens_order = ["bare_label", "raw_source", "summary", "ears", "bdd",
                  "failure_modes", "entity_lifecycle", "constraints"]

    by_lens = defaultdict(list)
    for r in rows:
        by_lens[r["lens"]].append(r)

    print("=" * 120)
    print(f"{'LENS':<18} {'n':>3} {'golden':>7} {'intr_v2':>8} {'delta':>7}"
          f" {'t1_parse':>8} {'t2_sig':>7} {'t3_oblig':>8} {'t4_bal':>7} {'t5_cplx':>8}"
          f" {'parse%':>6}")
    print("=" * 120)

    for lens in lens_order:
        rs = by_lens.get(lens, [])
        if not rs:
            continue

        n = len(rs)
        gm = statistics.mean([r.get("health", 0.0) for r in rs])
        im = statistics.mean([r["iscore"]["total"] for r in rs])
        t1 = statistics.mean([r["iscore"]["tier1"] for r in rs])
        t2 = statistics.mean([r["iscore"]["tier2"] for r in rs])
        t3 = statistics.mean([r["iscore"]["tier3"] for r in rs])
        t4 = statistics.mean([r["iscore"]["tier4"] for r in rs])
        t5 = statistics.mean([r["iscore"]["tier5"] for r in rs])
        pr = sum(1 for r in rs if r.get("parse_success")) / n * 100

        print(f"  {lens:<16} {n:>3} {gm:>7.3f} {im:>8.3f} {im-gm:>+7.3f}"
              f" {t1:>8.3f} {t2:>7.3f} {t3:>8.3f} {t4:>7.3f} {t5:>8.3f}"
              f" {pr:>5.0f}%")

    # ── Per-domain side-by-side ────────────────────────────────────
    groups = defaultdict(list)
    for r in rows:
        groups[(r["domain"], r["lens"])].append(r)

    domains = sorted({d for d, _ in groups})

    print()
    print("=" * 120)
    print("PER-DOMAIN: GOLDEN vs INTRINSIC v2 (median)")
    print("=" * 120)

    print(f"\n  {'domain':<20}", end="")
    for lens in lens_order:
        print(f" {lens[:8]:>8}", end="")
    print()

    print("  GOLDEN HEALTH:")
    for domain in domains:
        print(f"  {domain:<18}", end="")
        for lens in lens_order:
            vals = [r.get("health", 0.0) for r in groups.get((domain, lens), [])]
            if vals:
                print(f" {statistics.median(vals):>8.3f}", end="")
            else:
                print(f" {'---':>8}", end="")
        print()

    print(f"\n  INTRINSIC v2:")
    for domain in domains:
        print(f"  {domain:<18}", end="")
        for lens in lens_order:
            vals = [r["iscore"]["total"] for r in groups.get((domain, lens), [])]
            if vals:
                print(f" {statistics.median(vals):>8.3f}", end="")
            else:
                print(f" {'---':>8}", end="")
        print()

    # ── Divergence: high intrinsic, low golden ─────────────────────
    print()
    print("=" * 120)
    print("TOP 20 DIVERGENCES (intrinsic v2 >> golden) -- good spec, bad golden match")
    print("=" * 120)

    divergences = []
    for (domain, lens), rs in groups.items():
        gm = statistics.median([r.get("health", 0.0) for r in rs])
        im = statistics.median([r["iscore"]["total"] for r in rs])
        divergences.append((domain, lens, gm, im, im - gm))

    divergences.sort(key=lambda x: x[4], reverse=True)

    print(f"\n  {'domain':<20} {'lens':<18} {'golden':>7} {'intrinsic':>9} {'delta':>7}")
    for domain, lens, gm, im, delta in divergences[:20]:
        print(f"  {domain:<20} {lens:<18} {gm:>7.3f} {im:>9.3f} {delta:>+7.3f}")

    # ── Structural richness ────────────────────────────────────────
    print()
    print("=" * 120)
    print("STRUCTURAL RICHNESS BY LENS (mean, parsed specs only)")
    print("=" * 120)
    print(f"  {'lens':<18} {'sorts':>6} {'fns':>6} {'preds':>6} {'ctors':>6}"
          f" {'obs':>6} {'cells':>7} {'exp':>7} {'coverage':>9} {'helpers':>8}")

    for lens in lens_order:
        parsed = [r for r in by_lens.get(lens, []) if r.get("parse_success")]
        if not parsed:
            continue

        def avg(key):
            return statistics.mean([r.get(key, 0) for r in parsed])

        ctors_m = avg("constructor_count")
        obs_m = avg("observer_count")
        cells_m = avg("obligation_cell_count")
        exp_m = ctors_m * obs_m
        cov = cells_m / exp_m if exp_m > 0 else 0
        fns_m = avg("function_count")
        helpers = fns_m - ctors_m - obs_m

        print(f"  {lens:<18} {avg('sort_count'):>6.1f} {fns_m:>6.1f}"
              f" {avg('predicate_count'):>6.1f} {ctors_m:>6.1f}"
              f" {obs_m:>6.1f} {cells_m:>7.1f} {exp_m:>7.1f} {cov:>8.1%} {helpers:>8.1f}")

    # ── Correlation analysis ───────────────────────────────────────
    print()
    print("=" * 120)
    print("CORRELATION: Do golden and intrinsic agree on which DOMAINS are hard?")
    print("=" * 120)

    domain_gold = {}
    domain_intr = {}
    for domain in domains:
        gvals = []
        ivals = []
        for lens in lens_order:
            for r in groups.get((domain, lens), []):
                gvals.append(r.get("health", 0.0))
                ivals.append(r["iscore"]["total"])
        if gvals:
            domain_gold[domain] = statistics.mean(gvals)
            domain_intr[domain] = statistics.mean(ivals)

    # Rank correlation (Spearman-style)
    gold_ranked = sorted(domains, key=lambda d: domain_gold.get(d, 0))
    intr_ranked = sorted(domains, key=lambda d: domain_intr.get(d, 0))

    print(f"\n  {'Rank':>4} {'Golden ranking':<25} {'Intrinsic ranking':<25}")
    for i, (g, ir) in enumerate(zip(gold_ranked, intr_ranked)):
        marker = " <-" if g == ir else ""
        print(f"  {i+1:>4} {g:<25} {ir:<25}{marker}")


if __name__ == "__main__":
    main()
