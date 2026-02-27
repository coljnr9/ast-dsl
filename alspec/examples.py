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

    axioms:
        ∀ S : Stack, e : Elem
        • pop(push(S, e)) = S
        • top(push(S, e)) = e
        • empty(new)
        • ¬ empty(push(S, e))
    """
    s = var("S", "Stack")
    e = var("e", "Elem")

    sig = Signature(
        sorts={
            "Stack": atomic("Stack"),
            "Elem": atomic("Elem"),
        },
        functions={
            "new": fn("new", [], "Stack"),
            "push": fn("push", [("S", "Stack"), ("e", "Elem")], "Stack"),
            "pop": fn("pop", [("S", "Stack")], "Stack", total=False),
            "top": fn("top", [("S", "Stack")], "Elem", total=False),
        },
        predicates={
            "empty": pred("empty", [("S", "Stack")]),
        },
    )

    axioms = (
        # pop(push(S, e)) = S
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
        # top(push(S, e)) = e
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
        # empty(new)
        Axiom(
            label="empty_new",
            formula=PredApp("empty", (const("new"),)),
        ),
        # ¬ empty(push(S, e))
        Axiom(
            label="not_empty_push",
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
# Example 4: Bug Tracker (comprehensive worked example)
#
# Exercises: product sorts, coproduct sorts, field access, partial
# functions, predicates, implications, biconditionals, and the full
# axiom obligation pattern.
# ===================================================================


def bug_tracker_spec() -> Spec:
    """Bug tracker — the comprehensive worked example.

    Sorts:
        TicketId, Title, Body          (atomic)
        SeverityLevel                  (atomic — uninterpreted, filled by LLM)
        Status                         (atomic — enumeration via nullary constructors open, resolved)
        Ticket                         (product: id, title, body, severity, status)

    Functions:
        classify   : Title × Body → SeverityLevel        (total)
        create     : TicketId × Title × Body → Ticket    (total, constructor)
        resolve    : Ticket → Ticket                     (total, constructor — transitions status)
        get_severity : Ticket → SeverityLevel             (total, observer)
        get_status   : Ticket → Status                   (total, observer)

    Predicates:
        is_critical : Ticket

    Axiom obligation table:
        get_severity × create  → axiom (get_severity_create)
        get_severity × resolve → axiom (get_severity_resolve)
        get_status   × create  → axiom (get_status_create)
        get_status   × resolve → axiom (get_status_resolve)
        is_critical  × create  → axiom (is_critical_create)
        is_critical  × resolve → axiom (is_critical_resolve)
    """
    from alspec import (
        Biconditional,
        PredApp,
        ProductField,
        ProductSort,
    )

    # Variables
    id_var = var("id", "TicketId")
    t = var("t", "Title")
    b = var("b", "Body")
    tk = var("tk", "Ticket")

    sig = Signature(
        sorts={
            "TicketId": atomic("TicketId"),
            "Title": atomic("Title"),
            "Body": atomic("Body"),
            "SeverityLevel": atomic("SeverityLevel"),
            "Status": atomic("Status"),
            "Ticket": ProductSort(
                name=S("Ticket"),
                fields=(
                    ProductField("id", S("TicketId")),
                    ProductField("title", S("Title")),
                    ProductField("body", S("Body")),
                    ProductField("severity", S("SeverityLevel")),
                    ProductField("status", S("Status")),
                ),
            ),
        },
        functions={
            # Uninterpreted function — filled by LLM at code-gen time
            "classify": fn(
                "classify", [("t", "Title"), ("b", "Body")], "SeverityLevel"
            ),
            # Constructors for Ticket
            "create": fn(
                "create",
                [("id", "TicketId"), ("t", "Title"), ("b", "Body")],
                "Ticket",
            ),
            "resolve": fn("resolve", [("tk", "Ticket")], "Ticket"),
            # Observers
            "get_severity": fn("get_severity", [("tk", "Ticket")], "SeverityLevel"),
            "get_status": fn("get_status", [("tk", "Ticket")], "Status"),
            # Status constants
            "open": fn("open", [], "Status"),
            "resolved": fn("resolved", [], "Status"),
            # SeverityLevel constants
            "high": fn("high", [], "SeverityLevel"),
        },
        predicates={
            "is_critical": pred("is_critical", [("tk", "Ticket")]),
        },
    )

    axioms = (
        # ── get_severity × create ──
        # Observer: get_severity, Constructor: create
        Axiom(
            label="get_severity_create",
            formula=forall(
                [id_var, t, b],
                eq(
                    app("get_severity", app("create", id_var, t, b)),
                    app("classify", t, b),
                ),
            ),
        ),
        # ── get_severity × resolve ──
        # Observer: get_severity, Constructor: resolve
        # Severity is preserved across resolution.
        Axiom(
            label="get_severity_resolve",
            formula=forall(
                [tk],
                eq(
                    app("get_severity", app("resolve", tk)),
                    app("get_severity", tk),
                ),
            ),
        ),
        # ── get_status × create ──
        # Observer: get_status, Constructor: create
        # New tickets start open.
        Axiom(
            label="get_status_create",
            formula=forall(
                [id_var, t, b],
                eq(
                    app("get_status", app("create", id_var, t, b)),
                    const("open"),
                ),
            ),
        ),
        # ── get_status × resolve ──
        # Observer: get_status, Constructor: resolve
        Axiom(
            label="get_status_resolve",
            formula=forall(
                [tk],
                eq(
                    app("get_status", app("resolve", tk)),
                    const("resolved"),
                ),
            ),
        ),
        # ── is_critical × create ──
        # Predicate: is_critical, Constructor: create
        # A newly created ticket is critical iff classify returns high severity.
        # Uses Biconditional: is_critical holds exactly when severity is high.
        Axiom(
            label="is_critical_create",
            formula=forall(
                [id_var, t, b],
                Biconditional(
                    lhs=PredApp("is_critical", (app("create", id_var, t, b),)),
                    rhs=eq(app("classify", t, b), const("high")),
                ),
            ),
        ),
        # ── is_critical × resolve ──
        # Predicate: is_critical, Constructor: resolve
        # Criticality is preserved — resolving doesn't change severity.
        Axiom(
            label="is_critical_resolve",
            formula=forall(
                [tk],
                Biconditional(
                    lhs=PredApp("is_critical", (app("resolve", tk),)),
                    rhs=PredApp("is_critical", (tk,)),
                ),
            ),
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
