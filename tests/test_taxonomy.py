"""Tests for alspec.eval.taxonomy — classify_failure() and FailureCategory.

Every branch of classify_failure is covered by a dedicated test case.
Fakes are built from real frozen dataclasses (EvalResult, SpecScore,
Diagnostic) so no mocking framework is needed.
"""
from __future__ import annotations

import pytest

from alspec.check import Diagnostic, Severity
from alspec.eval.harness import EvalResult
from alspec.eval.taxonomy import FailureCategory, classify_failure
from alspec.score import SpecScore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_score(
    *,
    well_formed: bool,
    diagnostics: tuple[Diagnostic, ...] = (),
) -> SpecScore:
    """Construct a minimal SpecScore for testing."""
    error_count = sum(1 for d in diagnostics if d.severity == Severity.ERROR)
    return SpecScore(
        spec_name="test_spec",
        well_formed=well_formed,
        error_count=error_count,
        warning_count=0,
        health=1.0 if well_formed else 0.0,
        sort_count=1,
        function_count=1,
        predicate_count=0,
        axiom_count=0,
        diagnostics=diagnostics,
    )


def _make_eval(
    *,
    success: bool,
    parse_error: str | None = None,
    checker_error: str | None = None,
    score: SpecScore | None = None,
) -> EvalResult:
    """Construct a minimal EvalResult for testing."""
    return EvalResult(
        domain_id="test_domain",
        model="test_model",
        success=success,
        parse_error=parse_error,
        checker_error=checker_error,
        score=score,
        analysis=None,
        code=None,
        latency_ms=0,
        prompt_tokens=None,
        completion_tokens=None,
        cached_tokens=None,
        cache_write_tokens=None,
    )


def _diag(check: str, severity: Severity = Severity.ERROR) -> Diagnostic:
    return Diagnostic(
        check=check,
        severity=severity,
        axiom=None,
        message=f"test diagnostic for {check}",
        path=None,
    )


# ---------------------------------------------------------------------------
# Test A: PASS
# ---------------------------------------------------------------------------

def test_pass() -> None:
    """success=True, well_formed=True → PASS."""
    score = _make_score(well_formed=True, diagnostics=())
    result = _make_eval(success=True, score=score)
    assert classify_failure(result) == FailureCategory.PASS


# ---------------------------------------------------------------------------
# Test B: PARSE_OBLIGATION_VALIDATION
# ---------------------------------------------------------------------------

def test_parse_obligation_validation() -> None:
    """success=False with obligation validation message → PARSE_OBLIGATION_VALIDATION."""
    error = (
        "Obligation Table Validation Failed: Observer 'is_valid_withdraw' and "
        "constructor 'deposit' share key sort 'Amount' but no equality predicate "
        "'eq_amount' exists..."
    )
    result = _make_eval(success=False, parse_error=error)
    assert classify_failure(result) == FailureCategory.PARSE_OBLIGATION_VALIDATION


# ---------------------------------------------------------------------------
# Test C: PARSE_PYTHON_ERROR
# ---------------------------------------------------------------------------

def test_parse_python_error() -> None:
    """success=False with Python exception keyword → PARSE_PYTHON_ERROR."""
    result = _make_eval(
        success=False,
        parse_error="NameError: name 'Exists' is not defined",
    )
    assert classify_failure(result) == FailureCategory.PARSE_PYTHON_ERROR


# ---------------------------------------------------------------------------
# Test D: PARSE_OTHER
# ---------------------------------------------------------------------------

def test_parse_other() -> None:
    """success=False with unrecognised error string → PARSE_OTHER."""
    result = _make_eval(success=False, parse_error="Some unknown error")
    assert classify_failure(result) == FailureCategory.PARSE_OTHER


# ---------------------------------------------------------------------------
# Test E: WF_UNDECLARED_SYMBOL
# ---------------------------------------------------------------------------

def test_wf_undeclared_symbol() -> None:
    """success=True, score with fn_declared ERROR → WF_UNDECLARED_SYMBOL."""
    score = _make_score(
        well_formed=False,
        diagnostics=(_diag("fn_declared"),),
    )
    result = _make_eval(success=True, score=score)
    assert classify_failure(result) == FailureCategory.WF_UNDECLARED_SYMBOL


# ---------------------------------------------------------------------------
# Test F: WF_UNBOUND_VARIABLE
# ---------------------------------------------------------------------------

def test_wf_unbound_variable() -> None:
    """success=True, score with var_bound ERROR → WF_UNBOUND_VARIABLE."""
    score = _make_score(
        well_formed=False,
        diagnostics=(_diag("var_bound"),),
    )
    result = _make_eval(success=True, score=score)
    assert classify_failure(result) == FailureCategory.WF_UNBOUND_VARIABLE


