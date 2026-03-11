"""Structured worked example for prompt injection.

Every golden example is stored in this format to ensure uniform
presentation to the LLM. The render() method produces consistent
markdown + code regardless of which example is being shown.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto


# ============================================================
# Enums
# ============================================================


class RenderMode(Enum):
    """How to render a worked example for prompt injection."""
    FULL = auto()           # Analysis + annotated code
    CODE = auto()           # Annotated code only (comments preserved)
    CODE_BARE = auto()      # Code with all comments stripped
    ANALYSIS = auto()       # Structured analysis only (no code)
    SIGNATURE = auto()      # Analysis + signature-only code (no axioms, no function wrapper)
    SPEC = auto()           # Analysis + full code without function wrapper
    FILLS = auto()          # Analysis + submit_axiom_fills tool call JSON


class FunctionRole(Enum):
    """Role of a function in the specification."""
    CONSTRUCTOR = auto()       # Builds values of the sort (non-nullary)
    CONSTANT = auto()          # Nullary constructor or named value
    OBSERVER = auto()          # Queries/decomposes values (total)
    PARTIAL_OBSERVER = auto()  # Observer that may be undefined
    SELECTOR = auto()          # Component extractor for a specific constructor
    PREDICATE = auto()         # Boolean-valued observer (declared in predicates dict)
    HELPER = auto()            # Uninterpreted / basis function


class CellType(Enum):
    """Obligation table cell classification."""
    SELECTOR_EXTRACT = "selector_extract"
    SELECTOR_FOREIGN = "selector_foreign"
    DOMAIN = "domain"
    KEY_HIT = "key_hit"
    KEY_MISS = "key_miss"
    PRESERVATION = "preservation"
    GUARDED = "guarded"
    UNDEF = "undef"
    BASIS = "basis"


class Pattern(Enum):
    """Patterns from the 23-pattern taxonomy.

    Each pattern represents a distinct specification technique that
    an example can teach the LLM. Used for coverage analysis in
    saturation experiments.
    """
    # Sort structure
    COLLECTION_CONTAINER = auto()
    ENUMERATION = auto()
    PRODUCT_RECORD = auto()
    RECURSIVE = auto()
    SUM_VARIANT = auto()
    SINGLETON = auto()

    # Constructor patterns
    KEYED_CONSTRUCTOR = auto()
    KEYLESS_AGG = auto()
    PARTIAL_CTOR = auto()
    ARITY_VARIATION = auto()

    # Observer / axiom patterns
    SEL_EXTRACT = auto()
    EXPLICIT_UNDEF = auto()
    KEY_DISPATCH = auto()
    DELEGATION = auto()
    ACCUMULATION = auto()
    OVERWRITE = auto()
    PRESERVATION = auto()
    COND_DEF = auto()
    STATE_DEPENDENT = auto()
    ENUM_CASE_SPLIT = auto()
    BICOND_CHAR = auto()
    TRANSITIVE_CLOSURE = auto()
    CROSS_SORT = auto()

    # Structural patterns
    MULTI_GEN_SORT = auto()
    UNINTERP_FN = auto()
    DOUBLY_PARTIAL = auto()
    STRUCT_RECUR = auto()
    NESTED_GUARD = auto()
    BOTH_GUARD_POL = auto()


# ============================================================
# Structured data types
# ============================================================


@dataclass(frozen=True)
class SortInfo:
    """Description of a sort for the analysis section."""
    name: str
    role: str
    rationale: str


@dataclass(frozen=True)
class FunctionInfo:
    """Description of a function/predicate for the analysis section."""
    name: str
    profile: str
    role: FunctionRole
    notes: str = ""


@dataclass(frozen=True)
class ObligationCell:
    """One cell in the obligation table."""
    observer: str
    constructor: str
    cell_type: CellType
    formula_sketch: str
    guard: str = ""


@dataclass(frozen=True)
class DesignDecision:
    """A named design decision with rationale."""
    topic: str
    rationale: str


# ============================================================
# Function unwrapping
# ============================================================


def _unwrap_function(code: str) -> str:
    """Remove function wrapper from example code.

    Strips ``def xxx() -> ...:``, the docstring immediately after it,
    dedents the body by one level (4 spaces), and removes any
    ``return Spec(...)`` / ``return sig`` lines.
    """
    lines = code.splitlines()
    result: list[str] = []
    in_docstring = False
    docstring_quote: str = ""
    docstring_done = False
    skip_def = False

    for line in lines:
        stripped = line.strip()

        # Skip the def line (may span multiple lines if long, but in practice it
        # is always a single line ending with ":")
        if not skip_def and stripped.startswith("def ") and stripped.endswith(":"):
            skip_def = True
            continue

        # Skip docstring that immediately follows def
        if skip_def and not docstring_done:
            if stripped == "":
                # Allow blank lines between def and docstring
                continue
            if not in_docstring:
                if stripped.startswith('"""') or stripped.startswith("'''"):
                    docstring_quote = stripped[:3]
                    # Check if docstring closes on same line
                    rest = stripped[3:]
                    if docstring_quote in rest:
                        # Single-line docstring
                        docstring_done = True
                        continue
                    else:
                        in_docstring = True
                        continue
                else:
                    # No docstring — body starts here
                    docstring_done = True
            else:
                if docstring_quote in stripped:
                    in_docstring = False
                    docstring_done = True
                    continue
                continue

        # Convert 'return Spec(...)' to 'spec = Spec(...)' for top-level usage
        if stripped.startswith("return Spec("):
            # Preserve indentation
            indent = line[:line.find("return ")]
            result.append(indent + "spec = " + stripped[7:])
            continue

        if stripped == "return sig":
            continue

        # Dedent by one level (4 spaces)
        if line.startswith("    "):
            line = line[4:]

        result.append(line)

    # Strip leading and trailing blank lines
    while result and result[0].strip() == "":
        result.pop(0)
    while result and result[-1].strip() == "":
        result.pop()

    return "\n".join(result)


