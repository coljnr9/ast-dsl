"""Terms for many-sorted algebras.

A term is a well-sorted expression built from:
  - Variables (with a declared sort)
  - Function applications (f(t₁, ..., tₙ) where f is in the signature)
  - Field access (t.field_name, where t has a product sort)
  - Literals (stand-in for concrete values of a sort)

Terms are the building blocks of equations (axioms).
"""

from __future__ import annotations

from dataclasses import dataclass

from .sorts import SortRef

# ---------------------------------------------------------------------------
# Term AST
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Var:
    """A variable with a declared sort.

    Example: x : Nat
    """

    name: str
    sort: SortRef


@dataclass(frozen=True)
class FnApp:
    """Application of a function symbol to arguments.

    Example: suc(x)           — FnApp("suc", (Var("x", Nat),))
    Example: add(x, suc(y))   — FnApp("add", (Var("x", Nat), FnApp("suc", (Var("y", Nat),))))
    Example: zero              — FnApp("zero", ())  [constant]
    """

    fn_name: str
    args: tuple[Term, ...]


@dataclass(frozen=True)
class FieldAccess:
    """Access a named field on a product-sorted term.

    Example: p.fst  — FieldAccess(Var("p", Pair), "fst")
    """

    term: Term
    field_name: str


@dataclass(frozen=True)
class Literal:
    """A concrete literal value of a known sort.

    This is an escape hatch for things like numeric literals, string
    literals, etc. that don't correspond to a nullary function symbol.

    Example: 42 : Nat — Literal("42", SortRef("Nat"))
    """

    value: str
    sort: SortRef


# Union of all term forms
Term = Var | FnApp | FieldAccess | Literal

# Python needs this for frozen dataclass forward refs
FnApp.__pydantic_model__ = None  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Formulas — for axioms / equations
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Equation:
    """An equation between two terms of the same sort.

    lhs = rhs

    Following CASL, this is a "strong equation" — it holds when both sides
    are defined and equal, or both undefined.

    Example: add(zero, x) = x
    """

    lhs: Term
    rhs: Term


@dataclass(frozen=True)
class PredApp:
    """Application of a predicate to arguments.

    Example: empty(nil)        — PredApp("empty", (FnApp("nil", ()),))
    Example: leq(x, y)        — PredApp("leq", (Var("x", Nat), Var("y", Nat)))
    """

    pred_name: str
    args: tuple[Term, ...]


@dataclass(frozen=True)
class Negation:
    """Logical negation of a formula.

    Example: ¬ empty(cons(x, L))
    """

    formula: Formula


@dataclass(frozen=True)
class Conjunction:
    """Logical AND of formulas.

    Example: x ≤ y ∧ y ≤ z
    """

    conjuncts: tuple[Formula, ...]


@dataclass(frozen=True)
class Disjunction:
    """Logical OR of formulas.

    Example: x ≤ y ∨ y ≤ x
    """

    disjuncts: tuple[Formula, ...]


@dataclass(frozen=True)
class Implication:
    """Logical implication.

    Example: x ≤ y ∧ y ≤ z ⇒ x ≤ z
    """

    antecedent: Formula
    consequent: Formula


@dataclass(frozen=True)
class Biconditional:
    """Logical biconditional (if and only if).

    Example: even(n) ⇔ ¬ odd(n)

    Equivalent to Conjunction(Implication(lhs, rhs), Implication(rhs, lhs))
    but provided as primitive because:
    1. CASL includes ⇔ as a first-class connective.
    2. LLMs consistently need it for predicate equivalence across constructors.
    3. Without it, LLMs write one implication direction and forget the other.
    """

    lhs: Formula
    rhs: Formula


@dataclass(frozen=True)
class UniversalQuant:
    """Universal quantification over variables.

    Example: ∀ x : Nat • x ≤ x
    """

    variables: tuple[Var, ...]
    body: Formula


@dataclass(frozen=True)
class ExistentialQuant:
    """Existential quantification over variables.

    Example: ∃ m : Nat • n < m
    """

    variables: tuple[Var, ...]
    body: Formula


@dataclass(frozen=True)
class Definedness:
    """Definedness assertion for a term (relevant for partial functions).

    Example: def pre(suc(n))
    """

    term: Term


# Union of all formula forms
Formula = (
    Equation
    | PredApp
    | Negation
    | Conjunction
    | Disjunction
    | Implication
    | Biconditional
    | UniversalQuant
    | ExistentialQuant
    | Definedness
)
