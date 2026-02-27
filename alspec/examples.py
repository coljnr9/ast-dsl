"""Textbook algebraic specification examples.

Each function builds a Spec and returns it. Run this file to see them
all printed as JSON.

References:
  - CASL Language Summary (CoFI, 1998)
  - Sannella & Tarlecki, "Essential Concepts" (1997)
  - Sannella & Tarlecki, "Foundations of Algebraic Specification" (2012)
"""

from alspec import (
    Axiom,
    Conjunction,
    Implication,
    Negation,
    PredApp,
    Signature,
    Spec,
    dumps,
)
from alspec.helpers import S, app, atomic, const, eq, fn, forall, pred, var
from alspec.terms import Term

# ===================================================================
# Example 1: Natural Numbers (Peano)
#
# CASL:
#   spec Nat =
#     free type Nat ::= 0 | suc(pre :? Nat)
#
# We express this without free types — just sorts, operations, axioms.
# ===================================================================


def nat_spec() -> Spec:
    """Peano natural numbers.

    sorts: Nat, Bool
    ops:   zero : → Nat
           suc  : Nat → Nat
           add  : Nat × Nat → Nat
    preds: (none)
    axioms:
           ∀ x : Nat • add(zero, x) = x
           ∀ x, y : Nat • add(suc(x), y) = suc(add(x, y))
    """
    x = var("x", "Nat")
    y = var("y", "Nat")

    sig = Signature(
        sorts={
            "Nat": atomic("Nat"),
        },
        functions={
            "zero": fn("zero", [], "Nat"),
            "suc": fn("suc", [("n", "Nat")], "Nat"),
            "add": fn("add", [("x", "Nat"), ("y", "Nat")], "Nat"),
        },
        predicates={},
    )

    axioms = (
        # add(zero, x) = x
        Axiom(
            label="add_zero_left",
            formula=forall(
                [x],
                eq(
                    app("add", const("zero"), x),
                    x,
                ),
            ),
        ),
        # add(suc(x), y) = suc(add(x, y))
        Axiom(
            label="add_suc_left",
            formula=forall(
                [x, y],
                eq(
                    app("add", app("suc", x), y),
                    app("suc", app("add", x, y)),
                ),
            ),
        ),
    )

    return Spec(name="Nat", signature=sig, axioms=axioms)


# ===================================================================
# Example 2: Stack
#
# CASL:
#   sorts STACK, ELEM
#   ops new : → STACK
#       push : STACK × ELEM → STACK
#       pop  : STACK →? STACK
#       top  : STACK →? ELEM
#   preds empty : STACK
# ===================================================================


def stack_spec() -> Spec:
    """Classic Stack specification.

    Axiom Obligation Table Mapping:
    Observer/Pred | Constructor | Status    | Axiom Label
    --------------|-------------|-----------|------------
    pop           | new         | Undefined | (omitted)
    pop           | push        | Defined   | pop_push
    top           | new         | Undefined | (omitted)
    top           | push        | Defined   | top_push
    empty         | new         | Defined   | empty_new
    empty         | push        | Defined   | empty_push
    """
    # Sorts
    elem_sort = atomic("Elem")
    stack_sort = atomic("Stack")

    # Variables
    s = var("s", "Stack")
    e = var("e", "Elem")

    # Signature
    sig = Signature(
        sorts={
            "Elem": elem_sort,
            "Stack": stack_sort,
        },
        functions={
            # Constructors
            "new": fn("new", [], "Stack"),
            "push": fn("push", [("s", "Stack"), ("e", "Elem")], "Stack"),
            # Partial Observers
            "pop": fn("pop", [("s", "Stack")], "Stack", total=False),
            "top": fn("top", [("s", "Stack")], "Elem", total=False),
        },
        predicates={
            # Total Predicate Observer
            "empty": pred("empty", [("s", "Stack")]),
        },
    )

    axioms = (
        # pop × push
        Axiom(
            label="pop_push",
            formula=forall(
                [s, e],
                eq(
                    app("pop", app("push", s, e)),
                    s,
                ),
            ),
        ),
        # top × push
        Axiom(
            label="top_push",
            formula=forall(
                [s, e],
                eq(
                    app("top", app("push", s, e)),
                    e,
                ),
            ),
        ),
        # empty × new
        Axiom(
            label="empty_new",
            formula=PredApp("empty", (const("new"),)),
        ),
        # empty × push
        Axiom(
            label="empty_push",
            formula=forall(
                [s, e],
                Negation(
                    PredApp("empty", (app("push", s, e),)),
                ),
            ),
        ),
    )

    return Spec(name="Stack", signature=sig, axioms=axioms)


