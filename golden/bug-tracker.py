"""
# Analysis: Bug Tracker Algebraic Specification

## Step 1: Identify Sorts
The system describes a "Ticket Store" collection object that manages bug tracker tickets.
- `TicketId`, `Title`, `Body`, `UserId`: Opaque atomic identifiers.
- `SeverityLevel`: Atomic sort (with an uninterpreted constant `high`).
- `Status`: Atomic sort representing a finite enumeration (with constants `open` and `resolved`).
- `Store`: Atomic sort representing the core state of the collection (FiniteMap pattern).

## Step 2: Classify Functions and Predicates
### Constructors (building Store values)
- `empty : → Store`
- `create_ticket : Store × TicketId × Title × Body → Store`
- `resolve_ticket : Store × TicketId → Store`
- `assign_ticket : Store × TicketId × UserId → Store`

### Constants (nullary functions)
- `open : → Status`
- `resolved : → Status`
- `high : → SeverityLevel`

### Uninterpreted Function
- `classify : Title × Body → SeverityLevel`: External determination of severity used within axioms.

### Observers (partial operations on Tickets)
- `get_status : Store × TicketId →? Status`
- `get_severity : Store × TicketId →? SeverityLevel`
- `get_assignee : Store × TicketId →? UserId` (Doubly partial: needs both ticket existence and assignee assignment).

### Predicates
- `eq_id : TicketId × TicketId` (equality observer for keys).
- `has_ticket : Store × TicketId` (ticket existence query).
- `is_critical : Store × TicketId` (query combining ticket existence and high severity).

## Step 3: Axiom Obligation Table & Check
Using key-dispatch (`eq_id(k, k2)`) across observers and Store constructors:

1. **`eq_id`** (basis)
   - Reflexivity, symmetry, transitivity (3 axioms).
2. **`has_ticket`** (total predicate)
   - `empty`: false.
   - `create_ticket`: hit (true), miss (delegates).
   - `resolve_ticket`, `assign_ticket`: Both universally preserve ticket existence across all keys.
   - (5 axioms total).
3. **`get_status`** (partial)
   - `empty`: omitted (undefined).
   - `create_ticket`: hit (`open`), miss (delegates).
   - `resolve_ticket`: hit (`resolved` guarded by `has_ticket`), miss (delegates).
   - `assign_ticket`: universal preservation (assigning doesn't change status).
   - (5 axioms total).
4. **`get_severity`** (partial)
   - `empty`: omitted.
   - `create_ticket`: hit (`classify`), miss (delegates).
   - `resolve_ticket`, `assign_ticket`: Both universally preserve severity across all keys.
   - (4 axioms total).
5. **`get_assignee`** (doubly partial)
   - `empty`: omitted.
   - `create_ticket`: hit (omitted, no assignee initially), miss (delegates).
   - `assign_ticket`: hit (assigned user `u`, guarded by `has_ticket`), miss (delegates).
   - `resolve_ticket`: universally preserves assignee.
   - (4 axioms total).
6. **`is_critical`** (predicate)
   - `empty`: false.
   - `create_ticket`: hit (iff `classify = high`), miss (delegates).
   - `resolve_ticket`, `assign_ticket`: universally preserved.
   - (5 axioms total).

**Completeness Count:** Expected 26 total axioms covering key dispatch scenarios and universal preservation shortcuts.

## Design Decisions & Tricky Cases
- **Key Dispatching:** For FiniteMap-like specs, observer updates branch on key equality (`eq_id`). A match guarantees the value interacts with the current constructor. 
- **Partial Function Bounds:** Omitted axioms specifically document when function observation is undefined, such as querying empty stores, or querying `get_assignee` immediately on `create_ticket`.
- **Double Guards:** Certain updates like `get_assignee` hitting on `assign_ticket` require nesting `PredApp("has_ticket", ...)` inside the hit branch `Implication`. This ensures missing items are handled robustly (assigning nonexistent tickets is a no-op).
"""

from alspec import (
    Axiom, Conjunction, Implication, Negation, PredApp,
    Signature, Spec,
    atomic, fn, pred, var, app, const, eq, forall, iff,
)