# ---------------------------------------------------------------------------
# Test G: WF_SORT_MISMATCH
# ---------------------------------------------------------------------------

def test_wf_sort_mismatch() -> None:
    """success=True, score with fn_arg_sorts ERROR → WF_SORT_MISMATCH."""
    score = _make_score(
        well_formed=False,
        diagnostics=(_diag("fn_arg_sorts"),),
    )
    result = _make_eval(success=True, score=score)
    assert classify_failure(result) == FailureCategory.WF_SORT_MISMATCH


# ---------------------------------------------------------------------------
# Test H: WF_OTHER
# ---------------------------------------------------------------------------

def test_wf_other() -> None:
    """success=True, score with unrecognised check ERROR → WF_OTHER."""
    score = _make_score(
        well_formed=False,
        diagnostics=(_diag("duplicate_axiom_labels"),),
    )
    result = _make_eval(success=True, score=score)
    assert classify_failure(result) == FailureCategory.WF_OTHER


# ---------------------------------------------------------------------------
# Test I: Priority ordering — undeclared_symbol beats unbound_variable
# ---------------------------------------------------------------------------

def test_priority_undeclared_beats_unbound() -> None:
    """When both fn_declared and var_bound errors are present, result is WF_UNDECLARED_SYMBOL."""
    score = _make_score(
        well_formed=False,
        diagnostics=(
            _diag("fn_declared"),
            _diag("var_bound"),
        ),
    )
    result = _make_eval(success=True, score=score)
    assert classify_failure(result) == FailureCategory.WF_UNDECLARED_SYMBOL


# ---------------------------------------------------------------------------
# Test J: coarse property
# ---------------------------------------------------------------------------

def test_coarse_property() -> None:
    """Verify coarse group extraction for each root category."""
    assert FailureCategory.PASS.coarse == "pass"
    assert FailureCategory.PARSE_OBLIGATION_VALIDATION.coarse == "parse"
    assert FailureCategory.PARSE_PYTHON_ERROR.coarse == "parse"
    assert FailureCategory.PARSE_OTHER.coarse == "parse"
    assert FailureCategory.WF_UNDECLARED_SYMBOL.coarse == "wf"
    assert FailureCategory.WF_UNBOUND_VARIABLE.coarse == "wf"
    assert FailureCategory.WF_SORT_MISMATCH.coarse == "wf"
    assert FailureCategory.WF_OTHER.coarse == "wf"


# ---------------------------------------------------------------------------
# Test K: is_success property
# ---------------------------------------------------------------------------

def test_is_success_property() -> None:
    """Only PASS returns True for is_success; all others return False."""
    assert FailureCategory.PASS.is_success is True

    for member in FailureCategory:
        if member != FailureCategory.PASS:
            assert member.is_success is False, f"{member} should not be success"


# ---------------------------------------------------------------------------
# Additional edge cases
# ---------------------------------------------------------------------------

def test_parse_python_error_other_keywords() -> None:
    """All _PYTHON_ERROR_KEYWORDS trigger PARSE_PYTHON_ERROR."""
    keywords = [
        "SyntaxError", "TypeError", "AttributeError",
        "ValueError", "ImportError", "IndexError", "KeyError",
    ]
    for kw in keywords:
        result = _make_eval(success=False, parse_error=f"{kw}: something went wrong")
        assert classify_failure(result) == FailureCategory.PARSE_PYTHON_ERROR, kw


def test_wf_sort_mismatch_other_checks() -> None:
    """All sort-mismatch check names (equation_sort_match, pred_arg_sorts) map correctly."""
    for check in ("equation_sort_match", "pred_arg_sorts"):
        score = _make_score(
            well_formed=False,
            diagnostics=(_diag(check),),
        )
        result = _make_eval(success=True, score=score)
        assert classify_failure(result) == FailureCategory.WF_SORT_MISMATCH, check


def test_wf_pred_declared() -> None:
    """pred_declared (not just fn_declared) also maps to WF_UNDECLARED_SYMBOL."""
    score = _make_score(
        well_formed=False,
        diagnostics=(_diag("pred_declared"),),
    )
    result = _make_eval(success=True, score=score)
    assert classify_failure(result) == FailureCategory.WF_UNDECLARED_SYMBOL


def test_all_eight_enum_members_present() -> None:
    """Exactly 8 enum members exist with the expected values."""
    expected = {
        "pass",
        "parse:obligation_validation",
        "parse:python_error",
        "parse:other",
        "wf:undeclared_symbol",
        "wf:unbound_variable",
        "wf:sort_mismatch",
        "wf:other",
    }
    actual = {fc.value for fc in FailureCategory}
    assert actual == expected, f"Missing: {expected - actual}, Extra: {actual - expected}"
