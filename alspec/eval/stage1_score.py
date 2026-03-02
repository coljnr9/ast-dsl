"""Stage 1 scorer: evaluate a generated Signature against a golden reference.

This module scores signature quality *without* running Stage 2 (axiom generation),
making it cheap enough to use in large Design-of-Experiments runs.

The scorer compares:
- Structural validity (parse_success, well_formed)
- Overlap with the golden signature (Jaccard on sorts, functions, predicates,
  constructors)
- Obligation table size vs. golden (cell_count_delta)

And computes a composite ``health`` score in [0, 1].
"""

from __future__ import annotations

import ast
import logging
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from rapidfuzz import fuzz, process

from alspec.obligation import build_obligation_table
from alspec.pipeline import _execute_signature_code
from alspec.signature import GeneratedSortInfo, Signature

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Failure Classification
# ---------------------------------------------------------------------------


class FailureCategory(Enum):
    """Classifies why a Stage 1 output failed."""

    OK = "ok"  # Parsed successfully, has a Signature
    SYNTAX_ERROR = "syntax"  # ast.parse() fails — invalid Python
    IMPORT_ERROR = "import"  # NameError on alspec symbols
    API_MISUSE = "api_misuse"  # TypeError/ValueError in alspec constructors
    WRONG_TYPE = "wrong_type"  # Code executed but no Signature produced
    EXEC_ERROR = "exec_error"  # Other execution error


def classify_failure(
    code: str,
) -> tuple[Signature | None, FailureCategory, str | None]:
    """Try to execute code and classify the result."""
    # Step 1: syntax check
    try:
        ast.parse(code)
    except SyntaxError as e:
        return None, FailureCategory.SYNTAX_ERROR, f"line {e.lineno}: {e.msg}"

    # Step 2: execute
    namespace: dict[str, Any] = {}
    try:
        exec("from alspec import *", namespace)  # noqa: S102
        exec("from alspec.helpers import *", namespace)  # noqa: S102
        exec(code, namespace)  # noqa: S102
    except NameError as e:
        return None, FailureCategory.IMPORT_ERROR, str(e)
    except (TypeError, ValueError) as e:
        return None, FailureCategory.API_MISUSE, str(e)
    except Exception as e:
        return None, FailureCategory.EXEC_ERROR, f"{type(e).__name__}: {e}"

    # Step 3: find Signature
    sig = namespace.get("sig") or namespace.get("signature")
    if sig is None:
        for val in namespace.values():
            if isinstance(val, Signature):
                sig = val
                break

    if not isinstance(sig, Signature):
        return None, FailureCategory.WRONG_TYPE, "No Signature object produced"

    return sig, FailureCategory.OK, None


# ---------------------------------------------------------------------------
# Score dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage1Score:
    """Quality score for a single Stage 1 output (signature only)."""

    domain: str
    trial_id: int
    replicate: int
    model: str

    # --- Factor levels from the design matrix ---
    # Included so the analyzer can operate directly on scores.jsonl without
    # needing to re-join against design_matrix.csv.
    factor_levels: dict[str, int]  # {"A": 1, "B": -1, ...}

    # --- Basic validity ---
    parse_success: bool  # did the code execute and produce a Signature?
    well_formed: bool  # do all sorts resolve? (no undefined sort refs)

    # --- Structural metrics (meaningful only when parse_success) ---
    sort_count: int
    function_count: int
    predicate_count: int
    constructor_count: int  # total constructors across all generated sorts
    observer_count: int  # functions whose first param is a gen sort, excl. constructors
    obligation_cell_count: int  # from build_obligation_table()
    has_generated_sorts: bool

    # --- Golden comparison (Jaccard similarities) ---
    sort_overlap: float
    function_overlap: float
    predicate_overlap: float
    constructor_overlap: float
    cell_count_delta: int  # obligation_cells - golden_obligation_cells (0 is best)

    # --- Fuzzy name matching (rapidfuzz, threshold=80) ---
    fuzzy_sort_overlap: float = 0.0
    fuzzy_function_overlap: float = 0.0
    fuzzy_predicate_overlap: float = 0.0
    fuzzy_constructor_overlap: float = 0.0
    fuzzy_health: float = 0.0  # same weighted composite but with fuzzy overlaps

    # --- Composite ---
    health: float = 0.0  # weighted composite in [0, 1]
    
    # --- Intrinsic Health (structural only) ---
    intrinsic_health: float = 0.0
    tier1_parse: float = 0.0
    tier2_sig: float = 0.0
    tier3_oblig: float = 0.0
    tier4_balance: float = 0.0
    tier5_complexity: float = 0.0

    # --- Metadata ---
    error_message: str | None = None  # set when parse_success=False
    failure_category: FailureCategory = FailureCategory.OK
    partial_parse_credit: float = 0.0  # non-zero only when parse_success=False