# ===================================================================
# Example 3: Partial Order
#
# CASL:
#   spec PartialOrder =
#     sort Elem
#     pred ≤ : Elem × Elem
#     ∀ x, y, z : Elem
#     • x ≤ x                        %(reflexivity)%
#     • x = y if x ≤ y ∧ y ≤ x      %(antisymmetry)%
#     • x ≤ z if x ≤ y ∧ y ≤ z      %(transitivity)%
# ===================================================================


def partial_order_spec() -> Spec:
    """Partial order — the textbook example."""
    x = var("x", "Elem")
    y = var("y", "Elem")
    z = var("z", "Elem")

    def leq(a: Term, b: Term) -> PredApp:
        return PredApp("leq", (a, b))

    sig = Signature(
        sorts={"Elem": atomic("Elem")},
        functions={},
        predicates={
            "leq": pred("leq", [("x", "Elem"), ("y", "Elem")]),
        },
    )

    axioms = (
        # ∀ x : Elem • x ≤ x
        Axiom(
            label="reflexivity",
            formula=forall([x], leq(x, x)),
        ),
        # ∀ x, y : Elem • x ≤ y ∧ y ≤ x ⇒ x = y
        Axiom(
            label="antisymmetry",
            formula=forall(
                [x, y],
                Implication(
                    antecedent=Conjunction((leq(x, y), leq(y, x))),
                    consequent=eq(x, y),
                ),
            ),
        ),
        # ∀ x, y, z : Elem • x ≤ y ∧ y ≤ z ⇒ x ≤ z
        Axiom(
            label="transitivity",
            formula=forall(
                [x, y, z],
                Implication(
                    antecedent=Conjunction((leq(x, y), leq(y, z))),
                    consequent=leq(x, z),
                ),
            ),
        ),
    )

    return Spec(name="PartialOrder", signature=sig, axioms=axioms)


# ===================================================================
# Example 4: Bug Tracker with Ticket Store (comprehensive worked example)
#
# Exercises: key-dispatch (hit/miss via eq_id), PredApp inside logical
# connectives (Implication, Negation, Biconditional), partial observers
# with principled omissions, universal preservation (no key dispatch),
# and the full axiom obligation methodology.
#
# Architecture: Store holds multiple tickets indexed by TicketId.
# Individual tickets are NOT a sort — they're implicit in the Store.
# All ticket properties are accessed through store observers + key.
# ===================================================================