def _extract_signature_only(code: str) -> str:
    """Extract just the signature block from unwrapped code.

    Keeps everything from the start of the unwrapped code through the
    closing ``)`` of the ``sig = Signature(...)`` block.  Axiom
    assignments, variable declarations after the signature, and the
    ``spec = Spec(...)`` line are all removed.
    """
    unwrapped = _unwrap_function(code)
    lines = unwrapped.splitlines()

    # Find the line where sig = Signature( begins
    sig_start: int | None = None
    for i, line in enumerate(lines):
        if "sig = Signature(" in line:
            sig_start = i
            break

    if sig_start is None:
        return unwrapped  # Fallback: no signature block found

    # Walk forward counting open/close parens to find the matching close
    depth = 0
    sig_end = sig_start
    for i in range(sig_start, len(lines)):
        depth += lines[i].count("(") - lines[i].count(")")
        if depth == 0:
            sig_end = i
            break

    return "\n".join(lines[: sig_end + 1])


# ============================================================
# Comment stripping
# ============================================================


def _strip_comments(code: str) -> str:
    """Remove Python comments from code.

    - Strips full-line comments (lines that are only whitespace + comment)
    - Strips inline comments at end of code lines
    - Preserves blank lines between logical sections
    - Does NOT touch strings containing #
    """
    lines: list[str] = []
    for line in code.splitlines():
        stripped = line.strip()

        if stripped.startswith("#"):
            continue

        if "#" in line:
            in_string: str | None = None
            comment_start = -1
            for i, ch in enumerate(line):
                if in_string is None:
                    if ch in ('"', "'"):
                        in_string = ch
                    elif ch == "#":
                        comment_start = i
                        break
                else:
                    if ch == in_string:
                        in_string = None

            if comment_start >= 0:
                line = line[:comment_start].rstrip()

        lines.append(line)

    result: list[str] = []
    prev_blank = False
    for line in lines:
        is_blank = line.strip() == ""
        if is_blank and prev_blank:
            continue
        result.append(line)
        prev_blank = is_blank

    return "\n".join(result)


# ============================================================
# WorkedExample
# ============================================================


