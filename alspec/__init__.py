"""alspec: Building blocks for many-sorted algebraic specifications."""

from .axiom_match import (
    AxiomCellMatch,
    CellCoverage,
    CoverageStatus,
    MatchKind,
    MatchReport,
    match_spec,
    match_spec_sync,
)

from .helpers import (
    S,
    app,
    atomic,
    const,
    eq,
    exists,
    fn,
    forall,
    iff,
    param,
    pred,
    var,
)
from .result import Err, Ok, Result
from .serialization import dumps, loads
from .signature import (
    FnParam,
    FnSymbol,
    GeneratedSortInfo,
    PredSymbol,
    Signature,
    Totality,
)
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
from .spec import Axiom, Spec
from .terms import (
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
    Literal,
    Negation,
    PredApp,
    Term,
    UniversalQuant,
    Var,
)

__all__ = [
    # Axiom matching
    "AxiomCellMatch",
    "CellCoverage",
    "CoverageStatus",
    "MatchKind",
    "MatchReport",
    "match_spec",
    "match_spec_sync",
    # Sorts
    "AtomicSort",
    "CoproductAlt",
    "CoproductSort",
    "ProductField",
    "ProductSort",
    "SortDecl",
    "SortKind",
    "SortRef",
    # Signature
    "FnParam",
    "FnSymbol",
    "GeneratedSortInfo",
    "PredSymbol",
    "Signature",
    "Totality",
    # Terms
    "Conjunction",
    "Definedness",
    "Disjunction",
    "Equation",
    "ExistentialQuant",
    "FieldAccess",
    "FnApp",
    "Formula",
    "Implication",
    "Literal",
    "Negation",
    "PredApp",
    "Term",
    "UniversalQuant",
    "Var",
    "Biconditional",
    # Spec
    "Axiom",
    "Spec",
    # Serialization
    "dumps",
    "loads",
    # Helpers
    "S",
    "atomic",
    "param",
    "fn",
    "pred",
    "var",
    "app",
    "const",
    "eq",
    "forall",
    "exists",
    "iff",
    # Result
    "Ok",
    "Err",
    "Result",
]
