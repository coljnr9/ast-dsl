"""Failure taxonomy for pipeline eval results.

Every pipeline run is classified into exactly one FailureCategory.
The classifier is deterministic and derives the category from fields
already present on EvalResult — no LLM, no heuristics.
"""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from alspec.eval.harness import EvalResult


class FailureCategory(Enum):
    """Exhaustive, mutually exclusive classification of a pipeline run.

    Values use colon-delimited format for coarse/fine grouping:
    split on ':' to get the coarse group (pass, parse, wf).
    """

    # ── Success ──
    PASS = "pass"

    # ── Parse failures (success=False, no spec produced) ──
    PARSE_OBLIGATION_VALIDATION = "parse:obligation_validation"
    PARSE_OBLIGATION_CRASH = "parse:obligation_crash"
    PARSE_STAGE4_EXEC = "parse:stage4_exec"
    PARSE_PYTHON_ERROR = "parse:python_error"
    PARSE_OTHER = "parse:other"

    # ── Well-formedness failures (parsed, checker finds errors) ──
    WF_UNDECLARED_SYMBOL = "wf:undeclared_symbol"
    WF_UNBOUND_VARIABLE = "wf:unbound_variable"
    WF_SORT_MISMATCH = "wf:sort_mismatch"
    WF_OTHER = "wf:other"

    @property
    def is_success(self) -> bool:
        return self == FailureCategory.PASS

    @property
    def coarse(self) -> str:
        """Return the coarse group: 'pass', 'parse', or 'wf'."""
        return self.value.split(":")[0]


# Check names from alspec/check.py that map to each WF category.
_UNDECLARED_CHECKS = frozenset({"fn_declared", "pred_declared"})
_UNBOUND_CHECKS = frozenset({"var_bound"})
_SORT_MISMATCH_CHECKS = frozenset({"fn_arg_sorts", "equation_sort_match", "pred_arg_sorts"})

# Python error keywords that appear in parse_error strings
# when Stage 4 code fails at exec() time.
_PYTHON_ERROR_KEYWORDS = (
    "NameError", "SyntaxError", "TypeError", "AttributeError",
    "ValueError", "ImportError", "IndexError", "KeyError",
)


def classify_failure(result: EvalResult) -> FailureCategory:
    """Classify an EvalResult into exactly one FailureCategory.

    Classification rules (evaluated in order):

    1. If success=True and well_formed=True → PASS
    2. If success=False → parse failure subcategory
    3. If success=True and well_formed=False → WF failure subcategory

    For WF failures with multiple error types, priority is:
    undeclared_symbol > unbound_variable > sort_mismatch > other
    (most actionable / most common first).
    """
    from alspec.check import Severity

    # ── Success ──
    if result.success and result.score is not None and result.score.well_formed:
        return FailureCategory.PASS

    # ── Parse failures ──
    if not result.success:
        error_str = result.parse_error or result.checker_error or ""

        if "Obligation Table Validation" in error_str:
            return FailureCategory.PARSE_OBLIGATION_VALIDATION

        # Obligation table builder crashed (unhandled exception, not clean validation)
        if "Unexpected obligation table error:" in error_str:
            return FailureCategory.PARSE_OBLIGATION_CRASH

        # Stage 4 code executed but crashed at runtime (e.g. hallucinated DSL methods)
        if "Stage 4 (Axioms) code execution failed:" in error_str:
            return FailureCategory.PARSE_STAGE4_EXEC

        if any(kw in error_str for kw in _PYTHON_ERROR_KEYWORDS):
            return FailureCategory.PARSE_PYTHON_ERROR

        return FailureCategory.PARSE_OTHER

    # ── WF failures ──
    if result.score is not None:
        error_checks = frozenset(
            d.check
            for d in result.score.diagnostics
            if d.severity == Severity.ERROR
        )

        if error_checks & _UNDECLARED_CHECKS:
            return FailureCategory.WF_UNDECLARED_SYMBOL
        if error_checks & _UNBOUND_CHECKS:
            return FailureCategory.WF_UNBOUND_VARIABLE
        if error_checks & _SORT_MISMATCH_CHECKS:
            return FailureCategory.WF_SORT_MISMATCH

        return FailureCategory.WF_OTHER

    # Fallback: success=True but no score (shouldn't happen, but be safe)
    return FailureCategory.PARSE_OTHER
