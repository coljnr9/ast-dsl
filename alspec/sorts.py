"""Sorts for many-sorted algebras.

A sort is a name for a set of values. Sorts come in three kinds:

- Atomic: opaque carrier (e.g., Nat, Bool, Elem)
- Product: named fields, each typed by a sort (e.g., Pair(fst: Nat, snd: Nat))
- Coproduct: tagged alternatives (e.g., IntOrError = int(Int) | error(ErrorMsg))

Following CASL, sorts are declared as part of a signature and referenced
by name (SortRef) everywhere else.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import NewType

# ---------------------------------------------------------------------------
# Sort references — everywhere a sort is *used*, we use a plain string name.
# The actual sort declaration lives in the Signature.
# ---------------------------------------------------------------------------

SortRef = NewType("SortRef", str)


# ---------------------------------------------------------------------------
# Sort declarations
# ---------------------------------------------------------------------------


class SortKind(Enum):
    ATOMIC = "atomic"
    PRODUCT = "product"
    COPRODUCT = "coproduct"


@dataclass(frozen=True)
class AtomicSort:
    """An opaque sort with no internal structure.

    Examples: Nat, Bool, Elem, TicketId
    """

    name: SortRef

    @property
    def kind(self) -> SortKind:
        return SortKind.ATOMIC


@dataclass(frozen=True)
class ProductField:
    """A named, typed field in a product sort."""

    name: str
    sort: SortRef


@dataclass(frozen=True)
class ProductSort:
    """A sort with named fields (record / struct).

    Example:
        Pair = ProductSort("Pair", fields=(
            ProductField("fst", SortRef("Nat")),
            ProductField("snd", SortRef("Nat")),
        ))
    """

    name: SortRef
    fields: tuple[ProductField, ...]

    @property
    def kind(self) -> SortKind:
        return SortKind.PRODUCT

    def field_sort(self, field_name: str) -> SortRef | None:
        """Look up the sort of a field by name. Returns None if not found.

        Guards against malformed entries (e.g. raw tuples from LLM-generated
        code executed via exec that bypasses the dataclass constructor).
        """
        for f in self.fields:
            if not isinstance(f, ProductField):
                continue
            if f.name == field_name:
                return f.sort
        return None

    @property
    def field_names(self) -> tuple[str, ...]:
        return tuple(f.name for f in self.fields if isinstance(f, ProductField))


@dataclass(frozen=True)
class CoproductAlt:
    """A tagged alternative in a coproduct sort."""

    tag: str
    sort: SortRef


@dataclass(frozen=True)
class CoproductSort:
    """A sort that is one of several tagged alternatives (sum type).

    Example:
        IntOrError = CoproductSort("IntOrError", alts=(
            CoproductAlt("ok", SortRef("Int")),
            CoproductAlt("err", SortRef("ErrorMsg")),
        ))
    """

    name: SortRef
    alts: tuple[CoproductAlt, ...]

    @property
    def kind(self) -> SortKind:
        return SortKind.COPRODUCT

    @property
    def tags(self) -> tuple[str, ...]:
        return tuple(a.tag for a in self.alts)


# Union type for any sort declaration
SortDecl = AtomicSort | ProductSort | CoproductSort