# ---------------------------------------------------------------------------
# Golden reference cache
# ---------------------------------------------------------------------------


def _make_zero_score(
    domain: str,
    trial_id: int,
    replicate: int,
    model: str,
    error_message: str,
    failure_category: FailureCategory = FailureCategory.EXEC_ERROR,
    factor_levels: dict[str, int] | None = None,
    raw_output: str = "",
) -> Stage1Score:
    credit = partial_parse_score(raw_output)
    return Stage1Score(
        domain=domain,
        trial_id=trial_id,
        replicate=replicate,
        model=model,
        factor_levels=factor_levels or {},
        parse_success=False,
        well_formed=False,
        failure_category=failure_category,
        sort_count=0,
        function_count=0,
        predicate_count=0,
        constructor_count=0,
        observer_count=0,
        obligation_cell_count=0,
        has_generated_sorts=False,
        sort_overlap=0.0,
        function_overlap=0.0,
        predicate_overlap=0.0,
        constructor_overlap=0.0,
        cell_count_delta=0,
        fuzzy_sort_overlap=0.0,
        fuzzy_function_overlap=0.0,
        fuzzy_predicate_overlap=0.0,
        fuzzy_constructor_overlap=0.0,
        fuzzy_health=0.0,
        health=credit,
        intrinsic_health=0.05 if not error_message else 0.0, # minimal signal for trying
        error_message=error_message,
        partial_parse_credit=credit,
    )


# ---------------------------------------------------------------------------
# Golden spec loading
# ---------------------------------------------------------------------------


def _load_golden_signature(domain: str, golden_dir: Path) -> Signature | None:
    """Load the Signature from a golden spec file.

    Returns None if the domain has no golden spec or loading fails.
    """
    candidates = list(golden_dir.glob(f"{domain}.py"))
    if not candidates:
        logger.debug("No golden spec found for domain %r in %s", domain, golden_dir)
        return None

    path = candidates[0]
    namespace: dict[str, Any] = {}
    try:
        exec("from alspec import *", namespace)  # noqa: S102
        exec("from alspec.helpers import *", namespace)  # noqa: S102
        exec(path.read_text(), namespace)  # noqa: S102
    except Exception as exc:
        logger.warning("Failed to exec golden spec %s: %s", path, exc)
        return None

    # Find the spec-returning function and call it
    fn_name = domain.replace("-", "_") + "_spec"
    fn = namespace.get(fn_name)
    if fn is None:
        # Try any callable that returns a Spec
        from alspec.spec import Spec

        for val in namespace.values():
            if callable(val):
                try:
                    result = val()
                    if isinstance(result, Spec):
                        return result.signature
                except Exception:
                    pass
        logger.warning("No spec function found in golden/%s.py", domain)
        return None

    try:
        from alspec.spec import Spec

        result = fn()
        if isinstance(result, Spec):
            return result.signature
    except Exception as exc:
        logger.warning("Golden spec function %s() raised: %s", fn_name, exc)

    return None


# ---------------------------------------------------------------------------
# Well-formedness check for a bare Signature
# ---------------------------------------------------------------------------


def _check_well_formed(sig: Signature) -> bool:
    """Return True if all sort references in the signature are declared."""
    declared = frozenset(sig.sorts.keys())
    for fn in sig.functions.values():
        if fn.result not in declared:
            return False
        for p in fn.params:
            if p.sort not in declared:
                return False
    for pred in sig.predicates.values():
        for p in pred.params:
            if p.sort not in declared:
                return False
    return True


