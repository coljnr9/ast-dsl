"""
### Step 1: Identify Sorts
- `Stack`: The collection being modeled. This is our central domain sort, modeled as an atomic sort.
- `Elem`: The type of elements being stored in the stack. Modeled as an atomic sort.

### Step 2: Classify Functions and Predicates
Constructors (build values of `Stack`):
- `new : -> Stack` — Nullary constructor. Creates an empty stack.
- `push : Stack × Elem -> Stack` — Constructor. Adds an element to the top of the stack. Total.

Observers (query or decompose `Stack` values):
- `pop : Stack ->? Stack` — Function (partial). Removes the top element. Undefined on an empty stack.
- `top : Stack ->? Elem` — Function (partial). Returns the topmost element. Undefined on an empty stack.
- `empty : Stack` — Predicate. True iff the stack has no elements. Total.

### Step 3: Axiom Obligation Table
All observers (`pop`, `top`, `empty`) must be checked against all constructors (`new`, `push`). 

| Observer | Constructor | Axiom Label | Formula |
|----------|-------------|-------------|---------|
| `pop` | `new` | *(omitted)* | pop is partial, undefined on empty stack |
| `pop` | `push` | `pop_push` | `pop(push(s, e)) = s` |
| `top` | `new` | *(omitted)* | top is partial, undefined on empty stack |
| `top` | `push` | `top_push` | `top(push(s, e)) = e` |
| `empty` | `new` | `empty_new` | `empty(new)` |
| `empty` | `push` | `not_empty_push` | `¬ empty(push(s, e))` |

### Completeness Count
- `pop`: 2 constructors - 1 undefined = 1 axiom
- `top`: 2 constructors - 1 undefined = 1 axiom
- `empty`: 2 constructors = 2 axioms
Total expected axioms: 4.

### Step 4 & 5: Design Decisions
- This perfectly matches the `Stack` standard pattern in the basis library.
- We declare `empty` as a predicate, so we use `PredApp` internally (and `Negation(PredApp(...))` for the push case).
- `pop` and `top` are declared with `total=False`.
- `new` is a constant (nullary function), so we evaluate it with `const("new")`.
- `empty_new` does not require any variables, so its formula uses `PredApp` without a top-level `UniversalQuant` wrapper.
"""

from alspec import (
    Axiom,
    Negation,
    PredApp,
    Signature,
    Spec,
    atomic,
    fn,
    pred,
    var,
    app,
    const,
    eq,
    forall,
)

def stack_spec() -> Spec:
    sig = Signature(
        sorts={
            "Stack": atomic("Stack"),
            "Elem": atomic("Elem"),
        },
        functions={
            "new": fn("new", [], "Stack"),
            "push": fn("push", [("s", "Stack"), ("e", "Elem")], "Stack"),
            "pop": fn("pop", [("s", "Stack")], "Stack", total=False),
            "top": fn("top", [("s", "Stack")], "Elem", total=False),
        },
        predicates={
            "empty": pred("empty", [("s", "Stack")]),
        }
    )

    s = var("s", "Stack")
    e = var("e", "Elem")

    axioms = (
        Axiom(
            label="pop_push",
            formula=forall([s, e], eq(
                app("pop", app("push", s, e)),
                s
            ))
        ),
        Axiom(
            label="top_push",
            formula=forall([s, e], eq(
                app("top", app("push", s, e)),
                e
            ))
        ),
        Axiom(
            label="empty_new",
            formula=PredApp("empty", (const("new"),))
        ),
        Axiom(
            label="not_empty_push",
            formula=forall([s, e], Negation(
                PredApp("empty", (app("push", s, e),))
            ))
        ),
    )

    return Spec(name="Stack", signature=sig, axioms=axioms)