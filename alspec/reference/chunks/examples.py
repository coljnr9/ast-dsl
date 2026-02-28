from pathlib import Path

from alspec.prompt_chunks import (
    ChunkId, Concept, Stage, BOTH, S1, S2, register,
)

_GOLDEN_DIR = Path(__file__).resolve().parent.parent.parent.parent / "golden"


def _read_golden(name: str) -> str:
    path = _GOLDEN_DIR / f"{name}.py"
    if not path.exists():
        # Fallback for different environments if necessary, but here we expect it to exist
        raise FileNotFoundError(f"Golden spec not found: {path}")
    return path.read_text()


def _extract_docstring(source: str) -> str:
    """Extract the triple-quoted docstring from a golden spec file."""
    try:
        start = source.index('"""')
        end = source.index('"""', start + 3) + 3
        return source[start + 3 : end - 3].strip()
    except ValueError:
        return "" # No docstring found


def _extract_code_after_docstring(source: str) -> str:
    """Extract everything after the docstring."""
    try:
        first_doc = source.index('"""')
        second_doc = source.index('"""', first_doc + 3)
        return source[second_doc + 3:].strip()
    except ValueError:
        return source.strip()


@register(
    id=ChunkId.EXAMPLE_COUNTER,
    stages=BOTH,
    concepts=frozenset({Concept.OBLIGATION_TABLE, Concept.COMPLETENESS}),
    depends_on=(ChunkId.OBLIGATION_PATTERN,),
)
def _example_counter():
    return (
        "### Worked Example: Counter (simplest spec)\n\n"
        "```python\n" + _read_golden("counter") + "```"
    )


@register(
    id=ChunkId.EXAMPLE_STACK,
    stages=BOTH,
    concepts=frozenset({Concept.SELECTORS, Concept.OBLIGATION_TABLE, Concept.NDEF_AXIOMS}),
    depends_on=(ChunkId.OBLIGATION_PATTERN,),
)
def _example_stack():
    return (
        "### Worked Example: Stack (selectors + explicit undefinedness)\n\n"
        "```python\n" + _read_golden("stack") + "```"
    )


@register(
    id=ChunkId.EXAMPLE_THERMOSTAT,
    stages=S2,
    concepts=frozenset({
        Concept.SELECTORS, Concept.PRESERVATION, Concept.DEFINEDNESS_BICONDITIONAL,
    }),
    depends_on=(ChunkId.OBLIGATION_PATTERN,),
)
def _example_thermostat():
    return (
        "### Worked Example: Thermostat (selectors + preservation + biconditional predicates)\n\n"
        "```python\n" + _read_golden("thermostat") + "```"
    )


@register(
    id=ChunkId.EXAMPLE_BUG_TRACKER_ANALYSIS,
    stages=BOTH,
    concepts=frozenset({
        Concept.OBLIGATION_TABLE, Concept.FUNCTION_ROLES, Concept.KEY_DISPATCH,
        Concept.PRESERVATION, Concept.NDEF_AXIOMS, Concept.GUARD_POLARITY,
    }),
    depends_on=(ChunkId.OBLIGATION_PATTERN,),
)
def _example_bug_tracker_analysis():
    source = _read_golden("bug-tracker")
    docstring = _extract_docstring(source)
    return (
        "### Worked Example: Bug Tracker — Analysis\n\n"
        "Complete methodology walkthrough for a domain with key dispatch, preservation, "
        "partial observers, and guard polarity.\n\n"
        + docstring
    )


@register(
    id=ChunkId.EXAMPLE_BUG_TRACKER_CODE,
    stages=S2,
    concepts=frozenset({
        Concept.KEY_DISPATCH, Concept.HIT_MISS, Concept.PRESERVATION,
        Concept.NDEF_AXIOMS, Concept.GUARD_POLARITY, Concept.EQ_PRED,
    }),
    depends_on=(ChunkId.EXAMPLE_BUG_TRACKER_ANALYSIS,),
)
def _example_bug_tracker_code():
    source = _read_golden("bug-tracker")
    code = _extract_code_after_docstring(source)
    return (
        "### Worked Example: Bug Tracker — Code\n\n"
        "```python\n" + code + "\n```"
    )


@register(
    id=ChunkId.EXAMPLE_BUG_TRACKER_FULL,
    stages=S2,
    concepts=frozenset({
        Concept.OBLIGATION_TABLE, Concept.FUNCTION_ROLES, Concept.KEY_DISPATCH,
        Concept.HIT_MISS, Concept.PRESERVATION, Concept.NDEF_AXIOMS,
        Concept.GUARD_POLARITY, Concept.EQ_PRED,
    }),
    depends_on=(ChunkId.OBLIGATION_PATTERN,),
)
def _example_bug_tracker_full():
    from alspec.reference.worked_example import render
    return render()
