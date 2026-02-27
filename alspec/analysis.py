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
from typing import assert_never

from .check import Diagnostic, Severity
from .signature import Signature, Totality
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


def _peel_body(
    formula: Formula,
    depth: int = 0,
) -> tuple[tuple[Guard, ...], Formula]:
    """Recursively peel Implication layers, collecting PredApp guards.

    For each Implication encountered:
    - If antecedent is PredApp → extract as Positive guard, recurse into consequent
    - If antecedent is Negation(PredApp) → extract as Negative guard, recurse into consequent
    - If antecedent is anything else (Equation, Definedness, Conjunction, ...) →
      DON'T extract a guard, but DO recurse into the consequent

    The depth limit (10) is a safety net against pathologically deep formulas;
    in practice algebraic specs are 2-4 levels deep.

    Returns (collected_guards, terminal_body).
    """
    if not isinstance(formula, Implication) or depth >= 10:
        return ((), formula)

    guard = _try_extract_guard(formula.antecedent)
    if guard is not None:
        inner_guards, body = _peel_body(formula.consequent, depth + 1)
        return ((guard,) + inner_guards, body)

    # Non-PredApp antecedent (Equation, Conjunction, Definedness, ...)
    # — skip the guard but recurse into the consequent so we can still
    # reach the terminal body and extract the constrained symbol.
    if isinstance(formula.antecedent, Conjunction):
        # Conjunction antecedents (e.g. antisymmetry) are property axioms;
        # treat the entire Implication as the terminal body so they stay
        # constrained=None, preserving existing behaviour.
        return ((), formula)

    inner_guards, body = _peel_body(formula.consequent, depth + 1)
    return (inner_guards, body)


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

    if isinstance(body, Negation) and isinstance(body.formula, Definedness):
        inner = body.formula
        if isinstance(inner.term, FnApp):
            return (ConstrainedSymbol(name=inner.term.fn_name, kind="function"), None)
        return (None, None)

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
    guards, body = _peel_body(stripped)
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


# ---------------------------------------------------------------------------
# Phase 3 helpers — definitely-defined predicate and Definedness scanner
# ---------------------------------------------------------------------------


def _definitely_defined(term: Term, sig: Signature) -> bool:
    """Conservative check: is this term definitely defined under total variable assignments?

    Based on CASL's definite definedness (Astesiano et al. §3.3).
    A term is definitely defined when its definedness follows from
    structure alone, without reasoning about axiom interactions.
    """
    if isinstance(term, Var):
        return True
    if isinstance(term, TermLiteral):
        return True
    if isinstance(term, FieldAccess):
        return _definitely_defined(term.term, sig)
    if isinstance(term, FnApp):
        fn_sym = sig.get_fn(term.fn_name)
        if fn_sym is None:
            return False  # undeclared function — can't determine
        if fn_sym.totality != Totality.TOTAL:
            return False  # partial function — never definitely defined
        return all(_definitely_defined(arg, sig) for arg in term.args)
    assert_never(term)


def _has_definedness_assertion(formula: Formula, fn_name: str) -> bool:
    """Does this formula contain a Definedness(FnApp(fn_name, ...)) node anywhere?"""
    if isinstance(formula, Definedness):
        if isinstance(formula.term, FnApp) and formula.term.fn_name == fn_name:
            return True
        return False
    if isinstance(formula, Equation):
        return False  # Equations contain Terms, not Formulas
    if isinstance(formula, PredApp):
        return False
    if isinstance(formula, Negation):
        return _has_definedness_assertion(formula.formula, fn_name)
    if isinstance(formula, Conjunction):
        return any(_has_definedness_assertion(f, fn_name) for f in formula.conjuncts)
    if isinstance(formula, Disjunction):
        return any(_has_definedness_assertion(f, fn_name) for f in formula.disjuncts)
    if isinstance(formula, Implication):
        return (
            _has_definedness_assertion(formula.antecedent, fn_name)
            or _has_definedness_assertion(formula.consequent, fn_name)
        )
    if isinstance(formula, Biconditional):
        return (
            _has_definedness_assertion(formula.lhs, fn_name)
            or _has_definedness_assertion(formula.rhs, fn_name)
        )
    if isinstance(formula, UniversalQuant):
        return _has_definedness_assertion(formula.body, fn_name)
    if isinstance(formula, ExistentialQuant):
        return _has_definedness_assertion(formula.body, fn_name)
    assert_never(formula)


