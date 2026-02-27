"""
### Step 1: Identify Sorts
- **`MsgId`** (atomic): Opaque identifier for messages, acting as the key.
- **`Inbox`** (atomic): The main domain object, acting as a finite map/collection of messages.
- **`Nat`** (atomic): For tracking the unread count.

### Step 2: Classify Functions & Predicates
**Inbox Constructors:**
- `empty : → Inbox`
- `receive : Inbox × MsgId → Inbox`
- `mark_read : Inbox × MsgId → Inbox`
- `mark_unread : Inbox × MsgId → Inbox`
- `delete : Inbox × MsgId → Inbox`
- `star : Inbox × MsgId → Inbox`

**Nat Helpers:**
- `zero : → Nat`, `suc : Nat → Nat`, `pred : Nat → Nat`

**Observers/Predicates:**
- `has_msg : Inbox × MsgId` (predicate) - checks if a message exists.
- `is_read : Inbox × MsgId` (predicate) - true if a message exists AND is read.
- `is_starred : Inbox × MsgId` (predicate) - true if a message exists AND is starred.
- `unread_count : Inbox → Nat` (total function) - tracks total unread.
- `eq_id : MsgId × MsgId` (predicate) - equality test for dispatch.

### Step 3: Axiom Obligation Table

**Tricky Design Decisions:**
1. Operations on missing items are generally preserved/no-ops to avoid inserting zombie records (e.g. marking a missing message read preserves its non-existence, returning false).
2. Because `unread_count` doesn't take a key argument, we can't use hit/miss dispatch. Instead, its axioms branch via logical conjunctions based on the system state *before* the constructor applies (e.g. "does this operation change the unread count, or preserve it?"). Let's call them _change_ and _preserve_.

**Completeness Count (42 axioms):**
- **Basis (5)**: `eq_id` properties (refl, sym, trans) and `pred` properties (zero, suc).
- **`has_msg` (8)**: empty(1), receive(2 keys), delete(2 keys), universal preservation for mark_read/mark_unread/star (3).
- **`is_read` (10)**: empty(1), receive(2 keys), mark_read(2 keys), mark_unread(2 keys), delete(2 keys), universal preservation for star (1).
- **`is_starred` (9)**: empty(1), receive(2 keys), star(2 keys), delete(2 keys), universal preservation for mark_read/mark_unread (2).
- **`unread_count` (10)**: empty(1), state-dispatch for receive(2 states), mark_read(2 states), mark_unread(2 states), delete(2 states), universal preservation for star(1).
"""

from alspec import (
    Axiom, Conjunction, Disjunction, Implication, Negation, PredApp,
    Signature, Spec,
    atomic, fn, pred, var, app, const, eq, forall, iff,
)

