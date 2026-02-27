"""
# Domain Analysis: Door Lock System

## 1. Sort Classification
*   **`Lock`**: The central domain object. **atomic** — opaque machine transitioned by constructors.
*   **`State`**: The logical status of the lock. **atomic** — modeled as an enumeration with three nullary constants (`locked`, `unlocked`, `open_state`).
*   **`Code`**: The security credential. **atomic** — opaque identifier used for validation.

## 2. Function and Predicate Roles
**Enumeration Constants:**
*   `locked : → State`
*   `unlocked : → State`
*   `open_state : → State`

**Constructors for `Lock`**:
*   `new : Code → Lock` (Sets initial tracking code, default state `locked`)
*   `lock : Lock × Code → Lock` (Transitions from `unlocked` to `locked` given correct code)
*   `unlock : Lock × Code → Lock` (Transitions from `locked` to `unlocked` given correct code)
*   `open_door : Lock → Lock` (Transitions from `unlocked` to `open_state`)
*   `close_door : Lock → Lock` (Transitions from `open_state` to `unlocked`)

**Observers on `Lock`**:
*   `get_state : Lock → State` (Total observer for the lock's state)
*   `get_code : Lock → Code` (Total observer for the lock's stored validation code)

**Predicates**:
*   `eq_code : Code × Code` (Key quality to determine code match)

## 3. Tricky Cases and Design Decisions
1.  **State Machine Model**: The lock acts as an immutable state machine where every action yields a "new" lock state.
2.  **Missing "Close" Semantic**: The prompt notes transitions "locked, unlocked, open" and conditions to open (`unlocked`), but does not describe closing the door. If left strictly to the prompt, a door in `open_state` could never be reset. Therefore, I added a `close_door` constructor transitioning `open_state` back to `unlocked` to make the system behavior fully reachable and realistic.
3.  **Code Retention**: To make "Lock/unlock requires a code" work systemically, the `Lock` itself captures the `Code` during the `new` step. When performing a `lock` or `unlock` action, the provided code is checked against the internal `get_code(l)` via `eq_code`.
4.  **Graceful Failures (Misses)**: All invalid transitions (wrong state OR wrong code) simply preserve the current state (a "no-op" in a state machine paradigm). This is captured using standard `Hit/Miss` paired axioms.

## 4. Axiom Obligation Table

| Observer | Constructor | Case | Behavior / Condition |
|----------|------------|------|----------------------|
| `eq_code` (basis) | — | — | Reflexivity, Symmetry, Transitivity (3 axioms) |
| `get_code` | `new` | — | Returns `c`. |
| `get_code` | `lock` | — | Preserves `get_code(l)`. |
| `get_code` | `unlock` | — | Preserves `get_code(l)`. |
| `get_code` | `open_door`| — | Preserves `get_code(l)`. |
| `get_code` | `close_door`| — | Preserves `get_code(l)`. |
| `get_state`| `new` | — | Returns `locked`. |
| `get_state`| `lock` | Hit | `eq_code` \(\wedge\) `get_state = unlocked` \(\implies locked\) |
| `get_state`| `lock` | Miss | \(\neg\) (Hit condition) \(\implies\) state preserved. |
| `get_state`| `unlock` | Hit | `eq_code` \(\wedge\) `get_state = locked` \(\implies unlocked\) |
| `get_state`| `unlock` | Miss | \(\neg\) (Hit condition) \(\implies\) state preserved. |
| `get_state`| `open_door`| Hit | `get_state = unlocked` \(\implies open\_state\) |
| `get_state`| `open_door`| Miss | \(\neg\) (Hit condition) \(\implies\) state preserved. |
| `get_state`| `close_door`| Hit | `get_state = open_state` \(\implies unlocked\) |
| `get_state`| `close_door`| Miss | \(\neg\) (Hit condition) \(\implies\) state preserved. |

**Completeness Count**:
- `eq_code` structural norms: 3
- `get_code` axioms: 5 (1 creation + 4 universal preservation)
- `get_state` axioms: 9 (1 creation + 4 pairs of Hit/Miss)
- **Total: 17 axioms**
"""

from alspec import (
    Axiom, Conjunction, Implication, Negation, PredApp,
    Signature, Spec, atomic, fn, pred, var, app, const, eq, forall
)