# ---------------------------------------------------------------------------
# Jaccard similarity
# ---------------------------------------------------------------------------


def jaccard(a: set[str], b: set[str]) -> float:
    """Jaccard similarity between two sets.

    Returns 1.0 when both sets are empty (vacuously similar).
    """
    if not a and not b:
        return 1.0
    union = a | b
    return len(a & b) / len(union) if union else 1.0


# Fuzzy matching threshold (rapidfuzz ratio score in [0, 100]).
FUZZY_THRESHOLD: int = 80


def fuzzy_jaccard(
    candidates: set[str], golden: set[str], threshold: int = FUZZY_THRESHOLD
) -> float:
    """Bipartite fuzzy Jaccard between two name sets.

    For each candidate, find its best match in golden (by rapidfuzz ratio).
    A pair is a "hit" if similarity >= threshold. Each golden name can only
    be claimed once (greedy matching, best-first).

    Returns |hits| / |union|, analogous to exact Jaccard.
    Returns 1.0 when both sets are empty (vacuously similar).
    """
    if not candidates and not golden:
        return 1.0
    if not candidates or not golden:
        return 0.0

    # Build all (candidate, golden, score) triples above threshold
    pairs: list[tuple[str, str, float]] = []
    for cand in candidates:
        result = process.extractOne(cand, golden, scorer=fuzz.partial_ratio)
        if result is not None and result[1] >= threshold:
            pairs.append((cand, result[0], result[1]))

    # Greedy match: sort by score descending, assign each golden name at most once
    pairs.sort(key=lambda x: x[2], reverse=True)
    matched_cands: set[str] = set()
    matched_golden: set[str] = set()
    for cand, gold, _score in pairs:
        if cand not in matched_cands and gold not in matched_golden:
            matched_cands.add(cand)
            matched_golden.add(gold)

    hits = len(matched_cands)
    union = len(candidates) + len(golden) - hits
    return hits / union if union > 0 else 1.0


# ---------------------------------------------------------------------------
# Partial parse scoring (Fix 4)
# ---------------------------------------------------------------------------


def partial_parse_score(raw_output: str) -> float:
    """Score in [0.0, 0.15] for outputs that didn't fully parse.

    Checks for evidence that the LLM understood the task format,
    even if the output has syntax errors or exec() fails.  This
    provides signal about which configs *almost* work even when
    they don't produce a valid Signature.
    """
    if not raw_output:
        return 0.0
    score = 0.0
    if "Signature(" in raw_output:
        score += 0.03  # recognised the Signature constructor
    if 'fn(' in raw_output or 'fn("' in raw_output:
        score += 0.03  # attempted function declarations
    if 'pred(' in raw_output or 'pred("' in raw_output:
        score += 0.02  # attempted predicate declarations
    if "GeneratedSortInfo(" in raw_output or "generated_sorts" in raw_output:
        score += 0.03  # attempted generated sorts
    if "SortRef(" in raw_output or "sorts=" in raw_output:
        score += 0.02  # attempted sort declarations
    if "selectors" in raw_output:
        score += 0.02  # attempted selector declarations
    return min(score, 0.15)  # cap below the 0.2 floor for well-formed sigs


def smooth_cap(value: float, target: float, steepness: float = 2.0) -> float:
    """Sigmoid-like scoring: full credit at target, diminishing returns above."""
    import math
    if target == 0:
        return 0.0
    ratio = value / target
    return min(1.0, 1.0 - math.exp(-steepness * ratio) + 0.05)


