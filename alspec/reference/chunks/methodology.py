from alspec.prompt_chunks import (
    ChunkId, Concept, Stage, SIG_AX, SIG, AX, register,
)

@register(
    id=ChunkId.WF_CHECKLIST,
    stages=SIG_AX,
    concepts=frozenset({Concept.WELL_FORMEDNESS}),
    depends_on=(ChunkId.FORMAL_FRAME,),
)
def _wf_checklist():
    return """### Well-Formedness Checklist

1. Every sort referenced must be declared.
2. Every function/predicate used in terms must be declared.
3. Variable sorts must match function profiles.
4. Equation sides must have the same sort.
5. Field access requires a product sort.
6. Constants are zero-arity functions — declare with `fn("zero", [], "Nat")`, use with `const("zero")`.
7. Mark partial functions with `total=False`."""

@register(
    id=ChunkId.OBLIGATION_PATTERN,
    stages=SIG_AX,
    concepts=frozenset({Concept.OBLIGATION_TABLE, Concept.COMPLETENESS}),
    depends_on=(ChunkId.WF_CHECKLIST,),
)
def _obligation_pattern():
    return """### Axiom Obligation Pattern

For each **observer** (function or predicate whose first argument is the generated sort)
and each **constructor** of that sort, write **one axiom per (observer, constructor) pair**.

This is the obligation table — a completeness checklist, not a guideline.

1. List the constructors of the observer's primary argument sort.
2. For each constructor, write an axiom specifying the observer applied to that constructor.
3. For partial observers, every constructor still needs an axiom — equations where defined,
   `Negation(Definedness(...))` where undefined. No exceptions.

**Completeness check:** If a sort has `k` constructors and `n` observers,
the obligation table has `n × k` cells (before key dispatch splits).
Every cell must be filled."""

@register(
    id=ChunkId.LOOSE_SEMANTICS_RULE,
    stages=SIG_AX,
    concepts=frozenset({Concept.LOOSE_SEMANTICS, Concept.NO_OMISSIONS}),
    depends_on=(ChunkId.OBLIGATION_PATTERN,),
)
def _loose_semantics_rule():
    return """### Loose Semantics — Why Every Cell Must Be Filled

This DSL uses **loose semantics**: the models of a spec are ALL algebras satisfying
the axioms. There is no distinguished "intended" model.

**Silence is permission, not prohibition.** If the axiom set says nothing about
`f(c(...))`, every model is free to interpret that case however it wants. Omitting
an axiom does NOT encode undefinedness — it leaves the value *unconstrained*.

To force undefinedness, write an explicit `Negation(Definedness(...))` axiom.
The `total=False` declaration merely *permits* undefinedness; it does not *cause* it.

A complete spec has no silent gaps in the obligation table."""

@register(
    id=ChunkId.PARTIAL_FN_PATTERNS,
    stages=AX,
    concepts=frozenset({Concept.PARTIAL_FUNCTIONS, Concept.DEFINEDNESS, Concept.NDEF_AXIOMS}),
    depends_on=(ChunkId.LOOSE_SEMANTICS_RULE,),
)
def _partial_fn_patterns():
    return """### Partial Function Patterns

**Pattern 1 — Partial constructor with definedness biconditional:**
```python
Axiom("refresh_def", forall([s], iff(
    Definedness(app("refresh", s)),
    eq(app("get_status", s), const("active"))
)))
```

**Pattern 2 — Partial observer, explicit undefinedness:**
```python
Axiom("pop_new_undef", Negation(Definedness(app("pop", const("new")))))
Axiom("last_input_create_undef", forall([t],
    Negation(Definedness(app("last_input", app("create", t))))
))
```

**Pattern 3 — Total constructor with domain guard (both polarities):**
```python
# is_verified × verify — POSITIVE guard: correct token on active session
Axiom("is_verified_verify_pos", forall([s, t], Implication(
    Conjunction((
        PredApp("eq_token", (t, app("get_token", s))),
        eq(app("get_status", s), const("active")),
    )),
    PredApp("is_verified", (app("verify", s, t),))
)))
# is_verified × verify — NEGATIVE guard: wrong token or expired session
Axiom("is_verified_verify_neg", forall([s, t], Implication(
    Negation(Conjunction((
        PredApp("eq_token", (t, app("get_token", s))),
        eq(app("get_status", s), const("active")),
    ))),
    iff(
        PredApp("is_verified", (app("verify", s, t),)),
        PredApp("is_verified", (s,)),
    )
)))
```"""

@register(
    id=ChunkId.GUARD_POLARITY,
    stages=AX,
    concepts=frozenset({Concept.GUARD_POLARITY, Concept.BOTH_CASES}),
    depends_on=(ChunkId.PARTIAL_FN_PATTERNS,),
)
def _guard_polarity():
    return """### Guard Polarity Rule

When an axiom is guarded by a predicate (like `is_verified`, `over_limit`, or a state check),
write axioms for BOTH the positive and negative case. The positive case gives the real behavior;
the negative case gives the no-op/delegation behavior. Omitting either leaves models unconstrained."""
