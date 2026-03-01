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

        parts.append(f"### Worked Example: {self.domain_name}")
        parts.append(f"_{self.summary}_\n")

        if mode in (RenderMode.FULL, RenderMode.ANALYSIS):
            parts.append(self._render_analysis(include_table=include_table))

        if mode in (RenderMode.FULL, RenderMode.CODE, RenderMode.CODE_BARE):
            code = self.code if mode != RenderMode.CODE_BARE else _strip_comments(self.code)
            parts.append("```python")
            parts.append(code)
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
