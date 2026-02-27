"""Axiom index and adequacy checks for algebraic specifications.

This module owns the shared infrastructure that three downstream analyses
depend on:
  - Unconstrained symbols check  (Phase 2, implemented here)
  - Definedness witness check    (Phase 3)
  - Case split completeness check (Phase 4)

The index operates purely on AST structure — no string matching, no
heuristics, no fuzzy classification.

References:
  - alspec.terms  — Formula / Term AST
  - alspec.spec   — Axiom, Spec
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from .check import Diagnostic, Severity
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
    Literal as TermLiteral,
    Negation,
    PredApp,
    Term,
    UniversalQuant,
    Var,
)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Guard:
    """A predicate guard extracted from an Implication antecedent.

    Only simple guards are extracted — a single PredApp or Negation(PredApp).
    Complex antecedents (Conjunction, Disjunction, nested formulas) are NOT
    decomposed into guards.  This is deliberate: compound guards represent
    property axioms (e.g., antisymmetry: leq(x,y) ∧ leq(y,x) ⇒ x = y),
    not key-dispatch case splits.
    """

    pred_name: str
    polarity: Literal["+", "-"]
    args: tuple[Term, ...]


@dataclass(frozen=True)
class ConstrainedSymbol:
    """The symbol being defined/constrained by an axiom.

    For equations: the outermost function on the LHS.
    For predicate assertions: the predicate itself.
    For biconditionals with a predicate LHS: the predicate.
    """

    name: str
    kind: Literal["function", "predicate"]


@dataclass(frozen=True)
class AxiomRecord:
    """Structural decomposition of a single axiom.

    Every axiom in a well-formed spec can be decomposed into:
    - Outermost quantified variables (stripped)
    - Zero or more guards (from nested Implications)
    - A body (the innermost formula)
    - A constrained symbol (what the axiom defines), if identifiable
    - Sets of all referenced function and predicate symbols

    The decomposer is total — it always produces a record, even for axioms
    whose structure doesn't fit the observer×constructor pattern.  In such
    cases, constrained_symbol will be None.
    """

    label: str
    variables: tuple[Var, ...]
    guards: tuple[Guard, ...]
    body: Formula  # innermost formula after stripping quantifiers + implications
    constrained: ConstrainedSymbol | None

    # For equations where constrained is a function, the RHS term
    # (needed for definedness witness check); None otherwise.
    equation_rhs: Term | None

    # All symbols referenced anywhere in the axiom (including guards).
    referenced_fns: frozenset[str]
    referenced_preds: frozenset[str]


@dataclass(frozen=True)
class AxiomIndex:
    """Index over all axioms in a spec, supporting efficient queries.

    Built once from a Spec, then queried by the three analysis checks.
    All fields are immutable — the factory builds mutable structures
    internally and converts at construction time.
    """

    records: tuple[AxiomRecord, ...]

    # Derived lookups: symbol name → all records whose constrained symbol
    # has that name.
    by_constrained: Mapping[str, tuple[AxiomRecord, ...]]

    all_referenced_fns: frozenset[str]
    all_referenced_preds: frozenset[str]

    @classmethod
    def from_spec(cls, spec: Spec) -> AxiomIndex:
        """Build an AxiomIndex from a Spec."""
        records = tuple(decompose_axiom(ax) for ax in spec.axioms)

        # Build mutable dict internally, convert to immutable Mapping at end.
        _by_constrained: dict[str, list[AxiomRecord]] = {}
        for rec in records:
            if rec.constrained is not None:
                _by_constrained.setdefault(rec.constrained.name, []).append(rec)

        by_constrained: Mapping[str, tuple[AxiomRecord, ...]] = {
            k: tuple(v) for k, v in _by_constrained.items()
        }

        if records:
            all_fns: frozenset[str] = frozenset().union(
                *(r.referenced_fns for r in records)
            )
            all_preds: frozenset[str] = frozenset().union(
                *(r.referenced_preds for r in records)
            )
        else:
            all_fns = frozenset()
            all_preds = frozenset()

        return cls(
            records=records,
            by_constrained=by_constrained,
            all_referenced_fns=all_fns,
            all_referenced_preds=all_preds,
        )


# ---------------------------------------------------------------------------
# Step 1: Strip quantifiers
# ---------------------------------------------------------------------------


def _strip_quantifiers(formula: Formula) -> tuple[tuple[Var, ...], Formula]:
    """Recursively strip leading universal/existential quantifiers.

    Returns (variables, inner_formula) where variables is the concatenated
    tuple of all quantified variables in order.

    Existential quantifiers are included for totality; they appear rarely
    in algebraic specs but the decomposer must handle them.
    """
    if isinstance(formula, UniversalQuant):
        inner_vars, inner = _strip_quantifiers(formula.body)
        return (formula.variables + inner_vars, inner)
    if isinstance(formula, ExistentialQuant):
        inner_vars, inner = _strip_quantifiers(formula.body)
        return (formula.variables + inner_vars, inner)
    return ((), formula)


# ---------------------------------------------------------------------------
# Step 2: Extract guards
# ---------------------------------------------------------------------------


def _try_extract_guard(formula: Formula) -> Guard | None:
    """Try to read a simple PredApp or Negation(PredApp) antecedent as a Guard.

    Returns None for compound antecedents (Conjunction, Disjunction, etc.).
    """
    if isinstance(formula, PredApp):
        return Guard(
            pred_name=formula.pred_name,
            polarity="+",
            args=formula.args,
        )
    if isinstance(formula, Negation) and isinstance(formula.formula, PredApp):
        inner = formula.formula
        return Guard(
            pred_name=inner.pred_name,
            polarity="-",
            args=inner.args,
        )
    return None


def _extract_guards(formula: Formula) -> tuple[tuple[Guard, ...], Formula]:
    """Peel off leading simple-guard Implications, returning (guards, body).

    Critical behaviour: when try_extract_guard returns None (complex
    antecedent), the entire Implication becomes the body with no guards
    extracted.  This correctly handles property axioms like antisymmetry.
    """
    if isinstance(formula, Implication):
        guard = _try_extract_guard(formula.antecedent)
        if guard is not None:
            inner_guards, body = _extract_guards(formula.consequent)
            return ((guard,) + inner_guards, body)
        # Complex antecedent — don't decompose further; whole Implication is body.
        return ((), formula)
    return ((), formula)


# ---------------------------------------------------------------------------
# Step 3: Identify constrained symbol
# ---------------------------------------------------------------------------


def _identify_constrained(
    body: Formula,
) -> tuple[ConstrainedSymbol | None, Term | None]:
    """Identify what symbol the axiom body defines/constrains.

    Returns (constrained_symbol, equation_rhs).
    equation_rhs is non-None only when the body is an Equation whose LHS
    is a FnApp — needed for the definedness witness check downstream.
    """
    if isinstance(body, Equation):
        if isinstance(body.lhs, FnApp):
            return (ConstrainedSymbol(name=body.lhs.fn_name, kind="function"), body.rhs)
        # LHS is Var, FieldAccess, or Literal — property axiom, no constrained symbol.
        return (None, None)

    if isinstance(body, PredApp):
        return (ConstrainedSymbol(name=body.pred_name, kind="predicate"), None)

    if isinstance(body, Negation) and isinstance(body.formula, PredApp):
        return (ConstrainedSymbol(name=body.formula.pred_name, kind="predicate"), None)

    if isinstance(body, Biconditional):
        if isinstance(body.lhs, PredApp):
            return (ConstrainedSymbol(name=body.lhs.pred_name, kind="predicate"), None)
        if isinstance(body.rhs, PredApp):
            # Less common: eq(...) ⇔ pred(...)
            return (ConstrainedSymbol(name=body.rhs.pred_name, kind="predicate"), None)
        return (None, None)

    if isinstance(body, Definedness):
        if isinstance(body.term, FnApp):
            return (ConstrainedSymbol(name=body.term.fn_name, kind="function"), None)
        return (None, None)

    # Conjunction, Disjunction, nested Implication, quantifiers — property
    # axioms or structural axioms with no single constrained symbol.
    return (None, None)


# ---------------------------------------------------------------------------
# Step 4: Collect referenced symbols
# ---------------------------------------------------------------------------


def _collect_term_symbols(term: Term, fns: set[str]) -> None:
    """Recursively add all function symbol names reachable from *term*."""
    if isinstance(term, FnApp):
        fns.add(term.fn_name)
        for arg in term.args:
            _collect_term_symbols(arg, fns)
    elif isinstance(term, FieldAccess):
        _collect_term_symbols(term.term, fns)
    # Var and TermLiteral contribute no function symbols.


def _collect_formula_symbols(
    formula: Formula,
    fns: set[str],
    preds: set[str],
) -> None:
    """Recursively add all function/predicate symbol names reachable from *formula*."""
    if isinstance(formula, Equation):
        _collect_term_symbols(formula.lhs, fns)
        _collect_term_symbols(formula.rhs, fns)
    elif isinstance(formula, PredApp):
        preds.add(formula.pred_name)
        for arg in formula.args:
            _collect_term_symbols(arg, fns)
    elif isinstance(formula, Negation):
        _collect_formula_symbols(formula.formula, fns, preds)
    elif isinstance(formula, Conjunction):
        for conjunct in formula.conjuncts:
            _collect_formula_symbols(conjunct, fns, preds)
    elif isinstance(formula, Disjunction):
        for disjunct in formula.disjuncts:
            _collect_formula_symbols(disjunct, fns, preds)
    elif isinstance(formula, Implication):
        _collect_formula_symbols(formula.antecedent, fns, preds)
        _collect_formula_symbols(formula.consequent, fns, preds)
    elif isinstance(formula, Biconditional):
        _collect_formula_symbols(formula.lhs, fns, preds)
        _collect_formula_symbols(formula.rhs, fns, preds)
    elif isinstance(formula, UniversalQuant):
        _collect_formula_symbols(formula.body, fns, preds)
    elif isinstance(formula, ExistentialQuant):
        _collect_formula_symbols(formula.body, fns, preds)
    elif isinstance(formula, Definedness):
        _collect_term_symbols(formula.term, fns)
    # TermLiteral nodes inside formulas are handled by collect_term_symbols.


# ---------------------------------------------------------------------------
# Step 5: Assemble — the main decomposer
# ---------------------------------------------------------------------------


def decompose_axiom(axiom: Axiom) -> AxiomRecord:
    """Decompose a single axiom into an AxiomRecord.

    This function is pure and total — it always returns a record, even for
    axioms whose structure is unusual.
    """
    variables, stripped = _strip_quantifiers(axiom.formula)
    guards, body = _extract_guards(stripped)
    constrained, equation_rhs = _identify_constrained(body)

    fns: set[str] = set()
    preds: set[str] = set()
    # Collect from the *original* formula so guards' symbols are included.
    _collect_formula_symbols(axiom.formula, fns, preds)

    return AxiomRecord(
        label=axiom.label,
        variables=variables,
        guards=guards,
        body=body,
        constrained=constrained,
        equation_rhs=equation_rhs,
        referenced_fns=frozenset(fns),
        referenced_preds=frozenset(preds),
    )


# ---------------------------------------------------------------------------
# Adequacy checks (Phase 2)
# ---------------------------------------------------------------------------


def _check_unconstrained_fns(spec: Spec, index: AxiomIndex) -> list[Diagnostic]:
    """Emit a WARNING for every declared function not referenced in any axiom."""
    unconstrained = set(spec.signature.functions.keys()) - index.all_referenced_fns
    return [
        Diagnostic(
            check="unconstrained_fn",
            severity=Severity.WARNING,
            axiom=None,
            message=f"Function '{name}' is declared but never referenced in any axiom",
            path=None,
        )
        for name in sorted(unconstrained)  # sorted for deterministic output
    ]


def _check_unconstrained_preds(spec: Spec, index: AxiomIndex) -> list[Diagnostic]:
    """Emit a WARNING for every declared predicate not referenced in any axiom."""
    unconstrained = set(spec.signature.predicates.keys()) - index.all_referenced_preds
    return [
        Diagnostic(
            check="unconstrained_pred",
            severity=Severity.WARNING,
            axiom=None,
            message=f"Predicate '{name}' is declared but never referenced in any axiom",
            path=None,
        )
        for name in sorted(unconstrained)
    ]


def _check_orphan_sorts(spec: Spec) -> list[Diagnostic]:
    """Emit a WARNING for every sort not referenced in any function or predicate profile.

    A sort is 'orphaned' when no function's param_sorts or result, and no
    predicate's param_sorts, mentions it.  This is a signature-level check
    that does not depend on the axiom index.
    """
    referenced: set[str] = set()
    for fn in spec.signature.functions.values():
        referenced.add(fn.result)
        referenced.update(fn.param_sorts)
    for pred in spec.signature.predicates.values():
        referenced.update(pred.param_sorts)

    orphaned = set(spec.signature.sorts.keys()) - referenced
    return [
        Diagnostic(
            check="orphan_sort",
            severity=Severity.WARNING,
            axiom=None,
            message=f"Sort '{name}' is declared but not referenced in any function or predicate profile",
            path=None,
        )
        for name in sorted(orphaned)
    ]


def audit_spec(spec: Spec) -> tuple[Diagnostic, ...]:
    """Run adequacy checks on a spec. Returns WARNING-level diagnostics.

    These checks go beyond well-formedness (which the checker verifies)
    to detect structural patterns that indicate likely semantic deficiencies.
    Every check is formally grounded — no heuristics, no fuzzy matching.

    Builds the AxiomIndex internally.  Phases 3 and 4 will add more checks
    here.
    """
    index = AxiomIndex.from_spec(spec)
    diagnostics: list[Diagnostic] = []
    diagnostics.extend(_check_unconstrained_fns(spec, index))
    diagnostics.extend(_check_unconstrained_preds(spec, index))
    diagnostics.extend(_check_orphan_sorts(spec))
    return tuple(diagnostics)
