"""
### Step 1: Identify Sorts
- `Stack`: The collection being modeled. This is our central domain sort, modeled as an atomic sort.
- `Elem`: The type of elements being stored in the stack. Modeled as an atomic sort.

### Step 2: Classify Functions and Predicates
Constructors (build values of `Stack`):
- `new : -> Stack` — Nullary constructor. Creates an empty stack.
- `push : Stack × Elem -> Stack` — Constructor. Adds an element to the top of the stack. Total.

Selectors (component extractors declared for `push`):
- `pop : Stack ->? Stack` — Selector of `push`. Extracts the Stack component. Undefined on `new`.
- `top : Stack ->? Elem` — Selector of `push`. Extracts the Elem component. Undefined on `new`.

Predicate observers:
- `empty : Stack` — Predicate. True iff the stack has no elements. Total.

### Step 3: Axiom Obligation Table
All observers (`pop`, `top`, `empty`) must be checked against all constructors (`new`, `push`).

Under loose semantics, every cell must be filled — no omissions.
`pop` and `top` are selectors of `push`, so:
  - `SELECTOR_EXTRACT` on `push`: mechanically derivable extraction axiom
  - `SELECTOR_FOREIGN` on `new`: must write explicit ¬def(...)

| Observer | Constructor | Cell Type | Formula |
|----------|-------------|-----------|---------|
| `pop` | `new` | `SELECTOR_FOREIGN` | `¬def(pop(new))` — explicit undefinedness |
| `pop` | `push` | `SELECTOR_EXTRACT` | `pop(push(s, e)) = s` |
| `top` | `new` | `SELECTOR_FOREIGN` | `¬def(top(new))` — explicit undefinedness |
| `top` | `push` | `SELECTOR_EXTRACT` | `top(push(s, e)) = e` |
| `empty` | `new` | `DOMAIN` | `empty(new)` |
| `empty` | `push` | `DOMAIN` | `¬ empty(push(s, e))` |

### Completeness Count
- `pop`: 2 constructors = 2 axioms (1 undefinedness + 1 equation)
- `top`: 2 constructors = 2 axioms (1 undefinedness + 1 equation)
- `empty`: 2 constructors = 2 axioms
Total expected axioms: 6.

### Step 4 & 5: Design Decisions
- This perfectly matches the `Stack` standard pattern in the basis library.
- We declare `empty` as a predicate, so we use `PredApp` internally (and `Negation(PredApp(...))` for the push case).
- `pop` and `top` are declared with `total=False` and registered as selectors in `generated_sorts`.
- `new` is a constant (nullary function), so we evaluate it with `const("new")`.
- `empty_new` does not require any variables, so its formula uses `PredApp` without a top-level `UniversalQuant` wrapper.
- `pop_new_undef` and `top_new_undef` are mandatory — omitting them would leave the value unconstrained under loose semantics.
"""

from alspec import (
    Axiom,
    Definedness,
    GeneratedSortInfo,
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
        },
        generated_sorts={
            "Stack": GeneratedSortInfo(
                constructors=("new", "push"),
                selectors={"push": {"top": "Elem", "pop": "Stack"}},
            )
        },
    )

    s = var("s", "Stack")
    e = var("e", "Elem")

    axioms = (
        # pop × new: SELECTOR_FOREIGN — explicit undefinedness required
        Axiom(
            label="pop_new_undef",
            formula=Negation(Definedness(app("pop", const("new"))))
        ),
        # pop × push: SELECTOR_EXTRACT — mechanically derivable
        Axiom(
            label="pop_push",
            formula=forall([s, e], eq(
                app("pop", app("push", s, e)),
                s
            ))
        ),
        # top × new: SELECTOR_FOREIGN — explicit undefinedness required
        Axiom(
            label="top_new_undef",
            formula=Negation(Definedness(app("top", const("new"))))
        ),
        # top × push: SELECTOR_EXTRACT — mechanically derivable
        Axiom(
            label="top_push",
            formula=forall([s, e], eq(
                app("top", app("push", s, e)),
                e
            ))
        ),
        # empty × new: DOMAIN — base case for predicate
        Axiom(
            label="empty_new",
            formula=PredApp("empty", (const("new"),))
        ),
        # empty × push: DOMAIN — recursive case
        Axiom(
            label="not_empty_push",
            formula=forall([s, e], Negation(
                PredApp("empty", (app("push", s, e),))
            ))
        ),
    )

    return Spec(name="Stack", signature=sig, axioms=axioms)