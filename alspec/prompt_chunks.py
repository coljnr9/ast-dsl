from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass
from enum import Enum, auto
from typing import Callable

logger = logging.getLogger(__name__)


class PromptAssemblyError(Exception):
    """Raised when prompt assembly fails validation."""

    pass


class Stage(Enum):
    """Pipeline stages that consume prompt chunks.

    ANALYSIS and OBLIGATION don't use the chunk system but are included
    for completeness and future extensibility.
    """

    ANALYSIS = auto()    # Stage 1 — domain analysis (no chunks currently)
    SIGNATURE = auto()   # Stage 2 — signature generation
    OBLIGATION = auto()  # Stage 3 — deterministic obligation table (no chunks currently)
    AXIOMS = auto()      # Stage 4 — axiom generation


class Concept(Enum):
    """Concepts taught by chunks. Used for DoE analysis."""

    SIGNATURES = auto()
    WELL_SORTEDNESS = auto()
    TERM_VS_FORMULA = auto()
    AST_TYPES = auto()
    BUILDER_API = auto()
    STANDARD_PATTERNS = auto()
    WELL_FORMEDNESS = auto()
    OBLIGATION_TABLE = auto()
    COMPLETENESS = auto()
    LOOSE_SEMANTICS = auto()
    NO_OMISSIONS = auto()
    PARTIAL_FUNCTIONS = auto()
    DEFINEDNESS = auto()
    NDEF_AXIOMS = auto()
    PARTIAL_CONSTRUCTORS = auto()
    DEFINEDNESS_BICONDITIONAL = auto()
    GUARD_POLARITY = auto()
    BOTH_CASES = auto()
    GENERATED_SORTS = auto()
    FUNCTION_ROLES = auto()
    SELECTORS = auto()
    KEY_DISPATCH = auto()
    HIT_MISS = auto()
    SHARED_KEY_SORT = auto()
    SELECTOR_EXTRACT = auto()
    SELECTOR_FOREIGN = auto()
    CELL_TIERS = auto()
    PRESERVATION = auto()
    MULTI_COVERED = auto()
    CASE_SPLITS = auto()
    EQ_PRED = auto()
    REFLEXIVITY_SYMMETRY_TRANSITIVITY = auto()


class ChunkId(Enum):
    """Every prompt chunk has a unique typed identifier.

    Naming convention: CATEGORY_TOPIC
    """

    # Foundation
    ROLE_PREAMBLE = auto()
    FORMAL_FRAME = auto()
    TYPE_GRAMMAR = auto()
    API_HELPERS = auto()

    # Basis Library
    BASIS_CATALOG = auto()

    # Methodology (decomposed from current methodology.py)
    WF_CHECKLIST = auto()
    OBLIGATION_PATTERN = auto()
    LOOSE_SEMANTICS_RULE = auto()
    PARTIAL_FN_PATTERNS = auto()
    GUARD_POLARITY = auto()

    # New formal grounding (from THEORY.md §7-9)
    GENERATED_SORTS_ROLES = auto()
    DISPATCH_RULES = auto()
    CELL_TIERS = auto()
    PRESERVATION_COLLAPSE = auto()
    DOMAIN_SUBCASES = auto()
    EQ_PRED_BASIS = auto()

    # Worked examples
    EXAMPLE_COUNTER = auto()
    EXAMPLE_STACK = auto()
    EXAMPLE_THERMOSTAT = auto()
    EXAMPLE_BUG_TRACKER_ANALYSIS = auto()
    EXAMPLE_BUG_TRACKER_CODE = auto()
    EXAMPLE_BUG_TRACKER_FULL = auto()
    # New saturation ladder examples
    EXAMPLE_BOUNDED_COUNTER = auto()
    EXAMPLE_TRAFFIC_LIGHT = auto()
    EXAMPLE_QUEUE = auto()
    EXAMPLE_SESSION_STORE = auto()
    EXAMPLE_RATE_LIMITER = auto()
    EXAMPLE_DNS_ZONE = auto()
    EXAMPLE_CONNECTION = auto()
    # Stage 2 variants — same examples, rendered with RenderMode.SPEC (analysis + full axiom code)
    EXAMPLE_SESSION_STORE_SPEC = auto()
    EXAMPLE_RATE_LIMITER_SPEC = auto()
    EXAMPLE_DNS_ZONE_SPEC = auto()
    EXAMPLE_CONNECTION_SPEC = auto()

    # Stage-specific methodology (output format + analysis steps)
    SIGNATURE_METHODOLOGY = auto()
    AXIOMS_METHODOLOGY = auto()


