from alspec.prompt_chunks import (
    ChunkId, Concept, Stage, BOTH, S1, S2, register,
)

@register(
    id=ChunkId.WF_CHECKLIST,
    stages=BOTH,
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
    stages=BOTH,
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
    stages=BOTH,
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
    stages=S2,
    concepts=frozenset({Concept.PARTIAL_FUNCTIONS, Concept.DEFINEDNESS, Concept.NDEF_AXIOMS}),
    depends_on=(ChunkId.LOOSE_SEMANTICS_RULE,),
)
def _partial_fn_patterns():
    return """### Partial Function Patterns

**Pattern 1 — Partial constructor with definedness biconditional:**
```python
Axiom("withdraw_def", forall([a, n], iff(
    Definedness(app("withdraw", a, n)),
    PredApp("geq", (app("balance", a), n))
)))
```

**Pattern 2 — Partial observer, explicit undefinedness:**
```python
Axiom("pop_new_undef", Negation(Definedness(app("pop", const("new")))))
Axiom("get_assignee_create_hit", forall([s, k, k2, t, b], Implication(
    PredApp("eq_id", (k, k2)),
    Negation(Definedness(app("get_assignee", app("create_ticket", s, k, t, b), k2)))
)))
```

**Pattern 3 — Total constructor with existence guard (both polarities):**
```python
# resolve_ticket hit WITH ticket
Axiom("get_status_resolve_hit", forall([s, k, k2], Implication(
    PredApp("eq_id", (k, k2)),
    Implication(PredApp("has_ticket", (s, k)),
        eq(app("get_status", app("resolve_ticket", s, k), k2), const("resolved"))
    )
)))
# resolve_ticket hit WITHOUT ticket — must also be stated
Axiom("get_status_resolve_hit_noticket", forall([s, k, k2], Implication(
    PredApp("eq_id", (k, k2)),
    Implication(Negation(PredApp("has_ticket", (s, k))),
        eq(app("get_status", app("resolve_ticket", s, k), k2), app("get_status", s, k2))
    )
)))
```"""

@register(
    id=ChunkId.GUARD_POLARITY,
    stages=S2,
    concepts=frozenset({Concept.GUARD_POLARITY, Concept.BOTH_CASES}),
    depends_on=(ChunkId.PARTIAL_FN_PATTERNS,),
)
def _guard_polarity():
    return """### Guard Polarity Rule

When an axiom is guarded by a predicate (like `has_ticket`, `is_at_max`, or a state check),
write axioms for BOTH the positive and negative case. The positive case gives the real behavior;
the negative case gives the no-op/delegation behavior. Omitting either leaves models unconstrained."""