def compute_intrinsic_health(score_dict: dict) -> dict:
    """Compute intrinsic health from structural fields.
    
    Ported from intrinsic_score_v2.py.
    """
    result = {
        "intrinsic_health": 0.0,
        "tier1_parse": 0.0,
        "tier2_sig": 0.0,
        "tier3_oblig": 0.0,
        "tier4_balance": 0.0,
        "tier5_complexity": 0.0
    }

    # ── Tier 1: Parse & Structure (0.20) ──────────────────────────
    parse_ok = score_dict.get("parse_success", False)
    well_formed = score_dict.get("well_formed", False)
    has_gen = score_dict.get("has_generated_sorts", False)

    if not parse_ok:
        result["intrinsic_health"] = 0.05
        return result

    t1 = 0.0
    t1 += 0.08                         # parsed
    t1 += 0.06 if well_formed else 0   # well-formed
    t1 += 0.06 if has_gen else 0       # has generated sorts
    result["tier1_parse"] = t1

    # ── Tier 2: Signature Richness (0.20) ──────────────────────────
    sorts = score_dict.get("sort_count", 0)
    fns = score_dict.get("function_count", 0)
    preds = score_dict.get("predicate_count", 0)
    ctors = score_dict.get("constructor_count", 0)
    obs = score_dict.get("observer_count", 0)

    t2 = 0.0
    t2 += 0.04 * smooth_cap(sorts, 3)
    t2 += 0.05 * smooth_cap(ctors, 3)
    t2 += 0.04 * smooth_cap(obs, 2)
    t2 += 0.03 * smooth_cap(preds, 1)
    t2 += 0.02 * smooth_cap(fns, 6)
    if ctors >= 2 and obs >= 2:
        ratio = min(ctors, obs) / max(ctors, obs)
        t2 += 0.02 * ratio
    result["tier2_sig"] = min(t2, 0.20)

    # ── Tier 3: Obligation Completeness (0.25) ─────────────────────
    cells = score_dict.get("obligation_cell_count", 0)
    expected = ctors * obs

    t3 = 0.0
    if expected > 0:
        coverage = cells / expected
        t3 += 0.12 * min(coverage, 1.0)
        if coverage > 1.2:
            t3 += 0.05
        elif coverage > 1.0:
            t3 += 0.03
    t3 += 0.05 * smooth_cap(cells, 8)
    if cells > 0 and fns > cells:
        t3 += 0.03
    result["tier3_oblig"] = min(t3, 0.25)

    # ── Tier 4: Balance & Proportion (0.20) ────────────────────────
    t4 = 0.0
    if sorts >= 2 and ctors >= 3:
        t4 += 0.05
    elif ctors >= 2:
        t4 += 0.03

    if preds >= 2:
        t4 += 0.05
    elif preds >= 1:
        t4 += 0.03

    if ctors > 0 and obs > 0:
        oc_ratio = obs / ctors
        if 0.4 <= oc_ratio <= 2.5:
            t4 += 0.05
        elif 0.2 <= oc_ratio <= 4.0:
            t4 += 0.03
        else:
            t4 += 0.01

    if has_gen and sorts >= 3:
        t4 += 0.05
    elif has_gen and sorts >= 2:
        t4 += 0.03
    result["tier4_balance"] = min(t4, 0.20)

    # ── Tier 5: Complexity Signal (0.15) ───────────────────────────
    t5 = 0.0
    helper_fns = fns - ctors - obs
    if helper_fns >= 3:
        t5 += 0.05
    elif helper_fns >= 1:
        t5 += 0.03

    if ctors > 0:
        density = cells / ctors
        t5 += 0.05 * smooth_cap(density, 4)

    total_symbols = fns + preds
    if total_symbols >= 10:
        t5 += 0.05
    elif total_symbols >= 6:
        t5 += 0.03
    elif total_symbols >= 3:
        t5 += 0.01
    result["tier5_complexity"] = min(t5, 0.15)

    # ── Composite ──────────────────────────────────────────────────
    result["intrinsic_health"] = round(
        result["tier1_parse"] + result["tier2_sig"] + result["tier3_oblig"] + 
        result["tier4_balance"] + result["tier5_complexity"], 4
    )
    return result


# ---------------------------------------------------------------------------
# Health computation
# ---------------------------------------------------------------------------


