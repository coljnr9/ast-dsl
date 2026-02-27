"""alspec: Building blocks for many-sorted algebraic specifications."""

from .sorts import (
    AtomicSort,
    CoproductAlt,
    CoproductSort,
    ProductField,
    ProductSort,
    SortDecl,
    SortKind,
    SortRef,
)
from .signature import (
    FnParam,
    FnSymbol,
    PredSymbol,
    Signature,
    Totality,
)
from .terms import (
    Conjunction,
    Definedness,
    Disjunction,
    Equation,
    ExistentialQuant,
    FieldAccess,
    FnApp,
    Formula,
    Implication,
    Biconditional,
    Literal,
    Negation,
    PredApp,
    Term,
    UniversalQuant,
    Var,
)
from .spec import Axiom, Spec
from .serialization import dumps, loads
from .helpers import (
    S, atomic, fn, pred, var, app, const, eq, forall, exists, iff
)
from .result import Ok, Err, Result

__all__ = [
    # Sorts
    "AtomicSort", "CoproductAlt", "CoproductSort", "ProductField",
    "ProductSort", "SortDecl", "SortKind", "SortRef",
    # Signature
    "FnParam", "FnSymbol", "PredSymbol", "Signature", "Totality",
    # Terms
    "Conjunction", "Definedness", "Disjunction", "Equation",
    "ExistentialQuant", "FieldAccess", "FnApp", "Formula",
    "Implication", "Literal", "Negation", "PredApp", "Term",
    "UniversalQuant", "Var", "Biconditional",
    # Spec
    "Axiom", "Spec",
    # Serialization
    "dumps", "loads",
    # Helpers
    "S", "atomic", "fn", "pred", "var", "app", "const", "eq", "forall", "exists", "iff",
    # Result
    "Ok", "Err", "Result",
]