def door_lock_spec() -> Spec:
    # Variables
    c = var("c", "Code")
    l = var("l", "Lock")
    c1 = var("c1", "Code")
    c2 = var("c2", "Code")
    c3 = var("c3", "Code")

    sig = Signature(
        sorts={
            "Code": atomic("Code"),
            "State": atomic("State"),
            "Lock": atomic("Lock"),
        },
        functions={
            # Enumeration Constants for State
            "locked": fn("locked", [], "State"),
            "unlocked": fn("unlocked", [], "State"),
            "open_state": fn("open_state", [], "State"),
            
            # Constructors for Lock
            "new": fn("new", [("c", "Code")], "Lock"),
            "lock": fn("lock", [("l", "Lock"), ("c", "Code")], "Lock"),
            "unlock": fn("unlock", [("l", "Lock"), ("c", "Code")], "Lock"),
            "open_door": fn("open_door", [("l", "Lock")], "Lock"),
            "close_door": fn("close_door", [("l", "Lock")], "Lock"),
            
            # Observers for Lock
            "get_state": fn("get_state", [("l", "Lock")], "State"),
            "get_code": fn("get_code", [("l", "Lock")], "Code"),
        },
        predicates={
            "eq_code": pred("eq_code", [("c1", "Code"), ("c2", "Code")]),
        }
    )

    axioms = (
        # ━━ eq_code basis ━━
        Axiom(
            label="eq_code_refl",
            formula=forall([c1], PredApp("eq_code", (c1, c1))),
        ),
        Axiom(
            label="eq_code_sym",
            formula=forall([c1, c2], Implication(
                PredApp("eq_code", (c1, c2)),
                PredApp("eq_code", (c2, c1)),
            )),
        ),
        Axiom(
            label="eq_code_trans",
            formula=forall([c1, c2, c3], Implication(
                Conjunction((
                    PredApp("eq_code", (c1, c2)),
                    PredApp("eq_code", (c2, c3)),
                )),
                PredApp("eq_code", (c1, c3)),
            )),
        ),

        # ━━ get_code (Total observer) ━━
        Axiom(
            label="get_code_new",
            formula=forall([c], eq(
                app("get_code", app("new", c)),
                c
            )),
        ),
        Axiom(
            label="get_code_lock",
            formula=forall([l, c], eq(
                app("get_code", app("lock", l, c)),
                app("get_code", l)
            )),
        ),
        Axiom(
            label="get_code_unlock",
            formula=forall([l, c], eq(
                app("get_code", app("unlock", l, c)),
                app("get_code", l)
            )),
        ),
        Axiom(
            label="get_code_open_door",
            formula=forall([l], eq(
                app("get_code", app("open_door", l)),
                app("get_code", l)
            )),
        ),
        Axiom(
            label="get_code_close_door",
            formula=forall([l], eq(
                app("get_code", app("close_door", l)),
                app("get_code", l)
            )),
        ),

        # ━━ get_state (Total observer) ━━
        Axiom(
            label="get_state_new",
            formula=forall([c], eq(
                app("get_state", app("new", c)),
                const("locked")
            )),
        ),

        # lock transitions
        Axiom(
            label="get_state_lock_hit",
            formula=forall([l, c], Implication(
                Conjunction((
                    PredApp("eq_code", (c, app("get_code", l))),
                    eq(app("get_state", l), const("unlocked")),
                )),
                eq(app("get_state", app("lock", l, c)), const("locked")),
            )),
        ),
        Axiom(
            label="get_state_lock_miss",
            formula=forall([l, c], Implication(
                Negation(Conjunction((
                    PredApp("eq_code", (c, app("get_code", l))),
                    eq(app("get_state", l), const("unlocked")),
                ))),
                eq(app("get_state", app("lock", l, c)), app("get_state", l)),
            )),
        ),

        # unlock transitions
        Axiom(
            label="get_state_unlock_hit",
            formula=forall([l, c], Implication(
                Conjunction((
                    PredApp("eq_code", (c, app("get_code", l))),
                    eq(app("get_state", l), const("locked")),
                )),
                eq(app("get_state", app("unlock", l, c)), const("unlocked")),
            )),
        ),
        Axiom(
            label="get_state_unlock_miss",
            formula=forall([l, c], Implication(
                Negation(Conjunction((
                    PredApp("eq_code", (c, app("get_code", l))),
                    eq(app("get_state", l), const("locked")),
                ))),
                eq(app("get_state", app("unlock", l, c)), app("get_state", l)),
            )),
        ),

        # open_door transitions
        Axiom(
            label="get_state_open_door_hit",
            formula=forall([l], Implication(
                eq(app("get_state", l), const("unlocked")),
                eq(app("get_state", app("open_door", l)), const("open_state")),
            )),
        ),
        Axiom(
            label="get_state_open_door_miss",
            formula=forall([l], Implication(
                Negation(eq(app("get_state", l), const("unlocked"))),
                eq(app("get_state", app("open_door", l)), app("get_state", l)),
            )),
        ),

        # close_door transitions
        Axiom(
            label="get_state_close_door_hit",
            formula=forall([l], Implication(
                eq(app("get_state", l), const("open_state")),
                eq(app("get_state", app("close_door", l)), const("unlocked")),
            )),
        ),
        Axiom(
            label="get_state_close_door_miss",
            formula=forall([l], Implication(
                Negation(eq(app("get_state", l), const("open_state"))),
                eq(app("get_state", app("close_door", l)), app("get_state", l)),
            )),
        ),
    )

    return Spec(name="DoorLock", signature=sig, axioms=axioms)