"""Builder helpers for constructing algebraic specifications.

These are the primary public API for writing specs. Both human authors
and LLM-generated code should use these rather than constructing AST
nodes directly.
"""

from alspec.sorts import AtomicSort, SortRef, ProductSort, ProductField, CoproductSort, CoproductAlt
from alspec.signature import FnParam, FnSymbol, PredSymbol, Totality
from alspec.terms import (
    Var, FnApp, FieldAccess, Equation, UniversalQuant,
    ExistentialQuant, PredApp, Biconditional,
)

S = SortRef

def atomic(name: str) -> AtomicSort:
    return AtomicSort(name=S(name))

def param(name: str, sort: str) -> FnParam:
    return FnParam(name=name, sort=S(sort))

def fn(name: str, params: list[tuple[str, str]], result: str, total: bool = True) -> FnSymbol:
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

def app(fn_name: str, *args) -> FnApp:
    return FnApp(fn_name=fn_name, args=tuple(args))

def const(name: str) -> FnApp:
    return FnApp(fn_name=name, args=())

def eq(lhs, rhs) -> Equation:
    return Equation(lhs=lhs, rhs=rhs)

def forall(variables: list[Var], body) -> UniversalQuant:
    return UniversalQuant(variables=tuple(variables), body=body)

def exists(variables: list[Var], body) -> ExistentialQuant:
    return ExistentialQuant(variables=tuple(variables), body=body)

def iff(lhs, rhs) -> Biconditional:
    """Biconditional: lhs ⇔ rhs."""
    return Biconditional(lhs=lhs, rhs=rhs)
