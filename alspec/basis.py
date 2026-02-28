"""Basis library of fundamental algebraic specifications.

These are the standard "building block" specs that real specifications
compose from. Each is translated from verified sources:

- Bool, Nat, List, FiniteMap: CASL Basic Libraries (CoFI, tool-checked by Hets)
- PartialOrder, TotalOrder: CASL Language Summary (Astesiano et al., 2001)
- Stack, Monoid: Sannella & Tarlecki, "Foundations of Algebraic Specification" (2012)
- Pair: CASL free type Pair

Every spec here follows the methodology:
  1. Declare sorts
  2. Declare constructors (every sort has at least one)
  3. Declare derived operations / observers
  4. Write axioms: one per (operation, constructor) pair

Usage:
    from alspec.sorts import AtomicSort, ProductSort, SortRef
    from alspec.terms import Term, list_spec, ...
"""

from alspec import (
    Axiom,
    Conjunction,
    Disjunction,
    Implication,
    Negation,
    PredApp,
    Signature,
    Spec,
)
from alspec.helpers import app, atomic, const, eq, fn, forall, pred, var
from alspec.terms import Definedness, Term

# =====================================================================
# Bool
#
# CASL: free type Bool ::= True | False
# Source: CASL Basic Libraries, Basic/Booleans
# =====================================================================


def bool_spec() -> Spec:
    """Boolean values with standard connectives.

    sorts:  Bool
    ops:    true, false : → Bool
            not : Bool → Bool
            and, or, implies : Bool × Bool → Bool
    axioms: not(true) = false
            not(false) = true
            and(true, b) = b
            and(false, b) = false
            or(true, b) = true
            or(false, b) = b
            implies(a, b) = or(not(a), b)
    """
    a = var("a", "Bool")
    b = var("b", "Bool")

    sig = Signature(
        sorts={"Bool": atomic("Bool")},
        functions={
            "true": fn("true", [], "Bool"),
            "false": fn("false", [], "Bool"),
            "not": fn("not", [("a", "Bool")], "Bool"),
            "and": fn("and", [("a", "Bool"), ("b", "Bool")], "Bool"),
            "or": fn("or", [("a", "Bool"), ("b", "Bool")], "Bool"),
            "implies": fn("implies", [("a", "Bool"), ("b", "Bool")], "Bool"),
        },
        predicates={},
    )

    axioms = (
        # not: 2 constructors (true, false) → 2 axioms
        Axiom("not_true", eq(app("not", const("true")), const("false"))),
        Axiom("not_false", eq(app("not", const("false")), const("true"))),
        # and: primary arg has 2 constructors → 2 axioms
        Axiom("and_true", forall([b], eq(app("and", const("true"), b), b))),
        Axiom(
            "and_false", forall([b], eq(app("and", const("false"), b), const("false")))
        ),
        # or: primary arg has 2 constructors → 2 axioms
        Axiom("or_true", forall([b], eq(app("or", const("true"), b), const("true")))),
        Axiom("or_false", forall([b], eq(app("or", const("false"), b), b))),
        # implies: defined in terms of not and or
        Axiom(
            "implies_def",
            forall(
                [a, b],
                eq(
                    app("implies", a, b),
                    app("or", app("not", a), b),
                ),
            ),
        ),
    )

    return Spec(name="Bool", signature=sig, axioms=axioms)


# =====================================================================
# Nat (Peano)
#
# CASL: free type Nat ::= 0 | suc(pre :? Nat)
# Source: CASL Basic Libraries, Basic/Numbers
# =====================================================================