def compute_health(
    parse_success: bool,
    well_formed: bool,
    sort_overlap: float,
    function_overlap: float,
    predicate_overlap: float,
    constructor_overlap: float,
    cell_count_delta: int,
    obligation_cell_count: int,
) -> float:
    """Compute composite health score in [0, 1].

    - Parse failure: partial credit from partial_parse_score() (0–0.15),
      applied by the caller which passes raw_output.
    - Parsed but ill-formed: 0.20 (below the well-formed floor).
    - Parsed and well-formed: 0.20 + 0.80 × weighted_overlap_score.
    """
    if not parse_success:
        # Caller already set health = partial_parse_credit via
        # _make_zero_score(); this branch is kept for direct call compatibility.
        return 0.0
    if not well_formed:
        return 0.2  # parsed but ill-sorted — some signal

    # Cell count relative error: 0 when delta = 0, approaches 0 as delta grows
    max_cells = max(obligation_cell_count, 1)
    cell_score = max(0.0, 1.0 - abs(cell_count_delta) / max_cells)

    overlap_score = (
        0.25 * sort_overlap
        + 0.30 * function_overlap
        + 0.20 * predicate_overlap
        + 0.15 * constructor_overlap
        + 0.10 * cell_score
    )

    # Floor at 0.2 for well-formed signatures
    return 0.2 + 0.8 * overlap_score


# ---------------------------------------------------------------------------
# Constructor extraction helpers
# ---------------------------------------------------------------------------


def _constructor_names(sig: Signature) -> set[str]:
    """Return all declared constructor names from generated_sorts."""
    names: set[str] = set()
    for info in sig.generated_sorts.values():
        names.update(info.constructors)
    return names


def _observer_count(sig: Signature) -> int:
    """Count function symbols that observe a generated sort (not constructors)."""
    gen_sorts = frozenset(sig.generated_sorts.keys())
    ctors = _constructor_names(sig)
    count = 0
    for name, fn in sig.functions.items():
        if name in ctors:
            continue
        if fn.params and fn.params[0].sort in gen_sorts:
            count += 1
    return count


# ---------------------------------------------------------------------------
# Main scoring function
# ---------------------------------------------------------------------------