def bug_tracker_spec() -> Spec:
    """Bug tracker with ticket store — the comprehensive worked example.

    Models a Store containing multiple tickets indexed by TicketId.
    Individual tickets are not first-class values; all properties are
    accessed through store observers with a TicketId key.

    Sorts:
        TicketId, Title, Body, UserId  (atomic — opaque identifiers)
        SeverityLevel                  (atomic — uninterpreted, filled by classify)
        Status                         (atomic — enumeration: open, resolved)
        Store                          (atomic — opaque collection)

    Store Constructors:
        empty         : → Store
        create_ticket : Store × TicketId × Title × Body → Store
        resolve_ticket: Store × TicketId → Store
        assign_ticket : Store × TicketId × UserId → Store

    Observers (partial — undefined if ticket doesn't exist):
        get_status   : Store × TicketId →? Status
        get_severity : Store × TicketId →? SeverityLevel
        get_assignee : Store × TicketId →? UserId

    Predicates:
        eq_id       : TicketId × TicketId          (key equality for dispatch)
        has_ticket  : Store × TicketId              (existence check)
        is_critical : Store × TicketId              (severity == high)

    Other:
        classify : Title × Body → SeverityLevel     (uninterpreted)
        open     : → Status                         (constant)
        resolved : → Status                         (constant)
        high     : → SeverityLevel                  (constant)

    Key patterns demonstrated:
        1. PredApp inside Implication (hit case)
        2. Negation(PredApp) inside Implication (miss case)
        3. Negation(PredApp) as complete formula
        4. Implication(PredApp, PredApp)
        5. Implication(Negation(PredApp), Biconditional(PredApp, PredApp))
        6. PredApp inside Biconditional with eq
        7. Universal preservation (no key dispatch needed)
    """
    from alspec import Biconditional, Implication, Negation, PredApp

    # Variables
    s = var("s", "Store")
    k = var("k", "TicketId")
    k2 = var("k2", "TicketId")
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
            # Store constructors
            "empty": fn("empty", [], "Store"),
            "create_ticket": fn(
                "create_ticket",
                [("s", "Store"), ("k", "TicketId"), ("t", "Title"), ("b", "Body")],
                "Store",
            ),
            "resolve_ticket": fn(
                "resolve_ticket",
                [("s", "Store"), ("k", "TicketId")],
                "Store",
            ),
            "assign_ticket": fn(
                "assign_ticket",
                [("s", "Store"), ("k", "TicketId"), ("u", "UserId")],
                "Store",
            ),
            # Uninterpreted function — filled at implementation time
            "classify": fn(
                "classify", [("t", "Title"), ("b", "Body")], "SeverityLevel"
            ),
            # Partial observers (undefined if ticket doesn't exist)
            "get_status": fn(
                "get_status", [("s", "Store"), ("k", "TicketId")], "Status",
                total=False,
            ),
            "get_severity": fn(
                "get_severity", [("s", "Store"), ("k", "TicketId")], "SeverityLevel",
                total=False,
            ),
            "get_assignee": fn(
                "get_assignee", [("s", "Store"), ("k", "TicketId")], "UserId",
                total=False,
            ),
            # Enumeration constants
            "open": fn("open", [], "Status"),
            "resolved": fn("resolved", [], "Status"),
            "high": fn("high", [], "SeverityLevel"),
        },
        predicates={
            "eq_id": pred("eq_id", [("k1", "TicketId"), ("k2", "TicketId")]),
            "has_ticket": pred("has_ticket", [("s", "Store"), ("k", "TicketId")]),
            "is_critical": pred("is_critical", [("s", "Store"), ("k", "TicketId")]),
        },
    )

    axioms = (
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # eq_id basis axioms (reflexivity + symmetry)
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

        Axiom(
            label="eq_id_refl",
            formula=forall([k],
                PredApp("eq_id", (k, k)),                       # Formula ✓
            ),
        ),
        Axiom(
            label="eq_id_sym",
            formula=forall([k, k2], Implication(
                PredApp("eq_id", (k, k2)),                      # Formula ✓
                PredApp("eq_id", (k2, k)),                      # Formula ✓
            )),
        ),

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # has_ticket: predicate, total over store
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

        # Pattern 3: Negation(PredApp) as complete formula
        Axiom(
            label="has_ticket_empty",
            formula=forall([k], Negation(
                PredApp("has_ticket", (const("empty"), k)),      # Formula ✓
            )),
        ),

        # Pattern 4: Implication(PredApp, PredApp) — hit case
        Axiom(
            label="has_ticket_create_hit",
            formula=forall([s, k, k2, t, b], Implication(
                PredApp("eq_id", (k, k2)),                      # Formula ✓
                PredApp("has_ticket", (app("create_ticket", s, k, t, b), k2)),  # Formula ✓
            )),
        ),

        # Pattern 5: Implication(Negation(PredApp), Biconditional(PredApp, PredApp))
        Axiom(
            label="has_ticket_create_miss",
            formula=forall([s, k, k2, t, b], Implication(
                Negation(PredApp("eq_id", (k, k2))),            # Formula ✓
                Biconditional(
                    lhs=PredApp("has_ticket", (app("create_ticket", s, k, t, b), k2)),  # Formula ✓
                    rhs=PredApp("has_ticket", (s, k2)),         # Formula ✓
                ),
            )),
        ),

        # resolve_ticket hit: has_ticket is preserved
        Axiom(
            label="has_ticket_resolve_hit",
            formula=forall([s, k, k2], Implication(
                PredApp("eq_id", (k, k2)),                      # Formula ✓
                Biconditional(
                    lhs=PredApp("has_ticket", (app("resolve_ticket", s, k), k2)),  # Formula ✓
                    rhs=PredApp("has_ticket", (s, k2)),         # Formula ✓
                ),
            )),
        ),

        # resolve_ticket miss: has_ticket delegates
        Axiom(
            label="has_ticket_resolve_miss",
            formula=forall([s, k, k2], Implication(
                Negation(PredApp("eq_id", (k, k2))),            # Formula ✓
                Biconditional(
                    lhs=PredApp("has_ticket", (app("resolve_ticket", s, k), k2)),  # Formula ✓
                    rhs=PredApp("has_ticket", (s, k2)),         # Formula ✓
                ),
            )),
        ),

        # assign_ticket hit: has_ticket is preserved
        Axiom(
            label="has_ticket_assign_hit",
            formula=forall([s, k, k2, u], Implication(
                PredApp("eq_id", (k, k2)),                      # Formula ✓
                Biconditional(
                    lhs=PredApp("has_ticket", (app("assign_ticket", s, k, u), k2)),  # Formula ✓
                    rhs=PredApp("has_ticket", (s, k2)),         # Formula ✓
                ),
            )),
        ),

        # assign_ticket miss: has_ticket delegates
        Axiom(
            label="has_ticket_assign_miss",
            formula=forall([s, k, k2, u], Implication(
                Negation(PredApp("eq_id", (k, k2))),            # Formula ✓
                Biconditional(
                    lhs=PredApp("has_ticket", (app("assign_ticket", s, k, u), k2)),  # Formula ✓
                    rhs=PredApp("has_ticket", (s, k2)),         # Formula ✓
                ),
            )),
        ),

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # get_status: partial — undefined when ticket doesn't exist
        # empty case omitted (undefined — no tickets in empty store)
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

        # Pattern 1: PredApp inside Implication (hit case)
        Axiom(
            label="get_status_create_hit",
            formula=forall([s, k, k2, t, b], Implication(
                PredApp("eq_id", (k, k2)),                      # Formula ✓
                eq(app("get_status", app("create_ticket", s, k, t, b), k2),
                   const("open")),                               # Term ✓
            )),
        ),

        # Pattern 2: Negation(PredApp) inside Implication (miss case)
        Axiom(
            label="get_status_create_miss",
            formula=forall([s, k, k2, t, b], Implication(
                Negation(PredApp("eq_id", (k, k2))),            # Formula ✓
                eq(app("get_status", app("create_ticket", s, k, t, b), k2),
                   app("get_status", s, k2)),                    # Term ✓
            )),
        ),

        # resolve_ticket hit: status becomes resolved (guarded by has_ticket)
        Axiom(
            label="get_status_resolve_hit",
            formula=forall([s, k, k2], Implication(
                PredApp("eq_id", (k, k2)),                      # Formula ✓
                Implication(
                    PredApp("has_ticket", (s, k)),               # Formula ✓ — guard
                    eq(app("get_status", app("resolve_ticket", s, k), k2),
                       const("resolved")),                       # Term ✓
                ),
            )),
        ),

        # resolve_ticket miss: delegates to inner store
        Axiom(
            label="get_status_resolve_miss",
            formula=forall([s, k, k2], Implication(
                Negation(PredApp("eq_id", (k, k2))),            # Formula ✓
                eq(app("get_status", app("resolve_ticket", s, k), k2),
                   app("get_status", s, k2)),                    # Term ✓
            )),
        ),

        # assign_ticket hit: status preserved
        Axiom(
            label="get_status_assign_hit",
            formula=forall([s, k, k2, u], Implication(
                PredApp("eq_id", (k, k2)),                      # Formula ✓
                eq(app("get_status", app("assign_ticket", s, k, u), k2),
                   app("get_status", s, k2)),                    # Term ✓
            )),
        ),

        # assign_ticket miss: delegates
        Axiom(
            label="get_status_assign_miss",
            formula=forall([s, k, k2, u], Implication(
                Negation(PredApp("eq_id", (k, k2))),            # Formula ✓
                eq(app("get_status", app("assign_ticket", s, k, u), k2),
                   app("get_status", s, k2)),                    # Term ✓
            )),
        ),

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # get_severity: partial — undefined when ticket doesn't exist
        # empty case omitted (undefined)
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

        # create_ticket hit: severity = classify(t, b)
        Axiom(
            label="get_severity_create_hit",
            formula=forall([s, k, k2, t, b], Implication(
                PredApp("eq_id", (k, k2)),                      # Formula ✓
                eq(app("get_severity", app("create_ticket", s, k, t, b), k2),
                   app("classify", t, b)),                       # Term ✓
            )),
        ),

        # create_ticket miss: delegates
        Axiom(
            label="get_severity_create_miss",
            formula=forall([s, k, k2, t, b], Implication(
                Negation(PredApp("eq_id", (k, k2))),            # Formula ✓
                eq(app("get_severity", app("create_ticket", s, k, t, b), k2),
                   app("get_severity", s, k2)),                  # Term ✓
            )),
        ),

        # Pattern 7: Universal preservation (no key dispatch needed)
        # resolve_ticket doesn't change severity for ANY ticket, so we
        # don't need hit/miss split — one axiom covers all keys.
        Axiom(
            label="get_severity_resolve",
            formula=forall([s, k, k2], eq(
                app("get_severity", app("resolve_ticket", s, k), k2),
                app("get_severity", s, k2),                      # Term ✓
            )),
        ),

        # assign_ticket doesn't change severity for ANY ticket either.
        Axiom(
            label="get_severity_assign",
            formula=forall([s, k, k2, u], eq(
                app("get_severity", app("assign_ticket", s, k, u), k2),
                app("get_severity", s, k2),                      # Term ✓
            )),
        ),

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # get_assignee: doubly partial
        #   - undefined if ticket doesn't exist
        #   - undefined if ticket exists but has no assignee
        # empty case omitted (undefined — no tickets)
        # create_ticket hit case omitted — new tickets have no assignee,
        #   so get_assignee(create_ticket(s, k, t, b), k) is undefined.
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

        # create_ticket miss: delegates
        Axiom(
            label="get_assignee_create_miss",
            formula=forall([s, k, k2, t, b], Implication(
                Negation(PredApp("eq_id", (k, k2))),            # Formula ✓
                eq(app("get_assignee", app("create_ticket", s, k, t, b), k2),
                   app("get_assignee", s, k2)),                  # Term ✓
            )),
        ),

        # assign_ticket hit: returns the new UserId
        Axiom(
            label="get_assignee_assign_hit",
            formula=forall([s, k, k2, u], Implication(
                PredApp("eq_id", (k, k2)),                      # Formula ✓
                eq(app("get_assignee", app("assign_ticket", s, k, u), k2),
                   u),                                           # Term ✓
            )),
        ),

        # assign_ticket miss: delegates
        Axiom(
            label="get_assignee_assign_miss",
            formula=forall([s, k, k2, u], Implication(
                Negation(PredApp("eq_id", (k, k2))),            # Formula ✓
                eq(app("get_assignee", app("assign_ticket", s, k, u), k2),
                   app("get_assignee", s, k2)),                  # Term ✓
            )),
        ),

        # resolve_ticket doesn't change assignee for ANY ticket.
        Axiom(
            label="get_assignee_resolve",
            formula=forall([s, k, k2], eq(
                app("get_assignee", app("resolve_ticket", s, k), k2),
                app("get_assignee", s, k2),                      # Term ✓
            )),
        ),

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # is_critical: predicate observer
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

        # empty: no tickets → not critical
        Axiom(
            label="is_critical_empty",
            formula=forall([k], Negation(
                PredApp("is_critical", (const("empty"), k)),     # Formula ✓
            )),
        ),

        # Pattern 6: PredApp inside Biconditional with eq
        Axiom(
            label="is_critical_create_hit",
            formula=forall([s, k, k2, t, b], Implication(
                PredApp("eq_id", (k, k2)),                      # Formula ✓
                Biconditional(
                    lhs=PredApp("is_critical", (app("create_ticket", s, k, t, b), k2)),  # Formula ✓
                    rhs=eq(app("classify", t, b), const("high")),  # Formula (Equation) ✓
                ),
            )),
        ),

        # create_ticket miss: delegates
        Axiom(
            label="is_critical_create_miss",
            formula=forall([s, k, k2, t, b], Implication(
                Negation(PredApp("eq_id", (k, k2))),            # Formula ✓
                Biconditional(
                    lhs=PredApp("is_critical", (app("create_ticket", s, k, t, b), k2)),  # Formula ✓
                    rhs=PredApp("is_critical", (s, k2)),         # Formula ✓
                ),
            )),
        ),

        # resolve_ticket doesn't change severity → doesn't change criticality.
        # Universal preservation — no key dispatch needed.
        Axiom(
            label="is_critical_resolve",
            formula=forall([s, k, k2], Biconditional(
                lhs=PredApp("is_critical", (app("resolve_ticket", s, k), k2)),  # Formula ✓
                rhs=PredApp("is_critical", (s, k2)),            # Formula ✓
            )),
        ),

        # assign_ticket doesn't change severity → doesn't change criticality.
        Axiom(
            label="is_critical_assign",
            formula=forall([s, k, k2, u], Biconditional(
                lhs=PredApp("is_critical", (app("assign_ticket", s, k, u), k2)),  # Formula ✓
                rhs=PredApp("is_critical", (s, k2)),            # Formula ✓
            )),
        ),
    )

    return Spec(name="BugTracker", signature=sig, axioms=axioms)


# ===================================================================
# Main — build all examples, print as JSON
# ===================================================================


def main() -> None:
    examples = [
        nat_spec(),
        stack_spec(),
        partial_order_spec(),
        bug_tracker_spec(),
    ]

    for sp in examples:
        print(f"{'=' * 60}")
        print(f"  {sp.name}")
        print(f"{'=' * 60}")
        print(dumps(sp))
        print()


if __name__ == "__main__":
    main()
