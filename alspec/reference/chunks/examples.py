from alspec.prompt_chunks import (
    ChunkId, Concept, Stage, BOTH, S1, S2, register,
)
from alspec.reference.worked_examples import ALL_EXAMPLES
from alspec.worked_example import RenderMode


@register(
    id=ChunkId.EXAMPLE_COUNTER,
    stages=BOTH,
    concepts=frozenset({Concept.OBLIGATION_TABLE, Concept.COMPLETENESS}),
    depends_on=(ChunkId.OBLIGATION_PATTERN,),
)
def _example_counter() -> str:
    return ALL_EXAMPLES["counter"].render(RenderMode.FULL)


@register(
    id=ChunkId.EXAMPLE_STACK,
    stages=BOTH,
    concepts=frozenset({Concept.SELECTORS, Concept.OBLIGATION_TABLE, Concept.NDEF_AXIOMS}),
    depends_on=(ChunkId.OBLIGATION_PATTERN,),
)
def _example_stack() -> str:
    return ALL_EXAMPLES["stack"].render(RenderMode.FULL)


@register(
    id=ChunkId.EXAMPLE_THERMOSTAT,
    stages=S2,
    concepts=frozenset({
        Concept.SELECTORS, Concept.PRESERVATION, Concept.DEFINEDNESS_BICONDITIONAL,
    }),
    depends_on=(ChunkId.OBLIGATION_PATTERN,),
)
def _example_thermostat() -> str:
    return ALL_EXAMPLES["thermostat"].render(RenderMode.FULL)


@register(
    id=ChunkId.EXAMPLE_BUG_TRACKER_ANALYSIS,
    stages=BOTH,
    concepts=frozenset({
        Concept.OBLIGATION_TABLE, Concept.FUNCTION_ROLES, Concept.KEY_DISPATCH,
        Concept.PRESERVATION, Concept.NDEF_AXIOMS, Concept.GUARD_POLARITY,
    }),
    depends_on=(ChunkId.OBLIGATION_PATTERN,),
)
def _example_bug_tracker_analysis() -> str:
    return ALL_EXAMPLES["bug-tracker"].render(RenderMode.ANALYSIS)


@register(
    id=ChunkId.EXAMPLE_BUG_TRACKER_CODE,
    stages=S2,
    concepts=frozenset({
        Concept.KEY_DISPATCH, Concept.HIT_MISS, Concept.PRESERVATION,
        Concept.NDEF_AXIOMS, Concept.GUARD_POLARITY, Concept.EQ_PRED,
    }),
    depends_on=(ChunkId.EXAMPLE_BUG_TRACKER_ANALYSIS,),
)
def _example_bug_tracker_code() -> str:
    return ALL_EXAMPLES["bug-tracker"].render(RenderMode.CODE)


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
def _example_bug_tracker_full() -> str:
    return ALL_EXAMPLES["bug-tracker"].render(RenderMode.FULL)


@register(
    id=ChunkId.EXAMPLE_BOUNDED_COUNTER,
    stages=BOTH,
    concepts=frozenset({
        Concept.PARTIAL_CONSTRUCTORS, Concept.DEFINEDNESS_BICONDITIONAL,
        Concept.OBLIGATION_TABLE, Concept.COMPLETENESS,
    }),
    depends_on=(ChunkId.OBLIGATION_PATTERN,),
)
def _example_bounded_counter() -> str:
    return ALL_EXAMPLES["bounded-counter"].render(RenderMode.FULL)


@register(
    id=ChunkId.EXAMPLE_TRAFFIC_LIGHT,
    stages=BOTH,
    concepts=frozenset({
        Concept.GENERATED_SORTS, Concept.STANDARD_PATTERNS,
        Concept.OBLIGATION_TABLE,
    }),
    depends_on=(ChunkId.OBLIGATION_PATTERN,),
)
def _example_traffic_light() -> str:
    return ALL_EXAMPLES["traffic-light"].render(RenderMode.FULL)


@register(
    id=ChunkId.EXAMPLE_QUEUE,
    stages=BOTH,
    concepts=frozenset({
        Concept.OBLIGATION_TABLE, Concept.NDEF_AXIOMS,
    }),
    depends_on=(ChunkId.OBLIGATION_PATTERN,),
)
def _example_queue() -> str:
    return ALL_EXAMPLES["queue"].render(RenderMode.FULL)


@register(
    id=ChunkId.EXAMPLE_SESSION_STORE,
    stages=BOTH,
    concepts=frozenset({
        Concept.SELECTORS,
        Concept.SELECTOR_EXTRACT,
        Concept.SELECTOR_FOREIGN,
        Concept.PARTIAL_CONSTRUCTORS,
        Concept.DEFINEDNESS_BICONDITIONAL,
        Concept.GUARD_POLARITY,
        Concept.BOTH_CASES,
        Concept.OBLIGATION_TABLE,
        Concept.NDEF_AXIOMS,
        Concept.GENERATED_SORTS,
        Concept.EQ_PRED,
        Concept.REFLEXIVITY_SYMMETRY_TRANSITIVITY,
    }),
    depends_on=(ChunkId.OBLIGATION_PATTERN,),
)
def _example_session_store() -> str:
    return ALL_EXAMPLES["session-store"].render(RenderMode.FULL)


@register(
    id=ChunkId.EXAMPLE_RATE_LIMITER,
    stages=BOTH,
    concepts=frozenset({
        Concept.SELECTORS,
        Concept.SELECTOR_EXTRACT,
        Concept.OBLIGATION_TABLE,
        Concept.COMPLETENESS,
        Concept.STANDARD_PATTERNS,
        Concept.PRESERVATION,
    }),
    depends_on=(ChunkId.OBLIGATION_PATTERN,),
)
def _example_rate_limiter() -> str:
    return ALL_EXAMPLES["rate-limiter"].render(RenderMode.FULL)


@register(
    id=ChunkId.EXAMPLE_DNS_ZONE,
    stages=BOTH,
    concepts=frozenset({
        Concept.KEY_DISPATCH,
        Concept.HIT_MISS,
        Concept.OBLIGATION_TABLE,
        Concept.NDEF_AXIOMS,
        Concept.GUARD_POLARITY,
        Concept.EQ_PRED,
        Concept.REFLEXIVITY_SYMMETRY_TRANSITIVITY,
        Concept.PRESERVATION,
        Concept.SHARED_KEY_SORT,
    }),
    depends_on=(ChunkId.OBLIGATION_PATTERN,),
)
def _example_dns_zone() -> str:
    return ALL_EXAMPLES["dns-zone"].render(RenderMode.FULL)
