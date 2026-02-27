"""many_sorted: Building blocks for many-sorted algebraic specifications."""

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
    Literal,
    Negation,
    PredApp,
    Term,
    UniversalQuant,
    Var,
)
from .spec import Axiom, Spec
from .serialization import dumps, loads

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
    "UniversalQuant", "Var",
    # Spec
    "Axiom", "Spec",
    # Serialization
    "dumps", "loads",
]
