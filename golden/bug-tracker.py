"""
# Worked Example: Bug Tracker with Ticket Store

This is the reference specification for the Bug Tracker domain. It demonstrates
the complete methodology: sort identification, function classification, obligation
table construction, and axiom writing. This file scores 1.00 health with 0 warnings.

## Step 1: Identify Sorts

- `TicketId`, `Title`, `Body`, `UserId` — Opaque identifiers with no internal
  structure we need to reason about. → **atomic**
- `SeverityLevel` — Atomic sort. `high` is a named constant for `is_critical`;
  other values exist but don't need naming. `classify` determines severity.
- `Status` — Finite enumeration: `open`, `resolved`. Modeled as an atomic sort
  with nullary constructors (not a CoproductSort — no carried data).
- `Store` — The central domain object. A **collection** of tickets indexed by
  `TicketId`, following the FiniteMap pattern. Individual tickets are NOT a
  separate sort — all properties are accessed through store observers with a key.

  *Why not have a `Ticket` sort?* Because the FiniteMap pattern is the standard
  algebraic approach for collections. The Store is indexed by TicketId and all
  observations go through the Store. A separate Ticket sort would require
  modeling insertion/lookup separately, adding complexity without benefit.

## Step 2: Classify Functions and Predicates

**Constructors** build values of a sort. **Observers** query or decompose them.
Every observer owes axioms against every constructor of its primary sort.

### Store Constructors
- `empty : → Store` — Empty store, no tickets.
- `create_ticket : Store × TicketId × Title × Body → Store` — Adds a ticket. Total.
- `resolve_ticket : Store × TicketId → Store` — Transitions status. Total (no-op
  on nonexistent ticket).
- `assign_ticket : Store × TicketId × UserId → Store` — Sets assignee. Total
  (no-op on nonexistent ticket).

### Constants
- `open : → Status`, `resolved : → Status` — Enumeration values.
- `high : → SeverityLevel` — Needed for `is_critical` definition.

### Uninterpreted Function
- `classify : Title × Body → SeverityLevel` — Not defined by axioms. Appears
  only inside other axioms (e.g., `get_severity = classify(t, b)`). At
  implementation time, could be an LLM call, rules engine, or lookup table.

### Observers (partial — undefined if ticket doesn't exist)
- `get_status : Store × TicketId →? Status`
- `get_severity : Store × TicketId →? SeverityLevel`
- `get_assignee : Store × TicketId →? UserId` — **Doubly partial**: undefined if
  ticket doesn't exist AND if ticket exists but has no assignee yet.

### Predicates
- `eq_id : TicketId × TicketId` — Key equality for dispatch. A PREDICATE, not a
  function returning Bool — use `PredApp("eq_id", ...)` everywhere.
- `has_ticket : Store × TicketId` — True iff ticket exists. Total over store.
- `is_critical : Store × TicketId` — True iff ticket exists and severity is high.

## Step 3: Axiom Obligation Table

Store constructors: `empty`, `create_ticket`, `resolve_ticket`, `assign_ticket`.
Every observer takes a `TicketId` key, and constructors also take keys, so each
(observer, constructor) pair splits into **hit** (keys match) and **miss** (keys
differ) via `eq_id`.

**`eq_id` basis (3 axioms):** Reflexivity, symmetry, transitivity.

**`has_ticket` — total predicate (5 axioms):**
- × `empty`: false.
- × `create_ticket`: hit (true), miss (delegates).
- × `resolve_ticket`: universal preservation — both hit and miss produce identical
  biconditionals, so collapse to one axiom covering all keys.
- × `assign_ticket`: same — one universal axiom.

**`get_status` — partial (6 axioms):**
- × `create_ticket`: hit (`open`), miss (delegates).
- × `resolve_ticket`: hit+has_ticket (`resolved`), hit+¬has_ticket (delegates),
  miss (delegates). Both guard polarities required.
- × `assign_ticket`: universal preservation (one axiom, no key dispatch).

**`get_severity` — partial (4 axioms):**
- × `create_ticket`: hit (`classify(t, b)`), miss (delegates).
- × `resolve_ticket`: universal preservation — resolve doesn't change severity for
  ANY ticket regardless of key. One axiom covers all keys.
- × `assign_ticket`: same.

**`get_assignee` — doubly partial (6 axioms):**
- × `create_ticket` hit: **explicit undefinedness** via `Negation(Definedness(...))`.
  New tickets have no assignee. Under loose semantics, omitting this would NOT make
  `get_assignee` undefined — it would leave it unconstrained (any user is valid in
  some model). The `¬def(...)` axiom is required.
- × `create_ticket` miss: delegates.
- × `assign_ticket`: hit+has_ticket (returns new UserId), hit+¬has_ticket
  (delegates — assigning nonexistent ticket is no-op), miss (delegates).
- × `resolve_ticket`: universal preservation.

**`is_critical` — predicate (5 axioms):**
- × `empty`: false.
- × `create_ticket`: hit (⟺ `classify(t, b) = high`), miss (delegates).
- × `resolve_ticket`, `assign_ticket`: universal preservation.

**Total: 29 axioms.**

## Key Patterns Demonstrated

- **Hit/miss key dispatch**: `Implication(PredApp("eq_id", ...), ...)` vs
  `Implication(Negation(PredApp("eq_id", ...)), ...)`
- **Universal preservation**: When a constructor doesn't affect an observer at ANY
  key, collapse hit/miss into one unguarded equation.
- **Explicit undefinedness**: `Negation(Definedness(...))` — required under loose
  semantics. Omission leaves values unconstrained, not undefined.
- **Both guard polarities**: When guarded by `has_ticket`, write axioms for both
  positive and negative cases.
- **Nested Implication**: Key dispatch guard wrapping a `has_ticket` guard.
- **Conjunction in antecedent**: `eq_id_trans` uses `Conjunction((PredApp, PredApp))`.
- **iff(PredApp, Equation)**: `is_critical_create_hit` — critical iff severity = high.
- **Uninterpreted function**: `classify` appears in axioms but not defined by them.
"""

from alspec import (
    Axiom, Conjunction, Definedness, Implication, Negation, PredApp,
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
            label="get_status_resolve_hit_noticket",
            formula=forall([s, k, k2], Implication(
                PredApp("eq_id", (k, k2)),
                Implication(
                    Negation(PredApp("has_ticket", (s, k))),
                    eq(app("get_status", app("resolve_ticket", s, k), k2), app("get_status", s, k2))
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
            label="get_assignee_create_hit",
            formula=forall([s, k, k2, t, b], Implication(
                PredApp("eq_id", (k, k2)),
                Negation(Definedness(app("get_assignee", app("create_ticket", s, k, t, b), k2)))
            ))
        ),
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
            label="get_assignee_assign_hit_noticket",
            formula=forall([s, k, k2, u], Implication(
                PredApp("eq_id", (k, k2)),
                Implication(
                    Negation(PredApp("has_ticket", (s, k))),
                    eq(app("get_assignee", app("assign_ticket", s, k, u), k2), app("get_assignee", s, k2))
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
