from alspec.prompt_chunks import (
    ChunkId, Concept, Stage, BOTH, S1, S2, register,
)

@register(
    id=ChunkId.ROLE_PREAMBLE,
    stages=BOTH,
    concepts=frozenset(),
)
def _role_preamble():
    return (
        "You are a domain modeling expert specializing in algebraic specification.\n"
        "Write specifications using the many-sorted algebraic specification DSL "
        "described below."
    )

@register(
    id=ChunkId.FORMAL_FRAME,
    stages=BOTH,
    concepts=frozenset({Concept.SIGNATURES, Concept.WELL_SORTEDNESS, Concept.TERM_VS_FORMULA}),
    depends_on=(ChunkId.ROLE_PREAMBLE,),
)
def _formal_frame():
    from alspec.reference.formal_frame import render
    return render()

@register(
    id=ChunkId.TYPE_GRAMMAR,
    stages=BOTH,
    concepts=frozenset({Concept.AST_TYPES, Concept.TERM_VS_FORMULA}),
    depends_on=(ChunkId.FORMAL_FRAME,),
)
def _type_grammar():
    from alspec.reference.type_grammar import render
    return render()

@register(
    id=ChunkId.API_HELPERS,
    stages=BOTH,
    concepts=frozenset({Concept.BUILDER_API}),
    depends_on=(ChunkId.TYPE_GRAMMAR,),
)
def _api_helpers():
    from alspec.reference.api_reference import render
    return render()

@register(
    id=ChunkId.BASIS_CATALOG,
    stages=BOTH,
    concepts=frozenset({Concept.STANDARD_PATTERNS}),
    depends_on=(ChunkId.API_HELPERS,),
)
def _basis_catalog():
    from alspec.reference.basis_catalog import render
    return render()
