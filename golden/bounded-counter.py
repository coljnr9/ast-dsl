"""
### Axiom Specification Analysis: Bounded Counter

**Step 1: Identify Sorts**
- `Counter`: The central domain object modeling the counter state. Atomic.
- `Nat`: Required for counting the value and the maximum limit. Atomic.

**Step 2: Classify Functions and Predicates**
- `zero : -> Nat` (Constant)
- `suc : Nat -> Nat` (Constructor for Nat)
- `new : Nat -> Counter` (Constructor, total). Takes the maximum capacity.
- `inc : Counter ->? Counter` (Constructor, partial). Transitions the counter to the next state, but "fails at max".
- `val : Counter -> Nat` (Observer, total). Returns the current count.
- `max_val : Counter -> Nat` (Observer, total). While the prompt explicitly asks for `value` and `is-at-max`, we mathematically require the counter to remember its maximum in order to correctly compute whether subsequent increments hit the boundary.
- `is_at_max : Counter` (Predicate, total). Evaluates whether `val` has reached `max_val`.

**Step 3: Construct the Axiom Obligation Table**
Because `inc` is a partial constructor (undefined when `is_at_max(c)` holds), ANY observer inspecting `inc(c)` must split into two cases:
1. Hit a max (`is_at_max(c)`): undefined, and thus the case is omitted.
2. Under max (`not is_at_max(c)`): defined, so we specify the observer behavior.

| Observer | Constructor | Case | Definition Strategy |
|----------|------------|------|---------------------|
| `def` | `inc` | - | `def(inc(c)) ⇔ ¬is_at_max(c)` |
| `val` | `new` | - | `val(new(m)) = zero` |
| `val` | `inc` | `not is_at_max` | `val(inc(c)) = suc(val(c))` |
| `max_val` | `new` | - | `max_val(new(m)) = m` |
| `max_val` | `inc` | `not is_at_max` | preserved `max_val(inc(c)) = max_val(c)` |
| `is_at_max` | `new` | - | `<=> eq(zero, m)` (at max iff max is zero) |
| `is_at_max` | `inc` | `not is_at_max` | `<=> eq(suc(val(c)), max_val(c))` (at max iff new val is max) |

**Step 4: Design Decisions & Tricky Cases**
- **Explicit Definedness Boundary**: Under loose semantics, omitting axioms for the `is_at_max` case does not force `inc` to be undefined — it leaves the interpretation unconstrained. The `inc_def` axiom explicitly states `def(inc(c)) ⇔ ¬is_at_max(c)`, establishing that `inc` is defined exactly when not at max. Observer axioms over `inc` then only need the `¬is_at_max` branch; the `is_at_max` case is determined by strict error propagation (undefined constructor → undefined observation).
- **`max_val` Observer**: Without `max_val` (or a global constant limit), it would be impossible to derive whether `inc(c)` becomes at max just based on `suc(val(c))`. 

**Step 5: Completeness Check**
- 3 Observers × 2 Constructors = 6 obligations.
- `inc` triggers logical splitting per observer (1 guarded axiom per observer). 
Expected Total Axioms: 7 (1 definedness boundary + 6 observer obligations).
"""

from alspec import (
    Axiom, Definedness, GeneratedSortInfo, Implication, Negation, PredApp,
    Signature, Spec, atomic, fn, pred, var, app, const, eq, forall, iff
)

def bounded_counter_spec() -> Spec:
    # Variables definition
    c = var("c", "Counter")
    m = var("m", "Nat")
    
    # Signature definition
    sig = Signature(
        sorts={
            "Counter": atomic("Counter"),
            "Nat": atomic("Nat"),
        },
        functions={
            # Nat helpers
            "zero": fn("zero", [], "Nat"),
            "suc": fn("suc", [("n", "Nat")], "Nat"),
            
            # Counter constructors
            "new": fn("new", [("m", "Nat")], "Counter"),
            "inc": fn("inc", [("c", "Counter")], "Counter", total=False),
            
            # Counter observers
            "val": fn("val", [("c", "Counter")], "Nat"),
            "max_val": fn("max_val", [("c", "Counter")], "Nat"),
        },
        predicates={
            "is_at_max": pred("is_at_max", [("c", "Counter")]),
        },
        generated_sorts={
            "Counter": GeneratedSortInfo(
                constructors=("new", "inc"),
                selectors={},
            )
        },
    )
    
    # Axioms definition
    axioms = (
        # -- inc definedness boundary
        Axiom(
            label="inc_def",
            formula=forall([c],
                iff(
                    Definedness(app("inc", c)),
                    Negation(PredApp("is_at_max", (c,)))
                )
            )
        ),
        
        # -- val observer obligations
        Axiom(
            label="val_new",
            formula=forall([m],
                eq(app("val", app("new", m)), const("zero"))
            )
        ),
        Axiom(
            label="val_inc",
            formula=forall([c],
                Implication(
                    Negation(PredApp("is_at_max", (c,))),
                    eq(
                        app("val", app("inc", c)),
                        app("suc", app("val", c))
                    )
                )
            )
        ),
        
        # -- max_val observer obligations
        Axiom(
            label="max_val_new",
            formula=forall([m],
                eq(app("max_val", app("new", m)), m)
            )
        ),
        Axiom(
            label="max_val_inc",
            formula=forall([c],
                Implication(
                    Negation(PredApp("is_at_max", (c,))),
                    eq(
                        app("max_val", app("inc", c)),
                        app("max_val", c)
                    )
                )
            )
        ),
        
        # -- is_at_max predicate observer obligations
        Axiom(
            label="is_at_max_new",
            formula=forall([m],
                iff(
                    PredApp("is_at_max", (app("new", m),)),
                    eq(const("zero"), m)
                )
            )
        ),
        Axiom(
            label="is_at_max_inc",
            formula=forall([c],
                Implication(
                    Negation(PredApp("is_at_max", (c,))),
                    iff(
                        PredApp("is_at_max", (app("inc", c),)),
                        eq(app("suc", app("val", c)), app("max_val", c))
                    )
                )
            )
        )
    )
    
    return Spec(name="BoundedCounter", signature=sig, axioms=axioms)