def nat_spec() -> Spec:
    """Peano natural numbers with addition, multiplication, ordering.

    sorts:  Nat
    ops:    zero : → Nat
            suc : Nat → Nat
            add, mul : Nat × Nat → Nat
    preds:  leq, lt : Nat × Nat
    axioms: add(zero, y) = y
            add(suc(x), y) = suc(add(x, y))
            mul(zero, y) = zero
            mul(suc(x), y) = add(y, mul(x, y))
            leq(zero, y)
            ¬ lt(y, zero)
            leq(suc(x), suc(y)) ⟺ leq(x, y)
    """
    x = var("x", "Nat")
    y = var("y", "Nat")

    sig = Signature(
        sorts={"Nat": atomic("Nat")},
        functions={
            "zero": fn("zero", [], "Nat"),
            "suc": fn("suc", [("n", "Nat")], "Nat"),
            "add": fn("add", [("x", "Nat"), ("y", "Nat")], "Nat"),
            "mul": fn("mul", [("x", "Nat"), ("y", "Nat")], "Nat"),
        },
        predicates={
            "leq": pred("leq", [("x", "Nat"), ("y", "Nat")]),
            "lt": pred("lt", [("x", "Nat"), ("y", "Nat")]),
        },
    )

    axioms = (
        # add: 2 constructors (zero, suc) on first arg → 2 axioms
        Axiom("add_zero", forall([y], eq(app("add", const("zero"), y), y))),
        Axiom(
            "add_suc",
            forall(
                [x, y],
                eq(
                    app("add", app("suc", x), y),
                    app("suc", app("add", x, y)),
                ),
            ),
        ),
        # mul: 2 constructors on first arg → 2 axioms
        Axiom("mul_zero", forall([y], eq(app("mul", const("zero"), y), const("zero")))),
        Axiom(
            "mul_suc",
            forall(
                [x, y],
                eq(
                    app("mul", app("suc", x), y),
                    app("add", y, app("mul", x, y)),
                ),
            ),
        ),
        # leq: 2 constructors on first arg → 2 axioms
        Axiom("leq_zero", forall([y], PredApp("leq", (const("zero"), y)))),
        Axiom(
            "leq_suc_suc",
            forall(
                [x, y],
                Implication(
                    PredApp("leq", (app("suc", x), app("suc", y))),
                    PredApp("leq", (x, y)),
                ),
            ),
        ),
        # lt: 2 constructors on second arg → 2 axioms
        Axiom("lt_zero", forall([y], Negation(PredApp("lt", (y, const("zero")))))),
        Axiom(
            "lt_suc",
            forall(
                [x, y],
                Implication(
                    PredApp("lt", (app("suc", x), app("suc", y))),
                    PredApp("lt", (x, y)),
                ),
            ),
        ),
    )

    return Spec(name="Nat", signature=sig, axioms=axioms)


# =====================================================================
# Pair
#
# CASL: free type Pair ::= pair(fst : Elem1; snd : Elem2)
# Source: CASL datatypes
# =====================================================================


def pair_spec() -> Spec:
    """Pair of two element sorts with projections.

    sorts:  Elem1, Elem2, Pair
    ops:    pair : Elem1 × Elem2 → Pair
            fst : Pair → Elem1
            snd : Pair → Elem2
    axioms: fst(pair(a, b)) = a
            snd(pair(a, b)) = b
    """
    a = var("a", "Elem1")
    b = var("b", "Elem2")

    sig = Signature(
        sorts={
            "Elem1": atomic("Elem1"),
            "Elem2": atomic("Elem2"),
            "Pair": atomic("Pair"),
        },
        functions={
            "pair": fn("pair", [("a", "Elem1"), ("b", "Elem2")], "Pair"),
            "fst": fn("fst", [("p", "Pair")], "Elem1"),
            "snd": fn("snd", [("p", "Pair")], "Elem2"),
        },
        predicates={},
    )

    axioms = (
        # fst/snd: 1 constructor (pair) → 1 axiom each
        Axiom("fst_pair", forall([a, b], eq(app("fst", app("pair", a, b)), a))),
        Axiom("snd_pair", forall([a, b], eq(app("snd", app("pair", a, b)), b))),
    )

    return Spec(name="Pair", signature=sig, axioms=axioms)


# =====================================================================
# Stack
#
# Source: Sannella & Tarlecki (2012), Chapter 1
# =====================================================================