def _has_witnessing_equation(formula: Formula, fn_name: str, sig: Signature) -> bool:
    """Does this formula contain f(args) = t where t is definitely defined?

    Catches witnessing equations buried inside compound guards (e.g.
    Conjunction antecedents) that the decomposer cannot attribute to f
    as a constrained symbol.  Symmetry is respected: t = f(args) counts
    too.
    """
    if isinstance(formula, Equation):
        if (
            isinstance(formula.lhs, FnApp)
            and formula.lhs.fn_name == fn_name
            and _definitely_defined(formula.rhs, sig)
        ):
            return True
        # Symmetric: rhs = f(args)
        if (
            isinstance(formula.rhs, FnApp)
            and formula.rhs.fn_name == fn_name
            and _definitely_defined(formula.lhs, sig)
        ):
            return True
        return False
    if isinstance(formula, PredApp):
        return False
    if isinstance(formula, Negation):
        return _has_witnessing_equation(formula.formula, fn_name, sig)
    if isinstance(formula, Conjunction):
        return any(_has_witnessing_equation(f, fn_name, sig) for f in formula.conjuncts)
    if isinstance(formula, Disjunction):
        return any(_has_witnessing_equation(f, fn_name, sig) for f in formula.disjuncts)
    if isinstance(formula, Implication):
        return (
            _has_witnessing_equation(formula.antecedent, fn_name, sig)
            or _has_witnessing_equation(formula.consequent, fn_name, sig)
        )
    if isinstance(formula, Biconditional):
        return (
            _has_witnessing_equation(formula.lhs, fn_name, sig)
            or _has_witnessing_equation(formula.rhs, fn_name, sig)
        )
    if isinstance(formula, UniversalQuant):
        return _has_witnessing_equation(formula.body, fn_name, sig)
    if isinstance(formula, ExistentialQuant):
        return _has_witnessing_equation(formula.body, fn_name, sig)
    if isinstance(formula, Definedness):
        return False  # Definedness nodes are handled by the secondary scan
    assert_never(formula)


def _check_unwitnessed_partials(spec: Spec, index: AxiomIndex) -> list[Diagnostic]:
    """Detect partial functions with no definedness witness.

    A partial function f is unwitnessed when:
    1. No axiom constraining f has an equation RHS that is definitely defined, AND
    2. No axiom in the entire spec contains Definedness(FnApp(f, ...))

    Primary mechanism (1) handles the common case: f(constructor_term) = value.
    Secondary mechanism (2) catches explicit Definedness assertions that the
    decomposer can't attribute to f as a constrained symbol.
    """
    diagnostics: list[Diagnostic] = []

    for fn_name, fn_sym in spec.signature.functions.items():
        if fn_sym.totality != Totality.PARTIAL:
            continue

        witnessed = False

        # Primary: check equation RHS in constrained records
        constrained_records = index.by_constrained.get(fn_name, ())
        for rec in constrained_records:
            if rec.equation_rhs is not None:
                if _definitely_defined(rec.equation_rhs, spec.signature):
                    witnessed = True
                    break

        # Secondary: scan all axiom formulas for Definedness assertions
        if not witnessed:
            for axiom in spec.axioms:
                if _has_definedness_assertion(axiom.formula, fn_name):
                    witnessed = True
                    break

        # Tertiary: scan all axiom formulas for witnessing equations
        # that the decomposer couldn't attribute (e.g. under Conjunction guards)
        if not witnessed:
            for axiom in spec.axioms:
                if _has_witnessing_equation(axiom.formula, fn_name, spec.signature):
                    witnessed = True
                    break

        if not witnessed:
            diagnostics.append(
                Diagnostic(
                    check="unwitnessed_partial",
                    severity=Severity.WARNING,
                    axiom=None,
                    message=(
                        f"Partial function '{fn_name}' has no definedness witness: "
                        f"no axiom forces it to be defined on any input"
                    ),
                    path=None,
                )
            )

    return diagnostics


