"""Builder helpers for constructing algebraic specifications.

These are the primary public API for writing specs. Both human authors
and LLM-generated code should use these rather than constructing AST
nodes directly.
"""

from alspec.signature import FnParam, FnSymbol, PredSymbol, Totality
from alspec.sorts import (
    AtomicSort,
    SortRef,
)
from alspec.terms import (
    Biconditional,
    Conjunction,
    Definedness,
    Disjunction,
    Equation,
    ExistentialQuant,
    FieldAccess,
    FnApp,
    Formula,
    Implication,
    Negation,
    PredApp,
    Term,
    UniversalQuant,
    Var,
)

S = SortRef


def atomic(name: str) -> AtomicSort:
    return AtomicSort(name=S(name))


def param(name: str, sort: str) -> FnParam:
    return FnParam(name=name, sort=S(sort))


def fn(
    name: str, params: list[tuple[str, str]], result: str, total: bool = True
) -> FnSymbol:
    return FnSymbol(
        name=name,
        params=tuple(param(n, s) for n, s in params),
        result=S(result),
        totality=Totality.TOTAL if total else Totality.PARTIAL,
    )


def pred(name: str, params: list[tuple[str, str]]) -> PredSymbol:
    return PredSymbol(name=name, params=tuple(param(n, s) for n, s in params))


def var(name: str, sort: str) -> Var:
    return Var(name=name, sort=S(sort))


def app(fn_name: str, *args: Term) -> FnApp:
    return FnApp(fn_name=fn_name, args=tuple(args))


def const(name: str) -> FnApp:
    return FnApp(fn_name=name, args=())


def eq(lhs: Term, rhs: Term) -> Equation:
    return Equation(lhs=lhs, rhs=rhs)


def forall(variables: list[Var], body: Formula) -> UniversalQuant:
    return UniversalQuant(variables=tuple(variables), body=body)


def exists(variables: list[Var], body: Formula) -> ExistentialQuant:
    return ExistentialQuant(variables=tuple(variables), body=body)


def iff(lhs: Formula, rhs: Formula) -> Biconditional:
    """Biconditional: lhs ⇔ rhs."""
    return Biconditional(lhs=lhs, rhs=rhs)


def negation(formula: Formula) -> Negation:
    """Logical negation: ¬ formula."""
    return Negation(formula=formula)


def conjunction(*conjuncts: Formula) -> Conjunction:
    """Logical AND: f₁ ∧ f₂ ∧ ... ∧ fₙ."""
    return Conjunction(conjuncts=conjuncts)


def disjunction(*disjuncts: Formula) -> Disjunction:
    """Logical OR: f₁ ∨ f₂ ∨ ... ∨ fₙ."""
    return Disjunction(disjuncts=disjuncts)


def implication(antecedent: Formula, consequent: Formula) -> Implication:
    """Logical implication: antecedent ⇒ consequent."""
    return Implication(antecedent=antecedent, consequent=consequent)


def pred_app(pred_name: str, *args: Term) -> PredApp:
    """Apply a predicate to Term arguments."""
    return PredApp(pred_name=pred_name, args=args)


def definedness(term: Term) -> Definedness:
    """Definedness assertion: def(term)."""
    return Definedness(term=term)


def field_access(term: Term, field_name: str) -> FieldAccess:
    """Access a named field on a product-sorted term."""
    return FieldAccess(term=term, field_name=field_name)
