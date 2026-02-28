"""
### Analysis: Temperature Sensor

#### 1. Identify Sorts
The system describes a sensor acting as a single-value recording mechanism where old values are unconditionally overwritten by new ones.
*   `Sensor`: The primary carrier sort representing the mutable state of the sensor. (atomic)
*   `Temp`: The values being recorded by the sensor. Treats as completely opaque values in this domain. (atomic)

#### 2. Classify Functions and Predicates
We need to model the creation, mutation, and observation of the sensor. We will introduce a `has_reading` predicate to serve as a guard for the partiality of `read`, standard for algebraic properties of single-value stores (akin to `empty` and `top` in Stacks).

**Functions (Constructors):**
*   `init : → Sensor` — Creates a new, uninitialized sensor with no temperature recorded yet.
*   `record : Sensor × Temp → Sensor` — Overwrites the sensor's current record with the given temperature.

**Functions (Observers):**
*   `read : Sensor →? Temp` — Retrieves the currently recorded temperature. **Partial**: undefined if the sensor was freshly initialized and has not yet recorded anything.

**Predicates (Observers):**
*   `has_reading : Sensor` — Predicate returning true iff a temperature has been recorded.

#### 3. Axiom Obligation Table

We pair the observers (`has_reading`, `read`) against the constructors (`init`, `record`).
Because `record` replaces whatever history the sensor had, we only need basic axioms corresponding to the immediate effect. No key-dispatch or hit/miss branches are necessary. 

| Observer | Constructor | Axiom Label | Behavior |
|----------|------------|-------------|----------|
| `has_reading` (pred) | `init` | `has_reading_init` | false |
| `has_reading` (pred) | `record` | `has_reading_record` | true |
| `read` (partial) | `init` | *(omitted)* | undefined (sensor has no reading yet) |
| `read` (partial) | `record` | `read_record` | `read(record(s, t)) = t` (the new reading ignores/replaces previous state) |

#### 4. System Completeness and Design Decisions
*   **Tricky Case / Design Decision**: How to represent "New readings replace old"? In an algebraic specification, avoiding state-history is as simple as making `read` only introspect the outermost `record` constructor. By stating `read(record(s, t)) = t`, any previous calls to `record` inside `s` become completely invisible to `read`, neatly enforcing the overwrite rule.
*   **Completeness Count**: We have 2 observer obligations × 2 constructors = 4 total pairs. 1 case is omitted due to partiality (`read(init)` is intentionally undefined). The 3 remaining obligations map 1:1 to the 3 implemented axioms. Spec is fully complete.
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


def temperature_sensor_spec() -> Spec:
    # Variables for axioms
    s = var("s", "Sensor")
    t = var("t", "Temp")

    # Define the domain signature
    sig = Signature(
        sorts={
            "Sensor": atomic("Sensor"),
            "Temp": atomic("Temp"),
        },
        functions={
            "init": fn("init", [], "Sensor"),
            "record": fn("record", [("s", "Sensor"), ("t", "Temp")], "Sensor"),
            "read": fn("read", [("s", "Sensor")], "Temp", total=False),
        },
        predicates={
            "has_reading": pred("has_reading", [("s", "Sensor")]),
        },
        generated_sorts={
            "Sensor": GeneratedSortInfo(
                constructors=("init", "record"),
                selectors={"record": {"read": "Temp"}},
            )
        },
    )

    # Fulfill the obligation table
    axioms = (
        # has_reading x init -> false
        Axiom(
            label="has_reading_init",
            formula=Negation(PredApp("has_reading", (const("init"),))),
        ),
        # has_reading x record -> true
        Axiom(
            label="has_reading_record",
            formula=forall([s, t], PredApp("has_reading", (app("record", s, t),))),
        ),
        # read x init -> explicitly undefined (partial observer on base constructor)
        Axiom(
            label="read_init_undef",
            formula=Negation(Definedness(app("read", const("init")))),
        ),
        # read x record -> returns the newly recorded reading (discards old state)
        Axiom(
            label="read_record",
            formula=forall([s, t], eq(app("read", app("record", s, t)), t)),
        ),
    )

    return Spec(name="TemperatureSensor", signature=sig, axioms=axioms)