# ---------------------------------------------------------------------------
# Adequacy checks (Phase 2 — original)
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
    """Run adequacy checks on a spec. Returns diagnostics.

    These checks go beyond well-formedness (which the checker verifies)
    to detect structural patterns that indicate likely semantic deficiencies.
    Every check is formally grounded — no heuristics, no fuzzy matching.

    Builds the AxiomIndex internally.
    """
    index = AxiomIndex.from_spec(spec)
    diagnostics: list[Diagnostic] = []
    diagnostics.extend(_check_unconstrained_fns(spec, index))
    diagnostics.extend(_check_unconstrained_preds(spec, index))
    diagnostics.extend(_check_orphan_sorts(spec))
    diagnostics.extend(_check_unwitnessed_partials(spec, index))  # Phase 3
    diagnostics.extend(_check_case_splits(spec, index))           # Phase 4
    return tuple(diagnostics)


# ---------------------------------------------------------------------------
# Phase 4 — Case split completeness
# ---------------------------------------------------------------------------


def _extract_constructor(rec: AxiomRecord) -> str | None:
    """Extract the constructor name from an axiom record's body.

    For an equation body like ``obs(ctor(m, k, v), k2) = rhs``,
    the constructor is the FnApp in the first argument of the outermost
    observer FnApp on the equation's LHS.

    For a PredApp, Negation(PredApp), or Biconditional with a PredApp,
    looks at the PredApp's first argument for a constructor FnApp.

    Returns None when the body structure doesn't match these patterns.
    """
    body = rec.body

    if isinstance(body, Equation):
        if isinstance(body.lhs, FnApp) and body.lhs.args:
            first_arg = body.lhs.args[0]
            if isinstance(first_arg, FnApp):
                return first_arg.fn_name
        return None

    # Bare PredApp: pred(ctor(args...), ...)
    if isinstance(body, PredApp):
        if body.args:
            first_arg = body.args[0]
            if isinstance(first_arg, FnApp):
                return first_arg.fn_name
        return None

    # Negation(PredApp): ¬pred(ctor(args...), ...)
    if isinstance(body, Negation) and isinstance(body.formula, PredApp):
        inner = body.formula
        if inner.args:
            first_arg = inner.args[0]
            if isinstance(first_arg, FnApp):
                return first_arg.fn_name
        return None

    # Biconditional with PredApp on LHS: pred(ctor(args...), ...) ⇔ ...
    if isinstance(body, Biconditional):
        pred_app: PredApp | None = None
        if isinstance(body.lhs, PredApp):
            pred_app = body.lhs
        elif isinstance(body.rhs, PredApp):
            pred_app = body.rhs
        if pred_app is not None and pred_app.args:
            first_arg = pred_app.args[0]
            if isinstance(first_arg, FnApp):
                return first_arg.fn_name
        return None

    # Negation(Definedness(FnApp(obs, ctor(...), ...))): ¬def(obs(ctor(args...), ...))
    if isinstance(body, Negation) and isinstance(body.formula, Definedness):
        inner_fn = body.formula.term
        if isinstance(inner_fn, FnApp) and inner_fn.args:
            first_arg = inner_fn.args[0]
            if isinstance(first_arg, FnApp):
                return first_arg.fn_name
        return None

    # Bare Definedness(FnApp(obs, ctor(...), ...)): def(obs(ctor(args...), ...))
    if isinstance(body, Definedness):
        inner_fn = body.term
        if isinstance(inner_fn, FnApp) and inner_fn.args:
            first_arg = inner_fn.args[0]
            if isinstance(first_arg, FnApp):
                return first_arg.fn_name
        return None

    return None


def _guard_key(guard: Guard) -> tuple[str, tuple[str, ...]]:
    """Build a syntactic key for a guard.

    Uses ``(pred_name, tuple_of_arg_reprs)`` where each arg is either
    the variable name (for Var) or its repr (for complex terms).
    This is intentionally conservative: only syntactically identical
    guards are considered the same predicate dispatch.
    """
    arg_parts: list[str] = []
    for arg in guard.args:
        if isinstance(arg, Var):
            arg_parts.append(arg.name)
        else:
            arg_parts.append(repr(arg))
    return (guard.pred_name, tuple(arg_parts))


