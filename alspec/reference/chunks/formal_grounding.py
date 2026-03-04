from alspec.prompt_chunks import (
    ChunkId, Concept, Stage, SIG_AX, SIG, AX, register,
)

@register(
    id=ChunkId.GENERATED_SORTS_ROLES,
    stages=SIG_AX,
    concepts=frozenset({Concept.GENERATED_SORTS, Concept.FUNCTION_ROLES, Concept.SELECTORS}),
    depends_on=(ChunkId.OBLIGATION_PATTERN,),
)
def _generated_sorts_roles():
    return """### Generated Sorts and Function Roles

A **generated sort** declares which constructors build all its values. In the signature:

```python
generated_sorts={
    "Stack": GeneratedSortInfo(
        constructors=("new", "push"),
        selectors={"push": {"top": "Elem", "pop": "Stack"}},
    )
}
```

Every function is classified by its role relative to the generated sort:

| Role | Definition |
|------|-----------|
| **Constructor** | Builds values of the sort. Listed in `constructors`. |
| **Observer** | First param is the sort; not a constructor. Owes axioms vs every constructor. |
| **Selector** | Observer that extracts one component from one constructor. Axiom is mechanical: `sel(ctor(x₁,...,xₙ)) = xᵢ`. Declared in `selectors`. |
| **Constant** | Nullary function producing a non-generated sort. Not a constructor. |
| **Uninterpreted** | Appears in axioms but not defined by them (e.g., `classify`). |

**Selectors** are declared per-constructor. `get_target` is a selector of `set_target`
(extracts `Temp`) but a regular observer of `read_temp` (preservation, not extraction).
A function is a selector when its axiom is unconditional component extraction:
`get_target(set_target(th, t)) = t`."""

@register(
    id=ChunkId.DISPATCH_RULES,
    stages=SIG_AX,
    concepts=frozenset({Concept.KEY_DISPATCH, Concept.HIT_MISS, Concept.SHARED_KEY_SORT}),
    depends_on=(ChunkId.GENERATED_SORTS_ROLES,),
)
def _dispatch_rules():
    return """### Key Dispatch: When Cells Split into HIT/MISS

An obligation cell (observer, constructor) splits into HIT and MISS sub-cells when:

1. The observer takes a parameter of sort `K` beyond its primary sort argument
2. The constructor also takes a parameter of sort `K`
3. An equality predicate `eq_K : K × K` is declared in the signature

The HIT axiom is guarded by `eq_K(k, k2)`; the MISS axiom by `¬eq_K(k, k2)`.

**Example:** `get_rdata : Zone × DomainName × RecordType → RData` and
`add_record : Zone × DomainName × RecordType × RData × Nat → Zone` share `DomainName`, and
`eq_name : DomainName × DomainName` exists → the cell splits into HIT and MISS.

**Critical: domain guards ≠ dispatch guards.** In door-lock, `get_state(lock(l, c))`
has a guard `eq_code(c, get_code(l))`, but the cell is PLAIN — `get_state : Lock → State`
has no `Code` parameter. The `eq_code` is domain logic, not structural key dispatch.
Dispatch requires a shared key sort in the *profiles* of both observer and constructor."""

@register(
    id=ChunkId.CELL_TIERS,
    stages=AX,
    concepts=frozenset({Concept.SELECTORS, Concept.SELECTOR_EXTRACT, Concept.SELECTOR_FOREIGN, Concept.CELL_TIERS}),
    depends_on=(ChunkId.GENERATED_SORTS_ROLES,),
)
def _cell_tiers():
    return """### Cell Tiers — How Much Reasoning Each Cell Requires

| Tier | Meaning | Pattern |
|------|---------|---------|
| **SELECTOR_EXTRACT** | Selector applied to its own constructor. Mechanical. | `top(push(s, e)) = e` |
| **SELECTOR_FOREIGN** | Selector applied to a different constructor. Mechanical. | `¬def(top(new))` |
| **DOMAIN** | Everything else. Requires domain reasoning. | Equations, preservation, guards, biconditionals |

Selector cells are self-writing — no domain knowledge needed. Focus your reasoning on DOMAIN cells."""

@register(
    id=ChunkId.PRESERVATION_COLLAPSE,
    stages=AX,
    concepts=frozenset({Concept.PRESERVATION, Concept.KEY_DISPATCH}),
    depends_on=(ChunkId.DISPATCH_RULES,),
)
def _preservation_collapse():
    return """### Preservation Collapse

When a constructor does not affect an observer for ANY key, collapse HIT and MISS into
one universal axiom:

```python
# One axiom covers both cases — last_input is orthogonal to expire:
Axiom("last_input_expire", forall([s],
    eq(app("last_input", app("expire", s)),
       app("last_input", s))
))
```

No equality-predicate guard needed — the equation holds unconditionally. Use this when
a constructor is orthogonal to an observer (e.g., expiring a session does not change
its stored token input — the value is preserved exactly, including propagating
undefinedness when `last_input` is itself undefined)."""

@register(
    id=ChunkId.DOMAIN_SUBCASES,
    stages=AX,
    concepts=frozenset({Concept.MULTI_COVERED, Concept.CASE_SPLITS}),
    depends_on=(ChunkId.OBLIGATION_PATTERN,),
)
def _domain_subcases():
    return """### Domain Sub-Cases (Multiple Axioms per Cell)

Sometimes a single obligation cell requires multiple axioms because behavior depends
on the structure of the inner argument. This is NOT key dispatch — no equality predicate.

**Queue example:** `(dequeue, enqueue)` needs two axioms:
```python
# Base case: 1-element queue
forall([e], eq(app("dequeue", app("enqueue", const("empty"), e)), const("empty")))
# Recursive case: >1 elements
forall([q, e1, e2], eq(
    app("dequeue", app("enqueue", app("enqueue", q, e1), e2)),
    app("enqueue", app("dequeue", app("enqueue", q, e1)), e2)
))
```

Both axioms fill the same cell. This is valid — the obligation table counts cells, not axioms."""

@register(
    id=ChunkId.EQ_PRED_BASIS,
    stages=AX,
    concepts=frozenset({Concept.EQ_PRED, Concept.REFLEXIVITY_SYMMETRY_TRANSITIVITY}),
    depends_on=(ChunkId.DISPATCH_RULES,),
)
def _eq_pred_basis():
    return """### Equality Predicate Basis Axioms

Every equality predicate needs three structural axioms:

```python
Axiom("eq_token_refl",  forall([k], pred_app("eq_token", k, k)))
Axiom("eq_token_sym",   forall([k, k2], implication(
    pred_app("eq_token", k, k2), pred_app("eq_token", k2, k))))
Axiom("eq_token_trans",  forall([k, k2, k3], implication(
    conjunction(pred_app("eq_token", k, k2), pred_app("eq_token", k2, k3)),
    pred_app("eq_token", k, k3))))
```

These are NOT obligation cells — they don't involve constructors of the generated sort.
Write them for every `eq_*` predicate in the signature."""