# Convenience sets for chunk registration (only SIGNATURE and AXIOMS use chunks)
SIG = frozenset({Stage.SIGNATURE})
AX = frozenset({Stage.AXIOMS})
SIG_AX = frozenset({Stage.SIGNATURE, Stage.AXIOMS})


@dataclass(frozen=True)
class PromptChunk:
    """A self-contained unit of prompt content."""

    id: ChunkId
    stages: frozenset[Stage]
    concepts: frozenset[Concept]
    depends_on: tuple[ChunkId, ...]
    render: Callable[[], str]

    @property
    def name(self) -> str:
        return self.id.name


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_REGISTRY: dict[ChunkId, PromptChunk] = {}


def register(
    id: ChunkId,
    stages: frozenset[Stage],
    concepts: frozenset[Concept],
    depends_on: tuple[ChunkId, ...] = (),
) -> Callable[[Callable[[], str]], Callable[[], str]]:
    """Decorator to register a chunk renderer.

    The decorated function returns str (the chunk content).
    It is stored in the registry and remains callable.

    Raises ValueError at import time if the ChunkId is already registered.
    """

    def decorator(fn: Callable[[], str]) -> Callable[[], str]:
        if id in _REGISTRY:
            raise ValueError(f"Duplicate chunk registration: {id.name}")
        _REGISTRY[id] = PromptChunk(
            id=id,
            stages=stages,
            concepts=concepts,
            depends_on=depends_on,
            render=fn,
        )
        return fn

    return decorator


def get_chunk(id: ChunkId) -> PromptChunk:
    """Look up a registered chunk. Raises KeyError if not found."""
    if id not in _REGISTRY:
        raise KeyError(f"Chunk not registered: {id.name}")
    return _REGISTRY[id]


def get_all_chunks() -> dict[ChunkId, PromptChunk]:
    """Return a copy of the full registry."""
    return dict(_REGISTRY)


def chunks_for_stage(stage: Stage) -> list[PromptChunk]:
    """Return all chunks relevant to a given stage, in registration order."""
    return [c for c in _REGISTRY.values() if stage in c.stages]


# ---------------------------------------------------------------------------
# Prompt Assembly
# ---------------------------------------------------------------------------


def assemble_prompt(
    chunk_ids: list[ChunkId],
    stage: Stage,
    *,
    validate_deps: bool = True,
    validate_stage: bool = True,
) -> str:
    """Assemble a prompt from an ordered list of chunk IDs.

    Parameters
    ----------
    chunk_ids:
        Ordered list of chunks to include. Order determines prompt section order.
    stage:
        The pipeline stage this prompt is for. Used for validation.
    validate_deps:
        If True, verify all dependencies are present and appear before dependents.
    validate_stage:
        If True, verify all chunks are relevant to the given stage.

    Raises
    ------
    PromptAssemblyError:
        On unknown chunk, missing dependency, wrong stage, or dependency cycle.
    """
    chunks: list[PromptChunk] = []
    seen: set[ChunkId] = set()

    for cid in chunk_ids:
        chunk = _REGISTRY.get(cid)
        if chunk is None:
            raise PromptAssemblyError(f"Unknown chunk: {cid.name}")

        if validate_stage and stage not in chunk.stages:
            raise PromptAssemblyError(
                f"Chunk {cid.name} is not relevant to {stage.name} "
                f"(valid: {', '.join(s.name for s in chunk.stages)})"
            )

        if validate_deps:
            for dep in chunk.depends_on:
                if dep not in seen:
                    raise PromptAssemblyError(
                        f"Chunk {cid.name} depends on {dep.name}, "
                        f"which must appear earlier in the chunk list"
                    )

        chunks.append(chunk)
        seen.add(cid)

    sections = [chunk.render() for chunk in chunks]
    return "\n\n".join(sections)


