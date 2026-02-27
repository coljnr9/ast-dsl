"""
### Analysis of the Boolean Flag Specification

**1. Identify Sorts**
We need to model the state of the feature flag itself.
- `Flag`: We use an atomic sort to represent the feature flag state machine. No additional sorts are needed since the status (enabled/disabled) can be elegantly modeled as a predicate rather than returning a boolean value.

**2. Classify Functions & Predicates**
- `init : → Flag`
  - **Role:** Constructor. Creates a fresh feature flag in its default state.
- `enable : Flag → Flag`
  - **Role:** Constructor. Transitions the feature flag to the enabled state.
- `disable : Flag → Flag`
  - **Role:** Constructor. transitions the feature flag to the disabled state.
- `is_enabled : Flag`
  - **Role:** Predicate Observer. Checks whether the flag is currently enabled.

*Design Decision:* We assume the initial state of the flag (`init`) is disabled by default. Using a predicate `is_enabled` over the `Flag` sort is more idiomatic in CASL fragments than defining a `Bool` sort and returning it from an observer function.

**3. Axiom Obligation Table**
For our single observer `is_enabled`, we generate obligations against every constructor.

| Observer | Constructor | Axiom Label | Formula / Behavior |
|----------|-------------|-------------|--------------------|
| `is_enabled` | `init` | `is_enabled_init` | `¬ is_enabled(init)` |
| `is_enabled` | `enable(f)` | `is_enabled_enable` | `is_enabled(enable(f))` |
| `is_enabled` | `disable(f)` | `is_enabled_disable` | `¬ is_enabled(disable(f))` |

**4. Completeness Count**
- Constructors: 3 (`init`, `enable`, `disable`)
- Observers: 1 (`is_enabled`)
- Expected Axioms: 3 × 1 = 3 axioms.
- We have 3 axioms, mapping perfectly to our complete grid. No partial functions or missing definitions.
"""

from alspec import (
    Axiom, Negation, PredApp,
    Signature, Spec, atomic, fn, pred, var, app, const, forall
)

def boolean_flag_spec() -> Spec:
    f = var("f", "Flag")
    
    sig = Signature(
        sorts={
            "Flag": atomic("Flag"),
        },
        functions={
            # Constructors
            "init": fn("init", [], "Flag"),
            "enable": fn("enable", [("f", "Flag")], "Flag"),
            "disable": fn("disable", [("f", "Flag")], "Flag"),
        },
        predicates={
            # Observer
            "is_enabled": pred("is_enabled", [("f", "Flag")]),
        }
    )
    
    axioms = (
        # init constructor: A new flag is disabled by default
        Axiom(
            label="is_enabled_init",
            formula=Negation(PredApp("is_enabled", (const("init"),)))
        ),
        
        # enable constructor: enabling the flag makes it enabled
        Axiom(
            label="is_enabled_enable",
            formula=forall([f], PredApp("is_enabled", (app("enable", f),)))
        ),
        
        # disable constructor: disabling the flag makes it disabled
        Axiom(
            label="is_enabled_disable",
            formula=forall([f], Negation(PredApp("is_enabled", (app("disable", f),))))
        ),
    )
    
    return Spec(name="BooleanFlag", signature=sig, axioms=axioms)