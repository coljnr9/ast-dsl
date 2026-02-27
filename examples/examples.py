"""Textbook algebraic specification examples.

Each function builds a Spec and returns it. Run this file to see them
all printed as JSON.

References:
  - CASL Language Summary (CoFI, 1998)
  - Sannella & Tarlecki, "Essential Concepts" (1997)
  - Sannella & Tarlecki, "Foundations of Algebraic Specification" (2012)
"""

from many_sorted import (
    Axiom,
    AtomicSort,
    Conjunction,
    Equation,
    FnApp,
    FnParam,
    FnSymbol,
    Implication,
    Negation,
    PredApp,
    PredSymbol,
    Signature,
    SortRef,
    Spec,
    Totality,
    UniversalQuant,
    Var,
    dumps,
)

# ===================================================================
# Helpers — short aliases to reduce noise in spec construction
# ===================================================================

S = SortRef


def atomic(name: str) -> AtomicSort:
    return AtomicSort(name=S(name))


def param(name: str, sort: str) -> FnParam:
    return FnParam(name=name, sort=S(sort))


def fn(
    name: str,
    params: list[tuple[str, str]],
    result: str,
    total: bool = True,
) -> FnSymbol:
    return FnSymbol(
        name=name,
        params=tuple(param(n, s) for n, s in params),
        result=S(result),
        totality=Totality.TOTAL if total else Totality.PARTIAL,
    )


def pred(name: str, params: list[tuple[str, str]]) -> PredSymbol:
    return PredSymbol(
        name=name,
        params=tuple(param(n, s) for n, s in params),
    )


def var(name: str, sort: str) -> Var:
    return Var(name=name, sort=S(sort))


def app(fn_name: str, *args: "Var | FnApp") -> FnApp:
    return FnApp(fn_name=fn_name, args=tuple(args))


def const(name: str) -> FnApp:
    """Nullary function application — a constant."""
    return FnApp(fn_name=name, args=())


def eq(lhs: "Var | FnApp", rhs: "Var | FnApp") -> Equation:
    return Equation(lhs=lhs, rhs=rhs)


def forall(variables: list[Var], body: "Equation | Implication | PredApp | Conjunction | Negation") -> UniversalQuant:
    return UniversalQuant(variables=tuple(variables), body=body)


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
            formula=forall([x], eq(
                app("add", const("zero"), x),
                x,
            )),
        ),
        # add(suc(x), y) = suc(add(x, y))
        Axiom(
            label="add_suc_left",
            formula=forall([x, y], eq(
                app("add", app("suc", x), y),
                app("suc", app("add", x, y)),
            )),
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
            formula=forall([s, e], eq(
                app("pop", app("push", s, e)),
                s,
            )),
        ),
        # top(push(S, e)) = e
        Axiom(
            label="top_push",
            formula=forall([s, e], eq(
                app("top", app("push", s, e)),
                e,
            )),
        ),
        # empty(new)
        Axiom(
            label="empty_new",
            formula=PredApp("empty", (const("new"),)),
        ),
        # ¬ empty(push(S, e))
        Axiom(
            label="not_empty_push",
            formula=forall([s, e], Negation(
                PredApp("empty", (app("push", s, e),)),
            )),
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

    leq = lambda a, b: PredApp("leq", (a, b))  # noqa: E731

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
            formula=forall([x, y], Implication(
                antecedent=Conjunction((leq(x, y), leq(y, x))),
                consequent=eq(x, y),
            )),
        ),
        # ∀ x, y, z : Elem • x ≤ y ∧ y ≤ z ⇒ x ≤ z
        Axiom(
            label="transitivity",
            formula=forall([x, y, z], Implication(
                antecedent=Conjunction((leq(x, y), leq(y, z))),
                consequent=leq(x, z),
            )),
        ),
    )

    return Spec(name="PartialOrder", signature=sig, axioms=axioms)


# ===================================================================
# Example 4: Bug Tracker (our domain)
#
# This tests whether the building blocks handle a "real" domain spec
# with product sorts, multiple entities, and uninterpreted functions.
# ===================================================================


def bug_tracker_spec() -> Spec:
    """Simplified bug tracker in algebraic spec style.

    sorts:
        TicketId, Title, Body  (atomic)
        SeverityLevel          (atomic — uninterpreted, filled by LLM)
        Ticket                 (product: id, title, body, severity)

    ops:
        classify : Title × Body → SeverityLevel
        create   : TicketId × Title × Body → Ticket

    axioms:
        ∀ id : TicketId, t : Title, b : Body
        • create(id, t, b).severity = classify(t, b)

    This is the pattern Gravity-Well generates: an uninterpreted function
    (classify) whose result is bound to a field on a product sort (Ticket)
    via an equational axiom. The well-sortedness check would verify:
      - classify returns SeverityLevel
      - Ticket.severity has sort SeverityLevel
      - Therefore the equation is well-sorted.
    """
    from many_sorted import FieldAccess, ProductField, ProductSort

    id_var = var("id", "TicketId")
    t = var("t", "Title")
    b = var("b", "Body")

    sig = Signature(
        sorts={
            "TicketId": atomic("TicketId"),
            "Title": atomic("Title"),
            "Body": atomic("Body"),
            "SeverityLevel": atomic("SeverityLevel"),
            "Ticket": ProductSort(
                name=S("Ticket"),
                fields=(
                    ProductField("id", S("TicketId")),
                    ProductField("title", S("Title")),
                    ProductField("body", S("Body")),
                    ProductField("severity", S("SeverityLevel")),
                ),
            ),
        },
        functions={
            "classify": fn("classify", [("t", "Title"), ("b", "Body")], "SeverityLevel"),
            "create": fn(
                "create",
                [("id", "TicketId"), ("t", "Title"), ("b", "Body")],
                "Ticket",
            ),
        },
        predicates={},
    )

    # create(id, t, b).severity = classify(t, b)
    axioms = (
        Axiom(
            label="ticket_severity_is_classified",
            formula=forall([id_var, t, b], eq(
                FieldAccess(
                    term=app("create", id_var, t, b),
                    field_name="severity",
                ),
                app("classify", t, b),
            )),
        ),
    )

    return Spec(name="BugTracker", signature=sig, axioms=axioms)


# ===================================================================
# Main — build all examples, print as JSON
# ===================================================================


def main():
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