def score_stage1_output(
    code: str,
    domain: str,
    trial_id: int = 0,
    replicate: int = 0,
    model: str = "unknown",
    golden_dir: Path = Path("golden/"),
    factor_levels: dict[str, int] | None = None,
) -> Stage1Score:
    """Score a raw Stage 1 code string.

    Parameters
    ----------
    code:
        The Python code string returned by the LLM (from the ``submit_signature``
        tool call's ``code`` field).
    domain:
        Domain ID (e.g. ``"stack"``).
    trial_id:
        Row index in the design matrix.
    replicate:
        Replicate index (0-based).
    model:
        The model string used for this run.
    golden_dir:
        Path to the ``golden/`` directory for reference signatures.
    """
    # ---- Parse ----
    sig, failure_category, err = classify_failure(code)
    match failure_category:
        case FailureCategory.OK:
            # Since failure_category is OK, sig is not None.
            assert sig is not None
        case _:
            return _make_zero_score(
                domain,
                trial_id,
                replicate,
                model,
                err or "Unknown error",
                failure_category=failure_category,
                factor_levels=factor_levels,
                raw_output=code,
            )

    parse_success = True

    # ---- Well-formed ----
    well_formed = _check_well_formed(sig)

    # ---- Structural metrics ----
    sort_count = len(sig.sorts)
    function_count = len(sig.functions)
    predicate_count = len(sig.predicates)
    has_generated_sorts = bool(sig.generated_sorts)
    ctor_names = _constructor_names(sig)
    constructor_count = len(ctor_names)
    obs_count = _observer_count(sig)

    obligation_cell_count = 0
    if has_generated_sorts:
        try:
            table = build_obligation_table(sig)
            obligation_cell_count = table.cell_count
        except Exception as exc:
            logger.debug("build_obligation_table failed for %s: %s", domain, exc)

    # ---- Golden comparison ----
    golden_sig = _load_golden_signature(domain, golden_dir)

    if golden_sig is not None:
        golden_ctors = _constructor_names(golden_sig)
        golden_obligation_cells = 0
        if golden_sig.generated_sorts:
            try:
                golden_table = build_obligation_table(golden_sig)
                golden_obligation_cells = golden_table.cell_count
            except Exception:
                pass

        sort_overlap = jaccard(set(sig.sorts.keys()), set(golden_sig.sorts.keys()))
        function_overlap = jaccard(
            set(sig.functions.keys()), set(golden_sig.functions.keys())
        )
        predicate_overlap = jaccard(
            set(sig.predicates.keys()), set(golden_sig.predicates.keys())
        )
        constructor_overlap = jaccard(ctor_names, golden_ctors)
        cell_count_delta = obligation_cell_count - golden_obligation_cells

        fuzzy_sort_overlap = fuzzy_jaccard(
            set(sig.sorts.keys()), set(golden_sig.sorts.keys())
        )
        fuzzy_function_overlap = fuzzy_jaccard(
            set(sig.functions.keys()), set(golden_sig.functions.keys())
        )
        fuzzy_predicate_overlap = fuzzy_jaccard(
            set(sig.predicates.keys()), set(golden_sig.predicates.keys())
        )
        fuzzy_constructor_overlap = fuzzy_jaccard(ctor_names, golden_ctors)
    else:
        # No golden reference → neutral overlaps
        sort_overlap = 0.5
        function_overlap = 0.5
        predicate_overlap = 0.5
        constructor_overlap = 0.5
        cell_count_delta = 0

        fuzzy_sort_overlap = 0.5
        fuzzy_function_overlap = 0.5
        fuzzy_predicate_overlap = 0.5
        fuzzy_constructor_overlap = 0.5

    # ---- Health ----
    health = compute_health(
        parse_success=parse_success,
        well_formed=well_formed,
        sort_overlap=sort_overlap,
        function_overlap=function_overlap,
        predicate_overlap=predicate_overlap,
        constructor_overlap=constructor_overlap,
        cell_count_delta=cell_count_delta,
        obligation_cell_count=obligation_cell_count,
    )

    fuzzy_health = compute_health(
        parse_success=parse_success,
        well_formed=well_formed,
        sort_overlap=fuzzy_sort_overlap,
        function_overlap=fuzzy_function_overlap,
        predicate_overlap=fuzzy_predicate_overlap,
        constructor_overlap=fuzzy_constructor_overlap,
        cell_count_delta=cell_count_delta,
        obligation_cell_count=obligation_cell_count,
    )

    # ---- Intrinsic Health ----
    intrinsic = compute_intrinsic_health({
        "parse_success": parse_success,
        "well_formed": well_formed,
        "has_generated_sorts": has_generated_sorts,
        "sort_count": sort_count,
        "function_count": function_count,
        "predicate_count": predicate_count,
        "constructor_count": constructor_count,
        "observer_count": obs_count,
        "obligation_cell_count": obligation_cell_count,
    })

    return Stage1Score(
        domain=domain,
        trial_id=trial_id,
        replicate=replicate,
        model=model,
        factor_levels=factor_levels or {},
        parse_success=parse_success,
        well_formed=well_formed,
        sort_count=sort_count,
        function_count=function_count,
        predicate_count=predicate_count,
        constructor_count=constructor_count,
        observer_count=obs_count,
        obligation_cell_count=obligation_cell_count,
        has_generated_sorts=has_generated_sorts,
        sort_overlap=sort_overlap,
        function_overlap=function_overlap,
        predicate_overlap=predicate_overlap,
        constructor_overlap=constructor_overlap,
        cell_count_delta=cell_count_delta,
        fuzzy_sort_overlap=fuzzy_sort_overlap,
        fuzzy_function_overlap=fuzzy_function_overlap,
        fuzzy_predicate_overlap=fuzzy_predicate_overlap,
        fuzzy_constructor_overlap=fuzzy_constructor_overlap,
        fuzzy_health=fuzzy_health,
        health=health,
        intrinsic_health=intrinsic["intrinsic_health"],
        tier1_parse=intrinsic["tier1_parse"],
        tier2_sig=intrinsic["tier2_sig"],
        tier3_oblig=intrinsic["tier3_oblig"],
        tier4_balance=intrinsic["tier4_balance"],
        tier5_complexity=intrinsic["tier5_complexity"],
        error_message=None,
        failure_category=FailureCategory.OK,
        partial_parse_credit=0.0,
    )
