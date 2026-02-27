"""Signatures for many-sorted algebras.

A signature Σ = (S, F) consists of:
  S: a set of sort declarations
  F: a set of function symbols, each with a profile  f : s₁ × s₂ × ... → s

A function symbol with zero arguments is a constant.

Following CASL, we also support:
  - Predicates (functions returning Bool, but declared separately for clarity)
  - Partial functions (may be undefined for some inputs)

A well-formed signature requires that every SortRef appearing in any
function profile refers to a sort in S.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum

from .sorts import SortDecl, SortRef

# ---------------------------------------------------------------------------
# Function symbols
# ---------------------------------------------------------------------------


class Totality(Enum):
    TOTAL = "total"
    PARTIAL = "partial"


@dataclass(frozen=True)
class FnParam:
    """A named parameter of a function symbol."""

    name: str
    sort: SortRef


@dataclass(frozen=True)
class FnSymbol:
    """A function symbol with a profile.

    Examples:
        zero : → Nat                          (constant)
        suc  : Nat → Nat                      (unary total)
        hd   : List →? Elem                   (partial)
        add  : Nat × Nat → Nat                (binary total)
        classify : Title × Body → Severity    (domain function)
    """

    name: str
    params: tuple[FnParam, ...]
    result: SortRef
    totality: Totality = Totality.TOTAL

    @property
    def arity(self) -> int:
        return len(self.params)

    @property
    def param_sorts(self) -> tuple[SortRef, ...]:
        return tuple(p.sort for p in self.params)

    @property
    def is_constant(self) -> bool:
        return self.arity == 0


@dataclass(frozen=True)
class PredSymbol:
    """A predicate symbol (function returning truth value).

    Predicates are kept separate from FnSymbol following CASL convention.
    They don't return a sort — they hold or don't hold.

    Examples:
        empty : List              (unary predicate)
        ≤     : Nat × Nat        (binary predicate)
        member : Elem × Set      (membership)
    """

    name: str
    params: tuple[FnParam, ...]

    @property
    def arity(self) -> int:
        return len(self.params)

    @property
    def param_sorts(self) -> tuple[SortRef, ...]:
        return tuple(p.sort for p in self.params)


# ---------------------------------------------------------------------------
# Signature
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Signature:
    """A many-sorted signature Σ = (S, F, P).

    S: sort declarations, keyed by name
    F: function symbols, keyed by name
    P: predicate symbols, keyed by name

    Invariant: every SortRef in F and P must reference a sort in S.
    """

    sorts: Mapping[str, SortDecl]
    functions: Mapping[str, FnSymbol]
    predicates: Mapping[str, PredSymbol]

    def get_sort(self, name: str) -> SortDecl | None:
        return self.sorts.get(name)

    def get_fn(self, name: str) -> FnSymbol | None:
        return self.functions.get(name)

    def get_pred(self, name: str) -> PredSymbol | None:
        return self.predicates.get(name)

    @property
    def sort_names(self) -> frozenset[str]:
        return frozenset(self.sorts.keys())

    @property
    def fn_names(self) -> frozenset[str]:
        return frozenset(self.functions.keys())

    @property
    def pred_names(self) -> frozenset[str]:
        return frozenset(self.predicates.keys())