def bug_tracker_spec() -> Spec:
    s = var("s", "Store")
    k = var("k", "TicketId")
    k2 = var("k2", "TicketId")
    k3 = var("k3", "TicketId")
    t = var("t", "Title")
    b = var("b", "Body")
    u = var("u", "UserId")

    sig = Signature(
        sorts={
            "TicketId": atomic("TicketId"),
            "Title": atomic("Title"),
            "Body": atomic("Body"),
            "SeverityLevel": atomic("SeverityLevel"),
            "Status": atomic("Status"),
            "UserId": atomic("UserId"),
            "Store": atomic("Store"),
        },
        functions={
            "empty": fn("empty", [], "Store"),
            "create_ticket": fn("create_ticket", [("s", "Store"), ("k", "TicketId"), ("t", "Title"), ("b", "Body")], "Store"),
            "resolve_ticket": fn("resolve_ticket", [("s", "Store"), ("k", "TicketId")], "Store"),
            "assign_ticket": fn("assign_ticket", [("s", "Store"), ("k", "TicketId"), ("u", "UserId")], "Store"),
            
            "classify": fn("classify", [("t", "Title"), ("b", "Body")], "SeverityLevel"),
            
            "get_status": fn("get_status", [("s", "Store"), ("k", "TicketId")], "Status", total=False),
            "get_severity": fn("get_severity", [("s", "Store"), ("k", "TicketId")], "SeverityLevel", total=False),
            "get_assignee": fn("get_assignee", [("s", "Store"), ("k", "TicketId")], "UserId", total=False),
            
            "open": fn("open", [], "Status"),
            "resolved": fn("resolved", [], "Status"),
            "high": fn("high", [], "SeverityLevel"),
        },
        predicates={
            "eq_id": pred("eq_id", [("k1", "TicketId"), ("k2", "TicketId")]),
            "has_ticket": pred("has_ticket", [("s", "Store"), ("k", "TicketId")]),
            "is_critical": pred("is_critical", [("s", "Store"), ("k", "TicketId")]),
        }
    )

    axioms = (
        # eq_id basis
        Axiom(
            label="eq_id_refl",
            formula=forall([k], PredApp("eq_id", (k, k)))
        ),
        Axiom(
            label="eq_id_sym",
            formula=forall([k, k2], Implication(
                PredApp("eq_id", (k, k2)),
                PredApp("eq_id", (k2, k))
            ))
        ),
        Axiom(
            label="eq_id_trans",
            formula=forall([k, k2, k3], Implication(
                Conjunction((
                    PredApp("eq_id", (k, k2)),
                    PredApp("eq_id", (k2, k3)),
                )),
                PredApp("eq_id", (k, k3))
            ))
        ),

        # has_ticket
        Axiom(
            label="has_ticket_empty",
            formula=forall([k], Negation(PredApp("has_ticket", (const("empty"), k))))
        ),
        Axiom(
            label="has_ticket_create_hit",
            formula=forall([s, k, k2, t, b], Implication(
                PredApp("eq_id", (k, k2)),
                PredApp("has_ticket", (app("create_ticket", s, k, t, b), k2))
            ))
        ),
        Axiom(
            label="has_ticket_create_miss",
            formula=forall([s, k, k2, t, b], Implication(
                Negation(PredApp("eq_id", (k, k2))),
                iff(
                    PredApp("has_ticket", (app("create_ticket", s, k, t, b), k2)),
                    PredApp("has_ticket", (s, k2))
                )
            ))
        ),
        Axiom(
            label="has_ticket_resolve",
            formula=forall([s, k, k2], iff(
                PredApp("has_ticket", (app("resolve_ticket", s, k), k2)),
                PredApp("has_ticket", (s, k2))
            ))
        ),
        Axiom(
            label="has_ticket_assign",
            formula=forall([s, k, k2, u], iff(
                PredApp("has_ticket", (app("assign_ticket", s, k, u), k2)),
                PredApp("has_ticket", (s, k2))
            ))
        ),

        # get_status
        Axiom(
            label="get_status_create_hit",
            formula=forall([s, k, k2, t, b], Implication(
                PredApp("eq_id", (k, k2)),
                eq(app("get_status", app("create_ticket", s, k, t, b), k2), const("open"))
            ))
        ),
        Axiom(
            label="get_status_create_miss",
            formula=forall([s, k, k2, t, b], Implication(
                Negation(PredApp("eq_id", (k, k2))),
                eq(app("get_status", app("create_ticket", s, k, t, b), k2), app("get_status", s, k2))
            ))
        ),
        Axiom(
            label="get_status_resolve_hit",
            formula=forall([s, k, k2], Implication(
                PredApp("eq_id", (k, k2)),
                Implication(
                    PredApp("has_ticket", (s, k)),
                    eq(app("get_status", app("resolve_ticket", s, k), k2), const("resolved"))
                )
            ))
        ),
        Axiom(
            label="get_status_resolve_miss",
            formula=forall([s, k, k2], Implication(
                Negation(PredApp("eq_id", (k, k2))),
                eq(app("get_status", app("resolve_ticket", s, k), k2), app("get_status", s, k2))
            ))
        ),
        Axiom(
            label="get_status_assign",
            formula=forall([s, k, k2, u], eq(
                app("get_status", app("assign_ticket", s, k, u), k2),
                app("get_status", s, k2)
            ))
        ),

        # get_severity
        Axiom(
            label="get_severity_create_hit",
            formula=forall([s, k, k2, t, b], Implication(
                PredApp("eq_id", (k, k2)),
                eq(app("get_severity", app("create_ticket", s, k, t, b), k2), app("classify", t, b))
            ))
        ),
        Axiom(
            label="get_severity_create_miss",
            formula=forall([s, k, k2, t, b], Implication(
                Negation(PredApp("eq_id", (k, k2))),
                eq(app("get_severity", app("create_ticket", s, k, t, b), k2), app("get_severity", s, k2))
            ))
        ),
        Axiom(
            label="get_severity_resolve",
            formula=forall([s, k, k2], eq(
                app("get_severity", app("resolve_ticket", s, k), k2),
                app("get_severity", s, k2)
            ))
        ),
        Axiom(
            label="get_severity_assign",
            formula=forall([s, k, k2, u], eq(
                app("get_severity", app("assign_ticket", s, k, u), k2),
                app("get_severity", s, k2)
            ))
        ),

        # get_assignee
        Axiom(
            label="get_assignee_create_miss",
            formula=forall([s, k, k2, t, b], Implication(
                Negation(PredApp("eq_id", (k, k2))),
                eq(app("get_assignee", app("create_ticket", s, k, t, b), k2), app("get_assignee", s, k2))
            ))
        ),
        Axiom(
            label="get_assignee_assign_hit",
            formula=forall([s, k, k2, u], Implication(
                PredApp("eq_id", (k, k2)),
                Implication(
                    PredApp("has_ticket", (s, k)),
                    eq(app("get_assignee", app("assign_ticket", s, k, u), k2), u)
                )
            ))
        ),
        Axiom(
            label="get_assignee_assign_miss",
            formula=forall([s, k, k2, u], Implication(
                Negation(PredApp("eq_id", (k, k2))),
                eq(app("get_assignee", app("assign_ticket", s, k, u), k2), app("get_assignee", s, k2))
            ))
        ),
        Axiom(
            label="get_assignee_resolve",
            formula=forall([s, k, k2], eq(
                app("get_assignee", app("resolve_ticket", s, k), k2),
                app("get_assignee", s, k2)
            ))
        ),

        # is_critical
        Axiom(
            label="is_critical_empty",
            formula=forall([k], Negation(PredApp("is_critical", (const("empty"), k))))
        ),
        Axiom(
            label="is_critical_create_hit",
            formula=forall([s, k, k2, t, b], Implication(
                PredApp("eq_id", (k, k2)),
                iff(
                    PredApp("is_critical", (app("create_ticket", s, k, t, b), k2)),
                    eq(app("classify", t, b), const("high"))
                )
            ))
        ),
        Axiom(
            label="is_critical_create_miss",
            formula=forall([s, k, k2, t, b], Implication(
                Negation(PredApp("eq_id", (k, k2))),
                iff(
                    PredApp("is_critical", (app("create_ticket", s, k, t, b), k2)),
                    PredApp("is_critical", (s, k2))
                )
            ))
        ),
        Axiom(
            label="is_critical_resolve",
            formula=forall([s, k, k2], iff(
                PredApp("is_critical", (app("resolve_ticket", s, k), k2)),
                PredApp("is_critical", (s, k2))
            ))
        ),
        Axiom(
            label="is_critical_assign",
            formula=forall([s, k, k2, u], iff(
                PredApp("is_critical", (app("assign_ticket", s, k, u), k2)),
                PredApp("is_critical", (s, k2))
            ))
        ),
    )

    return Spec(name="BugTracker", signature=sig, axioms=axioms)