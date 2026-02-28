"""
## Step 1 — Identify sorts

Domain concepts:
- **Temperature** values (targets and readings). We do not need arithmetic, only the ability to compare “current < target”. Therefore we model temperatures as an **atomic sort** `Temp` and introduce an uninterpreted strict-order predicate `lt : Temp × Temp`.
- **Thermostat** state. The system stores a target temperature and a current reading; the heater on/off state is determined by the rule “heater activates when current < target”. We model the evolving device state as an **atomic sort** `Thermostat`, with constructors that update parts of the state and observers that read the parts.

Sort table:
| Sort | Kind | Rationale |
|------|------|-----------|
| `Temp` | atomic | Opaque temperature values; only compared via `lt` |
| `Thermostat` | atomic | Device state; behavior given by constructors/observers axioms |

Design decision (tricky point): Since the observers `get_target` and `get_current` are total, we must specify their values on the initial constructor `new`. We therefore introduce constants `init_target, init_current : → Temp`.

---

## Step 2 — Classify functions and predicates

### Constructors of `Thermostat`
- `new : → Thermostat` — creates an initial thermostat.
- `set_target : Thermostat × Temp → Thermostat` — updates the target.
- `read_temp : Thermostat × Temp → Thermostat` — records a new current reading.

### Observers on `Thermostat`
- `get_target : Thermostat → Temp` — total.
- `get_current : Thermostat → Temp` — total.
- `heater_on : Thermostat` — predicate observer (total) representing the on/off state.

### Other symbols
- `init_target : → Temp`, `init_current : → Temp` — constants used to define initial readings.
- `lt : Temp × Temp` — predicate: strict less-than on temperatures, left **uninterpreted** (no axioms needed for this system requirement).

Role summary:
| Symbol | Role | Profile |
|--------|------|---------|
| `new` | constructor | `→ Thermostat` |
| `set_target` | constructor | `Thermostat × Temp → Thermostat` |
| `read_temp` | constructor | `Thermostat × Temp → Thermostat` |
| `get_target` | observer | `Thermostat → Temp` |
| `get_current` | observer | `Thermostat → Temp` |
| `heater_on` | observer (pred) | `Thermostat` |
| `init_target` | constant | `→ Temp` |
| `init_current` | constant | `→ Temp` |
| `lt` | helper predicate | `Temp × Temp` |

---

## Step 3 — Axiom obligation table (observer × constructor)

Constructors of `Thermostat`: `new`, `set_target(th, t)`, `read_temp(th, r)`.

All observers are total, so **every (observer, constructor) pair requires an axiom**.

### Obligation table
| Observer | Constructor | Axiom label | Axiom |
|----------|-------------|-------------|------|
| `get_target` | `new` | `get_target_new` | `get_target(new) = init_target` |
| `get_target` | `set_target(th, t)` | `get_target_set_target` | `get_target(set_target(th,t)) = t` |
| `get_target` | `read_temp(th, r)` | `get_target_read_temp` | `get_target(read_temp(th,r)) = get_target(th)` |
| `get_current` | `new` | `get_current_new` | `get_current(new) = init_current` |
| `get_current` | `set_target(th, t)` | `get_current_set_target` | `get_current(set_target(th,t)) = get_current(th)` |
| `get_current` | `read_temp(th, r)` | `get_current_read_temp` | `get_current(read_temp(th,r)) = r` |
| `heater_on` | `new` | `heater_on_new` | `heater_on(new) ⇔ lt(init_current, init_target)` |
| `heater_on` | `set_target(th, t)` | `heater_on_set_target` | `heater_on(set_target(th,t)) ⇔ lt(get_current(th), t)` |
| `heater_on` | `read_temp(th, r)` | `heater_on_read_temp` | `heater_on(read_temp(th,r)) ⇔ lt(r, get_target(th))` |

Notes / tricky points:
- We treat `heater_on` as a predicate observer, not as stored state with a separate setter. The “heater activates when current < target” requirement is enforced by the `heater_on_*` axioms.
- No partial functions are needed.

### Completeness count
- `get_target`: 3 constructor cases → 3 axioms.
- `get_current`: 3 constructor cases → 3 axioms.
- `heater_on`: 3 constructor cases → 3 axioms.

**Total axioms: 9.**

---

## Step 4/5 — Implement signature and axioms

Implementation follows the obligation table row-by-row with universal quantification over free variables.

"""

