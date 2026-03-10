"""Structured compilation diagnostics for LLM-generated code.

Runs a multi-pass analysis pipeline:
  1. ast.parse() — catches SyntaxError/IndentationError
  2. ruff (via subprocess) — catches undefined names, unused imports, etc.
  3. exec() in alspec namespace — catches runtime DSL misuse

Each pass catches a different error class. The first failing pass
determines the diagnostic. This module is the shared building block
for both the forensic analysis script and the future retry mechanism.
"""

from __future__ import annotations

import ast
import json
import subprocess
import tempfile
import traceback
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class CompileDiagnostic:
    """Structured result from attempting to compile/execute LLM-generated code."""

    # Which pass caught the error
    pass_name: str  # "ast_parse" | "ruff" | "exec" | "clean"

    # Python exception class name (or ruff error code)
    error_class: str  # "SyntaxError" | "IndentationError" | "F821" | "NameError" | "TypeError" | "clean"

    # Human-readable error message
    message: str  # "unexpected indent" | "Undefined name `forall`" | ""

    # Location info (when available)
    line_number: int | None = None
    column: int | None = None
    end_line_number: int | None = None

    # The offending source line (extracted from code)
    offending_line: str | None = None

    # Retry heuristic
    retryable: bool = False

    # Full traceback for exec errors (useful for debugging, not for LLM retry prompts)
    full_traceback: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# Ruff error codes that indicate the error is likely retryable
_RETRYABLE_RUFF_CODES = frozenset({
    "E999",   # SyntaxError (ruff's syntax error code)
})

# Ruff codes that are NOT retryable (hallucinated names, wrong imports)
_NON_RETRYABLE_RUFF_CODES = frozenset({
    "F821",   # Undefined name — usually a hallucinated function
    "F811",   # Redefinition of unused name
})

# Ruff codes we care about for diagnostics
_DIAGNOSTIC_RUFF_CODES = "E999,F821,F811,F401"

# Python exception classes that are retryable
_RETRYABLE_EXEC_ERRORS = frozenset({
    "TypeError",    # e.g., "positional argument follows keyword argument"
    "SyntaxError",  # shouldn't reach here but defensive
})


def _get_source_line(code: str, lineno: int | None) -> str | None:
    """Extract a source line from code by line number (1-indexed)."""
    if lineno is None or lineno < 1:
        return None
    lines = code.splitlines()
    if lineno <= len(lines):
        return lines[lineno - 1]
    return None


def _classify_retryable_exec(error_class: str, message: str) -> bool:
    """Heuristic: is this exec error likely fixable by retry?"""
    if error_class in _RETRYABLE_EXEC_ERRORS:
        return True
    # NameError on known alspec symbols might be a typo — retryable
    if error_class == "NameError" and any(
        kw in message for kw in ("forall", "app", "eq", "var", "fn", "pred", "implication", "negation", "iff", "conjunction", "definedness", "pred_app")
    ):
        return True
    return False


def diagnose_code(code: str, *, stage: str = "axioms") -> CompileDiagnostic:
    """Run multi-pass compilation and return a structured diagnostic.

    Parameters
    ----------
    code:
        The Python code string to diagnose.
    stage:
        Which pipeline stage produced this code ("signature" or "axioms").
        Used for context in the diagnostic, not for logic.

    Returns
    -------
    CompileDiagnostic with pass_name="clean" if code compiles and executes successfully.
    """
    # Pass 1: ast.parse — catches pure syntax errors
    try:
        ast.parse(code)
    except SyntaxError as e:
        return CompileDiagnostic(
            pass_name="ast_parse",
            error_class=type(e).__name__,  # "SyntaxError" or "IndentationError"
            message=e.msg or str(e),
            line_number=e.lineno,
            column=e.offset,
            offending_line=_get_source_line(code, e.lineno),
            retryable=True,  # Syntax errors are almost always retryable
        )

    # Pass 2: ruff — catches undefined names, import issues
    ruff_diags = _run_ruff(code)
    if ruff_diags:
        # Return the first diagnostic (most severe)
        d = ruff_diags[0]
        ruff_code = d.get("code", "")
        return CompileDiagnostic(
            pass_name="ruff",
            error_class=ruff_code,
            message=d.get("message", ""),
            line_number=d.get("location", {}).get("row"),
            column=d.get("location", {}).get("column"),
            end_line_number=d.get("end_location", {}).get("row"),
            offending_line=_get_source_line(
                code, d.get("location", {}).get("row")
            ),
            retryable=ruff_code in _RETRYABLE_RUFF_CODES,
        )

    # Pass 3: exec in alspec namespace — catches runtime errors
    namespace: dict[str, Any] = {}
    try:
        exec("from alspec import *", namespace)  # noqa: S102
        exec("from alspec.helpers import *", namespace)  # noqa: S102
        exec(code, namespace)  # noqa: S102
    except Exception as e:
        tb = traceback.format_exc()
        # Try to extract line number from traceback
        lineno = _extract_lineno_from_traceback(tb)
        error_class = type(e).__name__
        message = str(e)
        return CompileDiagnostic(
            pass_name="exec",
            error_class=error_class,
            message=message,
            line_number=lineno,
            offending_line=_get_source_line(code, lineno),
            retryable=_classify_retryable_exec(error_class, message),
            full_traceback=tb,
        )

    # All passes clean
    return CompileDiagnostic(
        pass_name="clean",
        error_class="clean",
        message="",
        retryable=False,
    )


def _run_ruff(code: str) -> list[dict[str, Any]]:
    """Run ruff check on code string, return JSON diagnostics.

    Only returns diagnostics for error codes we care about.
    Returns empty list if ruff is not available or code is clean.
    """
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False
        ) as f:
            f.write(code)
            tmp_path = f.name

        result = subprocess.run(
            [
                "ruff", "check",
                "--select", _DIAGNOSTIC_RUFF_CODES,
                "--output-format", "json",
                "--no-fix",
                tmp_path,
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )

        if result.stdout.strip():
            diags = json.loads(result.stdout)
            return diags if isinstance(diags, list) else []
        return []

    except (FileNotFoundError, subprocess.TimeoutExpired, json.JSONDecodeError):
        return []
    finally:
        if tmp_path:
            try:
                Path(tmp_path).unlink(missing_ok=True)
            except Exception:
                pass


def _extract_lineno_from_traceback(tb: str) -> int | None:
    """Extract the line number from a traceback string.

    Looks for patterns like 'File "<string>", line 47' which is what
    exec() produces.
    """
    import re
    # Match the last occurrence of 'line N' in a File "<string>" frame
    matches = re.findall(r'File "<string>", line (\d+)', tb)
    if matches:
        return int(matches[-1])
    return None