def stack_spec() -> Spec:
    """Stack with partial pop/top.

    sorts:  Stack, Elem
    ops:    new : → Stack
            push : Stack × Elem → Stack
            pop : Stack →? Stack
            top : Stack →? Elem
    preds:  empty : Stack
    axioms: pop(push(S, e)) = S
            top(push(S, e)) = e
            empty(new)
            ¬ empty(push(S, e))
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
        # pop: partial, skip new (undefined), push → 1 axiom
        Axiom(
            "pop_push",
            forall(
                [s, e],
                eq(
                    app("pop", app("push", s, e)),
                    s,
                ),
            ),
        ),
        # top: partial, skip new (undefined), push → 1 axiom
        Axiom(
            "top_push",
            forall(
                [s, e],
                eq(
                    app("top", app("push", s, e)),
                    e,
                ),
            ),
        ),
        # empty: 2 constructors → 2 axioms
        Axiom("empty_new", PredApp("empty", (const("new"),))),
        Axiom(
            "not_empty_push",
            forall(
                [s, e],
                Negation(
                    PredApp("empty", (app("push", s, e),)),
                ),
            ),
        ),
    )

    return Spec(name="Stack", signature=sig, axioms=axioms)


# =====================================================================
# List
#
# CASL: free type List[Elem] ::= nil | cons(hd :? Elem; tl :? List)
# Source: CASL Basic Libraries, Basic/StructuredDatatypes
# =====================================================================


def list_spec() -> Spec:
    """List with head, tail, append, length.

    sorts:  Elem, List, Nat
    ops:    nil : → List
            cons : Elem × List → List
            hd : List →? Elem
            tl : List →? List
            append : List × List → List
            length : List → Nat
            zero : → Nat
            suc : Nat → Nat
    axioms: hd(cons(x, L)) = x
            tl(cons(x, L)) = L
            append(nil, M) = M
            append(cons(x, L), M) = cons(x, append(L, M))
            length(nil) = zero
            length(cons(x, L)) = suc(length(L))
    """
    x = var("x", "Elem")
    L = var("L", "List")
    M = var("M", "List")

    sig = Signature(
        sorts={
            "Elem": atomic("Elem"),
            "List": atomic("List"),
            "Nat": atomic("Nat"),
        },
        functions={
            # Constructors
            "nil": fn("nil", [], "List"),
            "cons": fn("cons", [("x", "Elem"), ("L", "List")], "List"),
            # Nat constructors (needed for length)
            "zero": fn("zero", [], "Nat"),
            "suc": fn("suc", [("n", "Nat")], "Nat"),
            # Observers (partial — undefined on nil)
            "hd": fn("hd", [("L", "List")], "Elem", total=False),
            "tl": fn("tl", [("L", "List")], "List", total=False),
            # Derived operations
            "append": fn("append", [("L", "List"), ("M", "List")], "List"),
            "length": fn("length", [("L", "List")], "Nat"),
        },
        predicates={},
    )

    axioms = (
        # hd: partial, skip nil, cons → 1 axiom
        Axiom("hd_cons", forall([x, L], eq(app("hd", app("cons", x, L)), x))),
        # tl: partial, skip nil, cons → 1 axiom
        Axiom("tl_cons", forall([x, L], eq(app("tl", app("cons", x, L)), L))),
        # append: 2 constructors (nil, cons) on first arg → 2 axioms
        Axiom("append_nil", forall([M], eq(app("append", const("nil"), M), M))),
        Axiom(
            "append_cons",
            forall(
                [x, L, M],
                eq(
                    app("append", app("cons", x, L), M),
                    app("cons", x, app("append", L, M)),
                ),
            ),
        ),
        # length: 2 constructors on arg → 2 axioms
        Axiom("length_nil", eq(app("length", const("nil")), const("zero"))),
        Axiom(
            "length_cons",
            forall(
                [x, L],
                eq(
                    app("length", app("cons", x, L)),
                    app("suc", app("length", L)),
                ),
            ),
        ),
    )

    return Spec(name="List", signature=sig, axioms=axioms)


# =====================================================================
# PartialOrder
#
# Source: CASL Language Summary (1998); Sannella & Tarlecki (2012)
# =====================================================================


def partial_order_spec() -> Spec:
    """Partial order: reflexive, antisymmetric, transitive.

    sorts:  Elem
    preds:  leq : Elem × Elem
    axioms: leq(x, x)                                  (reflexivity)
            leq(x, y) ∧ leq(y, x) ⇒ x = y             (antisymmetry)
            leq(x, y) ∧ leq(y, z) ⇒ leq(x, z)         (transitivity)
    """
    x = var("x", "Elem")
    y = var("y", "Elem")
    z = var("z", "Elem")

    sig = Signature(
        sorts={"Elem": atomic("Elem")},
        functions={},
        predicates={"leq": pred("leq", [("x", "Elem"), ("y", "Elem")])},
    )

    def leq(a: Term, b: Term) -> PredApp:
        return PredApp("leq", (a, b))

    axioms = (
        Axiom("reflexivity", forall([x], leq(x, x))),
        Axiom(
            "antisymmetry",
            forall(
                [x, y],
                Implication(
                    Conjunction((leq(x, y), leq(y, x))),
                    eq(x, y),
                ),
            ),
        ),
        Axiom(
            "transitivity",
            forall(
                [x, y, z],
                Implication(
                    Conjunction((leq(x, y), leq(y, z))),
                    leq(x, z),
                ),
            ),
        ),
    )

    return Spec(name="PartialOrder", signature=sig, axioms=axioms)


# =====================================================================
# TotalOrder (extends PartialOrder with totality)
#
# Source: CASL Language Summary
# =====================================================================


def total_order_spec() -> Spec:
    """Total order: partial order + totality.

    sorts:  Elem
    preds:  leq : Elem × Elem
    axioms: (all of PartialOrder) +
            leq(x, y) ∨ leq(y, x)                      (totality)
    """
    x = var("x", "Elem")
    y = var("y", "Elem")
    z = var("z", "Elem")

    sig = Signature(
        sorts={"Elem": atomic("Elem")},
        functions={},
        predicates={"leq": pred("leq", [("x", "Elem"), ("y", "Elem")])},
    )

    def leq(a: Term, b: Term) -> PredApp:
        return PredApp("leq", (a, b))

    axioms = (
        Axiom("reflexivity", forall([x], leq(x, x))),
        Axiom(
            "antisymmetry",
            forall(
                [x, y],
                Implication(
                    Conjunction((leq(x, y), leq(y, x))),
                    eq(x, y),
                ),
            ),
        ),
        Axiom(
            "transitivity",
            forall(
                [x, y, z],
                Implication(
                    Conjunction((leq(x, y), leq(y, z))),
                    leq(x, z),
                ),
            ),
        ),
        Axiom("totality", forall([x, y], Disjunction((leq(x, y), leq(y, x))))),
    )

    return Spec(name="TotalOrder", signature=sig, axioms=axioms)


# =====================================================================
# Monoid
#
# Source: Sannella & Tarlecki (2012), standard algebraic example
# =====================================================================


def monoid_spec() -> Spec:
    """Monoid: associative operation with unit.

    sorts:  M
    ops:    e : → M            (unit)
            op : M × M → M     (binary operation)
    axioms: op(e, x) = x                   (left unit)
            op(x, e) = x                   (right unit)
            op(op(x, y), z) = op(x, op(y, z))  (associativity)
    """
    x = var("x", "M")
    y = var("y", "M")
    z = var("z", "M")

    sig = Signature(
        sorts={"M": atomic("M")},
        functions={
            "e": fn("e", [], "M"),
            "op": fn("op", [("x", "M"), ("y", "M")], "M"),
        },
        predicates={},
    )

    axioms = (
        Axiom("left_unit", forall([x], eq(app("op", const("e"), x), x))),
        Axiom("right_unit", forall([x], eq(app("op", x, const("e")), x))),
        Axiom(
            "associativity",
            forall(
                [x, y, z],
                eq(
                    app("op", app("op", x, y), z),
                    app("op", x, app("op", y, z)),
                ),
            ),
        ),
    )

    return Spec(name="Monoid", signature=sig, axioms=axioms)


# =====================================================================
# FiniteMap (the key pattern the library example needs)
#
# CASL: free { type FiniteMap ::= [] | [_/_](FiniteMap; Val; Key) }
# Source: CASL Language Summary, Fig. 4; Sannella & Tarlecki (2012)
#
# This is the fundamental "lookup with equality" pattern.
# =====================================================================


def finite_map_spec() -> Spec:
    """Finite map from keys to values with equality-based lookup.

    sorts:  Key, Val, Map
    ops:    empty : → Map
            update : Map × Key × Val → Map
            lookup : Map × Key →? Val
    preds:  eq_key : Key × Key
    axioms: ¬def(lookup(empty, k))          (explicit undefinedness)
            eq_key(k1, k2) ⇒ lookup(update(M, k1, v), k2) = v
            ¬ eq_key(k1, k2) ⇒ lookup(update(M, k1, v), k2) = lookup(M, k2)
            eq_key(k, k)                              (reflexivity)
            eq_key(k1, k2) ⇒ eq_key(k2, k1)          (symmetry)

    This spec uses loose semantics: undefinedness is stated explicitly with
    Negation(Definedness(...)) rather than left implicit by omission.

    This is the pattern that any "indexed collection" spec needs:
    a state built by update, queried by lookup, dispatched on key equality.
    """
    k = var("k", "Key")
    k1 = var("k1", "Key")
    k2 = var("k2", "Key")
    v = var("v", "Val")
    M = var("M", "Map")

    def eq_key(a: Term, b: Term) -> PredApp:
        return PredApp("eq_key", (a, b))

    sig = Signature(
        sorts={
            "Key": atomic("Key"),
            "Val": atomic("Val"),
            "Map": atomic("Map"),
        },
        functions={
            "empty": fn("empty", [], "Map"),
            "update": fn("update", [("M", "Map"), ("k", "Key"), ("v", "Val")], "Map"),
            "lookup": fn("lookup", [("M", "Map"), ("k", "Key")], "Val", total=False),
        },
        predicates={
            "eq_key": pred("eq_key", [("k1", "Key"), ("k2", "Key")]),
        },
    )

    axioms = (
        # lookup on empty: explicitly undefined (¬Defined(lookup(empty, k)))
        Axiom(
            "lookup_empty_undef",
            forall([k], Negation(Definedness(app("lookup", const("empty"), k)))),
        ),
        # lookup on update: 2 cases (same key, different key)
        Axiom(
            "lookup_update_hit",
            forall(
                [M, k1, k2, v],
                Implication(
                    eq_key(k1, k2),
                    eq(app("lookup", app("update", M, k1, v), k2), v),
                ),
            ),
        ),
        Axiom(
            "lookup_update_miss",
            forall(
                [M, k1, k2, v],
                Implication(
                    Negation(eq_key(k1, k2)),
                    eq(
                        app("lookup", app("update", M, k1, v), k2), app("lookup", M, k2)
                    ),
                ),
            ),
        ),
        # eq_key is an equivalence (at minimum reflexive + symmetric for map correctness)
        Axiom("eq_key_refl", forall([k], eq_key(k, k))),
        Axiom(
            "eq_key_sym",
            forall(
                [k1, k2],
                Implication(
                    eq_key(k1, k2),
                    eq_key(k2, k1),
                ),
            ),
        ),
    )

    return Spec(name="FiniteMap", signature=sig, axioms=axioms)


# =====================================================================
# Summary: all basis specs
# =====================================================================

ALL_BASIS_SPECS = [
    bool_spec,
    nat_spec,
    pair_spec,
    stack_spec,
    list_spec,
    partial_order_spec,
    total_order_spec,
    monoid_spec,
    finite_map_spec,
]


if __name__ == "__main__":
    for spec_fn in ALL_BASIS_SPECS:
        sp = spec_fn()
        n_sorts = len(sp.signature.sorts)
        n_fns = len(sp.signature.functions)
        n_preds = len(sp.signature.predicates)
        n_axioms = len(sp.axioms)
        print(
            f"{sp.name:20s}  sorts={n_sorts}  fns={n_fns}  preds={n_preds}  axioms={n_axioms}"
        )