from alspec import (
    Axiom,
    GeneratedSortInfo,
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
    iff,
)


def thermostat_spec() -> Spec:
    # Variables
    th = var("th", "Thermostat")
    t = var("t", "Temp")
    r = var("r", "Temp")

    sig = Signature(
        sorts={
            "Temp": atomic("Temp"),
            "Thermostat": atomic("Thermostat"),
        },
        functions={
            # Constructors
            "new": fn("new", [], "Thermostat"),
            "set_target": fn(
                "set_target", [("th", "Thermostat"), ("t", "Temp")], "Thermostat"
            ),
            "read_temp": fn(
                "read_temp", [("th", "Thermostat"), ("r", "Temp")], "Thermostat"
            ),
            # Observers
            "get_target": fn("get_target", [("th", "Thermostat")], "Temp"),
            "get_current": fn("get_current", [("th", "Thermostat")], "Temp"),
            # Initial constants (needed because observers are total on `new`)
            "init_target": fn("init_target", [], "Temp"),
            "init_current": fn("init_current", [], "Temp"),
        },
        predicates={
            "lt": pred("lt", [("x", "Temp"), ("y", "Temp")]),
            "heater_on": pred("heater_on", [("th", "Thermostat")]),
        },
        generated_sorts={
            "Thermostat": GeneratedSortInfo(
                constructors=("new", "set_target", "read_temp"),
                selectors={
                    "set_target": {"get_target": "Temp"},
                    "read_temp": {"get_current": "Temp"},
                },
            )
        },
    )

    axioms = (
        # get_target observer
        Axiom(
            label="get_target_new",
            formula=eq(app("get_target", const("new")), const("init_target")),
        ),
        Axiom(
            label="get_target_set_target",
            formula=forall(
                [th, t],
                eq(
                    app("get_target", app("set_target", th, t)),
                    t,
                ),
            ),
        ),
        Axiom(
            label="get_target_read_temp",
            formula=forall(
                [th, r],
                eq(
                    app("get_target", app("read_temp", th, r)),
                    app("get_target", th),
                ),
            ),
        ),
        # get_current observer
        Axiom(
            label="get_current_new",
            formula=eq(app("get_current", const("new")), const("init_current")),
        ),
        Axiom(
            label="get_current_set_target",
            formula=forall(
                [th, t],
                eq(
                    app("get_current", app("set_target", th, t)),
                    app("get_current", th),
                ),
            ),
        ),
        Axiom(
            label="get_current_read_temp",
            formula=forall(
                [th, r],
                eq(
                    app("get_current", app("read_temp", th, r)),
                    r,
                ),
            ),
        ),
        # heater_on predicate (activation rule)
        Axiom(
            label="heater_on_new",
            formula=iff(
                PredApp("heater_on", (const("new"),)),
                PredApp("lt", (const("init_current"), const("init_target"))),
            ),
        ),
        Axiom(
            label="heater_on_set_target",
            formula=forall(
                [th, t],
                iff(
                    PredApp("heater_on", (app("set_target", th, t),)),
                    PredApp("lt", (app("get_current", th), t)),
                ),
            ),
        ),
        Axiom(
            label="heater_on_read_temp",
            formula=forall(
                [th, r],
                iff(
                    PredApp("heater_on", (app("read_temp", th, r),)),
                    PredApp("lt", (r, app("get_target", th))),
                ),
            ),
        ),
    )

    return Spec(name="Thermostat", signature=sig, axioms=axioms)
