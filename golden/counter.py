"""
### Axiom Obligation Analysis

**Step 1: Identify Sorts**
- `Counter`: The central domain object, representing the state of the counter. It's an atomic, opaque sort whose behavior is dictated by functions.
- `Int`: An atomic sort used to represent the observable value of the counter. We use `Int` instead of `Nat` to allow for negative values when decrementing (since the prompt places no lower bound constraints on decrement).

**Step 2: Classify Functions and Predicates**
*Constructors* (Return a `Counter`):
- `new : -> Counter`: Creates a fresh counter.
- `inc : Counter -> Counter`: Increments the given counter state.
- `dec : Counter -> Counter`: Decrements the given counter state.
- `reset : Counter -> Counter`: Resets the counter state back to zero.

*Observers* (Return properties of `Counter`):
- `get_value : Counter -> Int`: Total observer that yields the integer value of the counter state.

*Helpers/Uninterpreted Functions* (Basis operations for `Int` domain):
- `zero : -> Int`: The constant mathematical integer 0.
- `succ : Int -> Int`: The successor function for integers.
- `pred : Int -> Int`: The predecessor function for integers.

**Step 3: Build the Axiom Obligation Table**
For our single total observer (`get_value`), we must consider each of the 4 constructors of its primary sort (`Counter`). No key dispatch is needed as we are not dealing with a store or finite map. 

| Observer | Constructor | Case | Axiom Label | Behavior |
|----------|-------------|------|-------------|----------|
| `get_value` | `new` | — | `get_value_new` | initial value is `zero` |
| `get_value` | `inc` | — | `get_value_inc` | `succ(get_value(c))` |
| `get_value` | `dec` | — | `get_value_dec` | `pred(get_value(c))` |
| `get_value` | `reset` | — | `get_value_reset` | forces value to `zero` |

**Design Decisions and Tricky Cases:**
- **Modeling Resets:** While we could define `reset(c) = new` entirely, in fully abstract algebraic behavior, we capture the behavior by specifying what the observer yields. Axiomatizing `get_value(reset(c)) = zero` suffices.
- **Integers over Naturals:** Because there’s no bound specified for decrements, mapping down below zero via `pred` is a safer bet, hence utilizing `Int` rather than purely `Nat`. The integer operations (`succ`, `pred`, `zero`) are treated uninterpreted under the assumption they are fulfilled by the standard integer algebraic basis.

**Completeness Count:**
- 1 observer × 4 constructors = 4 expected axioms.
- All functions are specified; no partiality requires omitted axioms.
"""

from alspec import (
    Axiom, GeneratedSortInfo, Signature, Spec,
    atomic, fn, var, app, const, eq, forall
)

def counter_spec() -> Spec:
    # Variables
    c = var("c", "Counter")
    
    # Signature definition
    sig = Signature(
        sorts={
            "Counter": atomic("Counter"),
            "Int": atomic("Int"),
        },
        functions={
            # Counter Constructors
            "new": fn("new", [], "Counter"),
            "inc": fn("inc", [("c", "Counter")], "Counter"),
            "dec": fn("dec", [("c", "Counter")], "Counter"),
            "reset": fn("reset", [("c", "Counter")], "Counter"),
            
            # Counter Observer
            "get_value": fn("get_value", [("c", "Counter")], "Int"),
            
            # Int Operations (Helpers)
            "zero": fn("zero", [], "Int"),
            "succ": fn("succ", [("n", "Int")], "Int"),
            "pred": fn("pred", [("n", "Int")], "Int"),
        },
        predicates={},
        generated_sorts={
            "Counter": GeneratedSortInfo(
                constructors=("new", "inc", "dec", "reset"),
                selectors={},
            )
        },
    )
    
    # Axioms defining observable behavior
    axioms = (
        Axiom(
            label="get_value_new",
            formula=eq(
                app("get_value", const("new")), 
                const("zero")
            ),
        ),
        Axiom(
            label="get_value_inc",
            formula=forall([c],
                eq(
                    app("get_value", app("inc", c)),
                    app("succ", app("get_value", c))
                ),
            ),
        ),
        Axiom(
            label="get_value_dec",
            formula=forall([c],
                eq(
                    app("get_value", app("dec", c)),
                    app("pred", app("get_value", c))
                ),
            ),
        ),
        Axiom(
            label="get_value_reset",
            formula=forall([c],
                eq(
                    app("get_value", app("reset", c)),
                    const("zero")
                ),
            ),
        ),
    )
    
    return Spec(name="SimpleCounter", signature=sig, axioms=axioms)