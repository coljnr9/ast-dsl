"""Specification: a signature plus axioms.

A specification SP = (Σ, Φ) consists of:
  Σ: a signature (sorts + function symbols + predicates)
  Φ: a set of axioms (formulas over Σ)

The models of SP are all Σ-algebras that satisfy every axiom in Φ.
"""

from __future__ import annotations

from dataclasses import dataclass

from .signature import Signature
from .terms import Formula


@dataclass(frozen=True)
class Axiom:
    """A named axiom."""

    label: str
    formula: Formula


@dataclass(frozen=True)
class Spec:
    """A named specification.

    Example:
        spec PartialOrder =
            sort Elem
            pred ≤ : Elem × Elem
            ∀ x, y, z : Elem
            • x ≤ x                    %(reflexivity)%
            • x = y if x ≤ y ∧ y ≤ x  %(antisymmetry)%
            • x ≤ z if x ≤ y ∧ y ≤ z  %(transitivity)%
    """

    name: str
    signature: Signature
    axioms: tuple[Axiom, ...]