@dataclass(frozen=True)
class WorkedExample:
    """A complete worked example: structured analysis + annotated code.

    The analysis is stored as structured data and rendered uniformly.
    The code is always the fully-annotated version; comment stripping
    is a render-time transformation.

    Patterns indicate which specification techniques this example
    demonstrates, used for coverage analysis in experiments.
    """

    domain_name: str
    summary: str
    patterns: frozenset[Pattern]

    sorts: tuple[SortInfo, ...]
    functions: tuple[FunctionInfo, ...]
    obligations: tuple[ObligationCell, ...]
    design_decisions: tuple[DesignDecision, ...]

    code: str
    analysis_text: str = ""   # Free-form reasoning monologue

    # Fields for RenderMode.FILLS (Stage 4 tool call format)
    fills_analysis: str = ""                          # Axiom design reasoning for the tool call
    fills_variables: tuple[dict[str, str], ...] = ()  # [{"name": "s", "sort": "Session"}, ...]
    fills_entries: tuple[dict[str, str], ...] = ()    # [{"label": "...", "formula": "..."}, ...]

    def render(
        self,
        mode: RenderMode = RenderMode.FULL,
        *,
        include_table: bool = True,
    ) -> str:
        """Render the example for prompt injection.

        Parameters
        ----------
        mode:
            What to include. See RenderMode enum.
        include_table:
            If False, omit the obligation table from the analysis section.
            Only relevant when mode includes analysis (FULL or ANALYSIS).
        """
        parts: list[str] = []

        parts.append(f"---\n\n#### Worked Example: {self.domain_name}")
        parts.append(f"_{self.summary}_\n")

        if mode in (RenderMode.FULL, RenderMode.ANALYSIS, RenderMode.SIGNATURE, RenderMode.SPEC, RenderMode.FILLS):
            if self.analysis_text:
                parts.append("")
                parts.append("**Analysis**")
                parts.append("")
                parts.append(self.analysis_text)
                parts.append("")
            parts.append(self._render_analysis(include_table=include_table))

        if mode == RenderMode.SIGNATURE:
            code = _extract_signature_only(self.code)
            parts.append("```python")
            parts.append(code)
            parts.append("```")
        elif mode == RenderMode.SPEC:
            code = _unwrap_function(self.code)
            parts.append("```python")
            parts.append(code)
            parts.append("```")
        elif mode in (RenderMode.FULL, RenderMode.CODE, RenderMode.CODE_BARE):
            code = self.code if mode != RenderMode.CODE_BARE else _strip_comments(self.code)
            parts.append("```python")
            parts.append(code)
            parts.append("```")
        elif mode == RenderMode.FILLS:
            import json
            fills_data = {
                "analysis": self.fills_analysis,
                "variables": self.fills_variables,
                "fills": self.fills_entries,
            }
            parts.append("```json")
            parts.append(json.dumps(fills_data, indent=2))
            parts.append("```")

        return "\n".join(parts)

    def _render_analysis(self, *, include_table: bool = True) -> str:
        lines: list[str] = []

        # Step 1: Sorts
        lines.append("**Step 1: Identify Sorts**\n")
        for s in self.sorts:
            lines.append(f"- `{s.name}` ({s.role}): {s.rationale}")
        lines.append("")

        # Step 2: Functions
        lines.append("**Step 2: Classify Functions**\n")
        for f in self.functions:
            role_name = f.role.name
            role_label = role_name.lower().replace("_", " ")
            notes_suffix = f" — {f.notes}" if f.notes else ""
            lines.append(f"- `{f.name} : {f.profile}` [{role_label}]{notes_suffix}")
        lines.append("")

        # Step 3: Obligation table (toggleable)
        if include_table:
            lines.append("**Step 3: Obligation Table**\n")
            lines.append("| Observer | Constructor | Cell Type | Guard | Axiom |")
            lines.append("|----------|-------------|-----------|-------|-------|")
            for o in self.obligations:
                guard = o.guard if o.guard else "—"
                cell_val = o.cell_type.value
                lines.append(
                    f"| `{o.observer}` | `{o.constructor}` "
                    f"| {cell_val} | {guard} "
                    f"| {o.formula_sketch} |"
                )
            lines.append("")

        # Design decisions
        if self.design_decisions:
            lines.append("**Design Decisions**\n")
            for d in self.design_decisions:
                lines.append(f"- **{d.topic}:** {d.rationale}")
            lines.append("")

        return "\n".join(lines)

    @property
    def token_estimate(self) -> dict[str, int]:
        """Rough token estimates for each render mode (chars / 4)."""
        return {
            mode.name: len(self.render(mode)) // 4
            for mode in RenderMode
        }