def _check_group(
    obs_name: str,
    con_name: str,
    records: list[AxiomRecord],
    spec: Spec,
    diagnostics: list[Diagnostic],
) -> None:
    """Check a single (observer, constructor) group for case split completeness.

    If the constructor is declared partial (total=False), skip all
    case_split_incomplete checks for this group.  When a partial constructor
    is undefined, strict error propagation makes any observer over it also
    undefined — no axiom is needed or useful for that case, so a one-sided
    guard is correct by design.

    If any record has no guards, the group has a universal axiom covering
    all inputs — no case split is needed.  If a group has BOTH guarded and
    unguarded axioms, emits a ``case_split_mixed`` warning (possible
    redundancy).

    For purely guarded groups over total constructors, each guard predicate
    (by syntactic key) must appear in both positive and negative polarity.
    """
    # Partial constructor suppression: the undefined case is determined by
    # strict error propagation, so one-sided guards are semantically correct.
    con_fn = spec.signature.functions.get(con_name)
    if con_fn is not None and con_fn.totality != Totality.TOTAL:
        return

    unguarded = [r for r in records if not r.guards]
    guarded = [r for r in records if r.guards]

    if unguarded:
        # Universal axiom covers all inputs — skip case split check.
        # But warn if the group also has guarded axioms (redundancy).
        if guarded:
            diagnostics.append(
                Diagnostic(
                    check="case_split_mixed",
                    severity=Severity.WARNING,
                    axiom=None,
                    message=(
                        f"'{obs_name}' over '{con_name}': group has both "
                        f"guarded and unguarded axioms (possible redundancy)"
                    ),
                    path=None,
                )
            )
        return

    # Build map: guard_key → set of polarities seen
    guard_groups: dict[tuple[str, tuple[str, ...]], set[str]] = {}
    for rec in guarded:
        for guard in rec.guards:
            gk = _guard_key(guard)
            if gk not in guard_groups:
                guard_groups[gk] = set()
            guard_groups[gk].add(guard.polarity)

    for (pred_name, _arg_key), polarities in guard_groups.items():
        if polarities == {"+"}:
            diagnostics.append(
                Diagnostic(
                    check="case_split_incomplete",
                    severity=Severity.WARNING,
                    axiom=None,
                    message=(
                        f"'{obs_name}' over '{con_name}': has '{pred_name}' "
                        f"positive guard but missing negative (miss branch)"
                    ),
                    path=None,
                )
            )
        elif polarities == {"-"}:
            diagnostics.append(
                Diagnostic(
                    check="case_split_incomplete",
                    severity=Severity.WARNING,
                    axiom=None,
                    message=(
                        f"'{obs_name}' over '{con_name}': has '{pred_name}' "
                        f"negative guard but missing positive (hit branch)"
                    ),
                    path=None,
                )
            )
        # {"+", "-"} — complete, no diagnostic


def _check_case_splits(spec: Spec, index: AxiomIndex) -> list[Diagnostic]:
    """Detect incomplete predicate-based case splits.

    For each (observer, constructor) group with predicate guards,
    verifies both polarities are present. Uses syntactic matching
    on guard predicate name and argument variable names.

    Also reports coverage: how many axioms/pairs were checkable.
    """
    diagnostics: list[Diagnostic] = []

    # Group by (observer_name, constructor_name).
    # The observer is rec.constrained.name; the constructor is extracted
    # from the body's LHS structure.
    groups: dict[tuple[str, str], list[AxiomRecord]] = {}
    for rec in index.records:
        if rec.constrained is None:
            continue
        constructor = _extract_constructor(rec)
        if constructor is None:
            continue
        key = (rec.constrained.name, constructor)
        if key not in groups:
            groups[key] = []
        groups[key].append(rec)

    # Check each group
    for (obs_name, con_name), records in groups.items():
        _check_group(obs_name, con_name, records, spec, diagnostics)

    # Coverage report
    total_axioms = len(spec.axioms)
    decomposed = sum(1 for rec in index.records if rec.constrained is not None)
    grouped = sum(len(recs) for recs in groups.values())
    invisible = total_axioms - decomposed
    checkable_pairs = len(groups)

    diagnostics.append(
        Diagnostic(
            check="case_split_coverage",
            severity=Severity.INFO,
            axiom=None,
            message=(
                f"Case split check covered {grouped}/{total_axioms} axioms "
                f"across {checkable_pairs} observer×constructor pairs; "
                f"{invisible} axioms not decomposable"
            ),
            path=None,
        )
    )

    return diagnostics