def email_inbox_spec() -> Spec:
    # Variables
    i = var("i", "Inbox")
    m = var("m", "MsgId")
    m2 = var("m2", "MsgId")
    m3 = var("m3", "MsgId")
    n = var("n", "Nat")

    sig = Signature(
        sorts={
            "Inbox": atomic("Inbox"),
            "MsgId": atomic("MsgId"),
            "Nat": atomic("Nat"),
        },
        functions={
            # Inbox constructors
            "empty": fn("empty", [], "Inbox"),
            "receive": fn("receive", [("i", "Inbox"), ("m", "MsgId")], "Inbox"),
            "mark_read": fn("mark_read", [("i", "Inbox"), ("m", "MsgId")], "Inbox"),
            "mark_unread": fn("mark_unread", [("i", "Inbox"), ("m", "MsgId")], "Inbox"),
            "delete": fn("delete", [("i", "Inbox"), ("m", "MsgId")], "Inbox"),
            "star": fn("star", [("i", "Inbox"), ("m", "MsgId")], "Inbox"),

            # Nat
            "zero": fn("zero", [], "Nat"),
            "suc": fn("suc", [("n", "Nat")], "Nat"),
            "pred": fn("pred", [("n", "Nat")], "Nat"),

            # Observer
            "unread_count": fn("unread_count", [("i", "Inbox")], "Nat"),
        },
        predicates={
            "eq_id": pred("eq_id", [("m1", "MsgId"), ("m2", "MsgId")]),
            "has_msg": pred("has_msg", [("i", "Inbox"), ("m", "MsgId")]),
            "is_read": pred("is_read", [("i", "Inbox"), ("m", "MsgId")]),
            "is_starred": pred("is_starred", [("i", "Inbox"), ("m", "MsgId")]),
        }
    )

    axioms = (
        # ━━ Basis: eq_id and pred ━━
        Axiom(label="eq_id_refl", formula=forall([m], PredApp("eq_id", (m, m)))),
        Axiom(label="eq_id_sym", formula=forall([m, m2], Implication(PredApp("eq_id", (m, m2)), PredApp("eq_id", (m2, m))))),
        Axiom(label="eq_id_trans", formula=forall([m, m2, m3], Implication(
            Conjunction((PredApp("eq_id", (m, m2)), PredApp("eq_id", (m2, m3)))),
            PredApp("eq_id", (m, m3))
        ))),
        Axiom(label="pred_zero", formula=eq(app("pred", const("zero")), const("zero"))),
        Axiom(label="pred_suc", formula=forall([n], eq(app("pred", app("suc", n)), n))),

        # ━━ has_msg ━━
        Axiom(label="has_msg_empty", formula=forall([m], Negation(PredApp("has_msg", (const("empty"), m))))),
        
        Axiom(label="has_msg_receive_hit", formula=forall([i, m, m2], Implication(
            PredApp("eq_id", (m, m2)),
            PredApp("has_msg", (app("receive", i, m), m2))
        ))),
        Axiom(label="has_msg_receive_miss", formula=forall([i, m, m2], Implication(
            Negation(PredApp("eq_id", (m, m2))),
            iff(PredApp("has_msg", (app("receive", i, m), m2)), PredApp("has_msg", (i, m2)))
        ))),
        
        Axiom(label="has_msg_mark_read", formula=forall([i, m, m2], iff(
            PredApp("has_msg", (app("mark_read", i, m), m2)), PredApp("has_msg", (i, m2))
        ))),
        Axiom(label="has_msg_mark_unread", formula=forall([i, m, m2], iff(
            PredApp("has_msg", (app("mark_unread", i, m), m2)), PredApp("has_msg", (i, m2))
        ))),
        
        Axiom(label="has_msg_delete_hit", formula=forall([i, m, m2], Implication(
            PredApp("eq_id", (m, m2)),
            Negation(PredApp("has_msg", (app("delete", i, m), m2)))
        ))),
        Axiom(label="has_msg_delete_miss", formula=forall([i, m, m2], Implication(
            Negation(PredApp("eq_id", (m, m2))),
            iff(PredApp("has_msg", (app("delete", i, m), m2)), PredApp("has_msg", (i, m2)))
        ))),
        
        Axiom(label="has_msg_star", formula=forall([i, m, m2], iff(
            PredApp("has_msg", (app("star", i, m), m2)), PredApp("has_msg", (i, m2))
        ))),

        # ━━ is_read ━━
        Axiom(label="is_read_empty", formula=forall([m], Negation(PredApp("is_read", (const("empty"), m))))),
        
        Axiom(label="is_read_receive_hit", formula=forall([i, m, m2], Implication(
            PredApp("eq_id", (m, m2)),
            iff(
                PredApp("is_read", (app("receive", i, m), m2)),
                Conjunction((PredApp("has_msg", (i, m2)), PredApp("is_read", (i, m2))))
            )
        ))),
        Axiom(label="is_read_receive_miss", formula=forall([i, m, m2], Implication(
            Negation(PredApp("eq_id", (m, m2))),
            iff(PredApp("is_read", (app("receive", i, m), m2)), PredApp("is_read", (i, m2)))
        ))),

        Axiom(label="is_read_mark_read_hit", formula=forall([i, m, m2], Implication(
            PredApp("eq_id", (m, m2)),
            iff(PredApp("is_read", (app("mark_read", i, m), m2)), PredApp("has_msg", (i, m2)))
        ))),
        Axiom(label="is_read_mark_read_miss", formula=forall([i, m, m2], Implication(
            Negation(PredApp("eq_id", (m, m2))),
            iff(PredApp("is_read", (app("mark_read", i, m), m2)), PredApp("is_read", (i, m2)))
        ))),

        Axiom(label="is_read_mark_unread_hit", formula=forall([i, m, m2], Implication(
            PredApp("eq_id", (m, m2)),
            Negation(PredApp("is_read", (app("mark_unread", i, m), m2)))
        ))),
        Axiom(label="is_read_mark_unread_miss", formula=forall([i, m, m2], Implication(
            Negation(PredApp("eq_id", (m, m2))),
            iff(PredApp("is_read", (app("mark_unread", i, m), m2)), PredApp("is_read", (i, m2)))
        ))),

        Axiom(label="is_read_delete_hit", formula=forall([i, m, m2], Implication(
            PredApp("eq_id", (m, m2)),
            Negation(PredApp("is_read", (app("delete", i, m), m2)))
        ))),
        Axiom(label="is_read_delete_miss", formula=forall([i, m, m2], Implication(
            Negation(PredApp("eq_id", (m, m2))),
            iff(PredApp("is_read", (app("delete", i, m), m2)), PredApp("is_read", (i, m2)))
        ))),

        Axiom(label="is_read_star", formula=forall([i, m, m2], iff(
            PredApp("is_read", (app("star", i, m), m2)), PredApp("is_read", (i, m2))
        ))),

        # ━━ is_starred ━━
        Axiom(label="is_starred_empty", formula=forall([m], Negation(PredApp("is_starred", (const("empty"), m))))),
        
        Axiom(label="is_starred_receive_hit", formula=forall([i, m, m2], Implication(
            PredApp("eq_id", (m, m2)),
            iff(
                PredApp("is_starred", (app("receive", i, m), m2)),
                Conjunction((PredApp("has_msg", (i, m2)), PredApp("is_starred", (i, m2))))
            )
        ))),
        Axiom(label="is_starred_receive_miss", formula=forall([i, m, m2], Implication(
            Negation(PredApp("eq_id", (m, m2))),
            iff(PredApp("is_starred", (app("receive", i, m), m2)), PredApp("is_starred", (i, m2)))
        ))),

        Axiom(label="is_starred_mark_read", formula=forall([i, m, m2], iff(
            PredApp("is_starred", (app("mark_read", i, m), m2)), PredApp("is_starred", (i, m2))
        ))),
        Axiom(label="is_starred_mark_unread", formula=forall([i, m, m2], iff(
            PredApp("is_starred", (app("mark_unread", i, m), m2)), PredApp("is_starred", (i, m2))
        ))),

        Axiom(label="is_starred_delete_hit", formula=forall([i, m, m2], Implication(
            PredApp("eq_id", (m, m2)),
            Negation(PredApp("is_starred", (app("delete", i, m), m2)))
        ))),
        Axiom(label="is_starred_delete_miss", formula=forall([i, m, m2], Implication(
            Negation(PredApp("eq_id", (m, m2))),
            iff(PredApp("is_starred", (app("delete", i, m), m2)), PredApp("is_starred", (i, m2)))
        ))),

        Axiom(label="is_starred_star_hit", formula=forall([i, m, m2], Implication(
            PredApp("eq_id", (m, m2)),
            iff(PredApp("is_starred", (app("star", i, m), m2)), PredApp("has_msg", (i, m2)))
        ))),
        Axiom(label="is_starred_star_miss", formula=forall([i, m, m2], Implication(
            Negation(PredApp("eq_id", (m, m2))),
            iff(PredApp("is_starred", (app("star", i, m), m2)), PredApp("is_starred", (i, m2)))
        ))),

        # ━━ unread_count (state-dispatch) ━━
        Axiom(label="unread_count_empty", formula=eq(app("unread_count", const("empty")), const("zero"))),

        # receive
        Axiom(label="unread_count_receive_preserve", formula=forall([i, m], Implication(
            PredApp("has_msg", (i, m)),
            eq(app("unread_count", app("receive", i, m)), app("unread_count", i))
        ))),
        Axiom(label="unread_count_receive_change", formula=forall([i, m], Implication(
            Negation(PredApp("has_msg", (i, m))),
            eq(app("unread_count", app("receive", i, m)), app("suc", app("unread_count", i)))
        ))),

        # mark_read
        Axiom(label="unread_count_mark_read_change", formula=forall([i, m], Implication(
            Conjunction((PredApp("has_msg", (i, m)), Negation(PredApp("is_read", (i, m))))),
            eq(app("unread_count", app("mark_read", i, m)), app("pred", app("unread_count", i)))
        ))),
        Axiom(label="unread_count_mark_read_preserve", formula=forall([i, m], Implication(
            Negation(Conjunction((PredApp("has_msg", (i, m)), Negation(PredApp("is_read", (i, m)))))),
            eq(app("unread_count", app("mark_read", i, m)), app("unread_count", i))
        ))),

        # mark_unread
        Axiom(label="unread_count_mark_unread_change", formula=forall([i, m], Implication(
            Conjunction((PredApp("has_msg", (i, m)), PredApp("is_read", (i, m)))),
            eq(app("unread_count", app("mark_unread", i, m)), app("suc", app("unread_count", i)))
        ))),
        Axiom(label="unread_count_mark_unread_preserve", formula=forall([i, m], Implication(
            Negation(Conjunction((PredApp("has_msg", (i, m)), PredApp("is_read", (i, m))))),
            eq(app("unread_count", app("mark_unread", i, m)), app("unread_count", i))
        ))),

        # delete
        Axiom(label="unread_count_delete_change", formula=forall([i, m], Implication(
            Conjunction((PredApp("has_msg", (i, m)), Negation(PredApp("is_read", (i, m))))),
            eq(app("unread_count", app("delete", i, m)), app("pred", app("unread_count", i)))
        ))),
        Axiom(label="unread_count_delete_preserve", formula=forall([i, m], Implication(
            Negation(Conjunction((PredApp("has_msg", (i, m)), Negation(PredApp("is_read", (i, m)))))),
            eq(app("unread_count", app("delete", i, m)), app("unread_count", i))
        ))),

        # star
        Axiom(label="unread_count_star", formula=forall([i, m], eq(
            app("unread_count", app("star", i, m)), app("unread_count", i)
        ))),
    )

    return Spec(name="EmailInbox", signature=sig, axioms=axioms)