def build_default_prompt(stage: Stage) -> str:
    """Build the default prompt for a stage using the default chunk list.

    Uses the curated default ordering for each stage.
    """
    defaults = _DEFAULT_CONFIGS[stage]
    return assemble_prompt(defaults, stage, validate_deps=False)


# Trigger chunk registration by importing the content modules
import alspec.reference.chunks  # noqa: F401


def _topological_sort(chunks: list[PromptChunk]) -> list[PromptChunk]:
    """Sort chunks respecting depends_on. Stable within dependency levels."""
    id_set = {c.id for c in chunks}
    by_id = {c.id: c for c in chunks}

    in_degree: dict[ChunkId, int] = {c.id: 0 for c in chunks}
    dependents: dict[ChunkId, list[ChunkId]] = {c.id: [] for c in chunks}

    for c in chunks:
        for dep in c.depends_on:
            if dep in id_set:
                in_degree[c.id] += 1
                dependents[dep].append(c.id)

    queue: deque[ChunkId] = deque(cid for cid in in_degree if in_degree[cid] == 0)
    result: list[PromptChunk] = []

    while queue:
        cid = queue.popleft()
        result.append(by_id[cid])
        for dependent in dependents[cid]:
            in_degree[dependent] -= 1
            if in_degree[dependent] == 0:
                queue.append(dependent)

    if len(result) != len(chunks):
        missing = id_set - {c.id for c in result}
        raise PromptAssemblyError(
            f"Dependency cycle involving: {', '.join(m.name for m in missing)}"
        )

    return result


_DEFAULT_CONFIGS: dict[Stage, list[ChunkId]] = {
    Stage.SIGNATURE: [
        ChunkId.ROLE_PREAMBLE,
        ChunkId.TYPE_GRAMMAR,
        ChunkId.API_HELPERS,
        ChunkId.EXAMPLE_SESSION_STORE,
        ChunkId.EXAMPLE_RATE_LIMITER,
        ChunkId.EXAMPLE_DNS_ZONE,
        ChunkId.OBLIGATION_PATTERN,
        ChunkId.GENERATED_SORTS_ROLES,
        ChunkId.DISPATCH_RULES,
        ChunkId.SIGNATURE_METHODOLOGY,
    ],
    Stage.AXIOMS: [
        ChunkId.ROLE_PREAMBLE,
        ChunkId.FORMAL_FRAME,
        ChunkId.TYPE_GRAMMAR,
        ChunkId.API_HELPERS,
        ChunkId.WF_CHECKLIST,
        ChunkId.OBLIGATION_PATTERN,
        ChunkId.LOOSE_SEMANTICS_RULE,
        ChunkId.GENERATED_SORTS_ROLES,
        ChunkId.DISPATCH_RULES,
        ChunkId.CELL_TIERS,
        ChunkId.PARTIAL_FN_PATTERNS,
        ChunkId.GUARD_POLARITY,
        ChunkId.PRESERVATION_COLLAPSE,
        ChunkId.EQ_PRED_BASIS,
        ChunkId.EXAMPLE_SESSION_STORE_SPEC,
        ChunkId.EXAMPLE_RATE_LIMITER_SPEC,
        ChunkId.EXAMPLE_DNS_ZONE_SPEC,
        ChunkId.AXIOMS_METHODOLOGY,
    ],
}
