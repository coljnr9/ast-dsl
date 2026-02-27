"""Tests for alspec.analysis — axiom decomposition and AxiomIndex.

Each test builds a basis spec (or the bug tracker example), decomposes
every relevant axiom, and asserts the structural fields match the
expected decomposition from the task specification.
"""

from __future__ import annotations

import pytest

from alspec.analysis import (
    AxiomIndex,
    AxiomRecord,
    ConstrainedSymbol,
    Guard,
    audit_spec,
    decompose_axiom,
)
from alspec.basis import (
    ALL_BASIS_SPECS,
    finite_map_spec,
    nat_spec,
    partial_order_spec,
    stack_spec,
)
from alspec.examples import bug_tracker_spec
from alspec.helpers import app, const, eq, forall, iff, var
from alspec.spec import Axiom
from alspec.terms import (
    Biconditional,
    Equation,
    FnApp,
    Implication,
    Negation,
    PredApp,
    Var,
)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _record_by_label(index: AxiomIndex, label: str) -> AxiomRecord:
    """Return the AxiomRecord with the given label, failing fast if absent."""
    for rec in index.records:
        if rec.label == label:
            return rec
    raise KeyError(f"No record with label {label!r}")


# ─────────────────────────────────────────────────────────────────────────────
# stack_spec — 4 axioms
# ─────────────────────────────────────────────────────────────────────────────


class TestStackSpec:
    @pytest.fixture(autouse=True)
    def _index(self) -> None:
        self.index = AxiomIndex.from_spec(stack_spec())

    def test_record_count(self) -> None:
        assert len(self.index.records) == 4

    def test_pop_push(self) -> None:
        rec = _record_by_label(self.index, "pop_push")

        # variables: (S:Stack, e:Elem) — SortRef is a str NewType
        assert len(rec.variables) == 2
        assert rec.variables[0].name == "S"
        assert rec.variables[0].sort == "Stack"
        assert rec.variables[1].name == "e"
        assert rec.variables[1].sort == "Elem"

        # guards: none
        assert rec.guards == ()

        # constrained: pop (function)
        assert rec.constrained == ConstrainedSymbol("pop", "function")

        # equation_rhs: Var("S", Stack)  — the RHS of pop(push(S,e)) = S
        assert isinstance(rec.equation_rhs, Var)
        assert rec.equation_rhs.name == "S"

        # referenced symbols
        assert rec.referenced_fns == {"pop", "push"}
        assert rec.referenced_preds == set()

    def test_top_push(self) -> None:
        rec = _record_by_label(self.index, "top_push")

        assert len(rec.variables) == 2
        assert rec.variables[0].name == "S"
        assert rec.variables[1].name == "e"
        assert rec.guards == ()
        assert rec.constrained == ConstrainedSymbol("top", "function")

        # equation_rhs: Var("e", Elem)
        assert isinstance(rec.equation_rhs, Var)
        assert rec.equation_rhs.name == "e"

        assert rec.referenced_fns == {"top", "push"}
        assert rec.referenced_preds == set()

    def test_empty_new(self) -> None:
        rec = _record_by_label(self.index, "empty_new")

        # No quantifier — empty_new is a bare PredApp in basis.py
        assert rec.variables == ()
        assert rec.guards == ()
        assert rec.constrained == ConstrainedSymbol("empty", "predicate")
        assert rec.equation_rhs is None

        assert rec.referenced_fns == {"new"}
        assert rec.referenced_preds == {"empty"}

    def test_not_empty_push(self) -> None:
        rec = _record_by_label(self.index, "not_empty_push")

        assert len(rec.variables) == 2
        assert rec.guards == ()
        # Negation(PredApp("empty", ...)) → constrained = empty predicate
        assert rec.constrained == ConstrainedSymbol("empty", "predicate")
        assert rec.equation_rhs is None

        assert rec.referenced_fns == {"push"}
        assert rec.referenced_preds == {"empty"}

    def test_by_constrained_empty(self) -> None:
        # "empty" predicate has 2 axioms (empty_new, not_empty_push)
        assert "empty" in self.index.by_constrained
        labels = {r.label for r in self.index.by_constrained["empty"]}
        assert labels == {"empty_new", "not_empty_push"}

    def test_all_referenced_fns(self) -> None:
        assert {"pop", "push", "top", "new"} <= self.index.all_referenced_fns

    def test_all_referenced_preds(self) -> None:
        assert self.index.all_referenced_preds == {"empty"}


# ─────────────────────────────────────────────────────────────────────────────
# finite_map_spec — 4 axioms
# ─────────────────────────────────────────────────────────────────────────────


class TestFiniteMapSpec:
    @pytest.fixture(autouse=True)
    def _index(self) -> None:
        self.spec = finite_map_spec()
        self.index = AxiomIndex.from_spec(self.spec)

    def test_record_count(self) -> None:
        assert len(self.index.records) == 5

    def test_lookup_update_hit(self) -> None:
        rec = _record_by_label(self.index, "lookup_update_hit")

        # variables: (M:Map, k1:Key, k2:Key, v:Val)
        assert len(rec.variables) == 4
        var_names = [v.name for v in rec.variables]
        assert var_names == ["M", "k1", "k2", "v"]

        # guards: (Guard("eq_key", "+", (k1, k2)),)
        assert len(rec.guards) == 1
        g = rec.guards[0]
        assert g.pred_name == "eq_key"
        assert g.polarity == "+"
        assert len(g.args) == 2
        assert isinstance(g.args[0], Var) and g.args[0].name == "k1"
        assert isinstance(g.args[1], Var) and g.args[1].name == "k2"

        # constrained: lookup (function)
        assert rec.constrained == ConstrainedSymbol("lookup", "function")

        # equation_rhs: Var("v", Val)
        assert isinstance(rec.equation_rhs, Var)
        assert rec.equation_rhs.name == "v"

        assert rec.referenced_fns == {"lookup", "update"}
        assert rec.referenced_preds == {"eq_key"}

    def test_lookup_update_miss(self) -> None:
        rec = _record_by_label(self.index, "lookup_update_miss")

        assert len(rec.variables) == 4

        # guards: (Guard("eq_key", "-", (k1, k2)),)
        assert len(rec.guards) == 1
        g = rec.guards[0]
        assert g.pred_name == "eq_key"
        assert g.polarity == "-"
        assert isinstance(g.args[0], Var) and g.args[0].name == "k1"
        assert isinstance(g.args[1], Var) and g.args[1].name == "k2"

        assert rec.constrained == ConstrainedSymbol("lookup", "function")

        # equation_rhs: FnApp("lookup", ...)
        assert isinstance(rec.equation_rhs, FnApp)
        assert rec.equation_rhs.fn_name == "lookup"

        assert rec.referenced_fns == {"lookup", "update"}
        assert rec.referenced_preds == {"eq_key"}

    def test_eq_key_refl(self) -> None:
        rec = _record_by_label(self.index, "eq_key_refl")

        # variables: (k:Key,)
        assert len(rec.variables) == 1
        assert rec.variables[0].name == "k"

        assert rec.guards == ()
        assert rec.constrained == ConstrainedSymbol("eq_key", "predicate")
        assert rec.equation_rhs is None

        # Bare PredApp: no function apps, only eq_key predicate
        assert rec.referenced_fns == set()
        assert rec.referenced_preds == {"eq_key"}

    def test_eq_key_sym(self) -> None:
        rec = _record_by_label(self.index, "eq_key_sym")

        # variables: (k1:Key, k2:Key)
        assert len(rec.variables) == 2
        assert rec.variables[0].name == "k1"
        assert rec.variables[1].name == "k2"

        # guards: (Guard("eq_key", "+", (k1, k2)),)
        assert len(rec.guards) == 1
        g = rec.guards[0]
        assert g.pred_name == "eq_key"
        assert g.polarity == "+"

        # body: PredApp("eq_key", (k2, k1))
        assert isinstance(rec.body, PredApp)
        assert rec.body.pred_name == "eq_key"

        assert rec.constrained == ConstrainedSymbol("eq_key", "predicate")
        assert rec.equation_rhs is None

        assert rec.referenced_fns == set()
        assert rec.referenced_preds == {"eq_key"}

    def test_by_constrained_lookup(self) -> None:
        labels = {r.label for r in self.index.by_constrained["lookup"]}
        assert labels == {"lookup_update_hit", "lookup_update_miss"}

    def test_by_constrained_eq_key(self) -> None:
        labels = {r.label for r in self.index.by_constrained["eq_key"]}
        assert labels == {"eq_key_refl", "eq_key_sym"}


# ─────────────────────────────────────────────────────────────────────────────
# partial_order_spec — 3 axioms
# Edge cases: Conjunction antecedent stops guard extraction
# ─────────────────────────────────────────────────────────────────────────────


class TestPartialOrderSpec:
    @pytest.fixture(autouse=True)
    def _index(self) -> None:
        self.index = AxiomIndex.from_spec(partial_order_spec())

    def test_record_count(self) -> None:
        assert len(self.index.records) == 3

    def test_reflexivity(self) -> None:
        rec = _record_by_label(self.index, "reflexivity")

        assert len(rec.variables) == 1
        assert rec.variables[0].name == "x"
        assert rec.guards == ()
        assert rec.constrained == ConstrainedSymbol("leq", "predicate")
        assert rec.equation_rhs is None
        assert rec.referenced_preds == {"leq"}
        assert rec.referenced_fns == set()

    def test_antisymmetry_complex_antecedent(self) -> None:
        """Conjunction antecedent → no guards extracted, body is full Implication."""
        rec = _record_by_label(self.index, "antisymmetry")

        assert len(rec.variables) == 2
        # No guards: Conjunction is not a simple PredApp
        assert rec.guards == ()

        # Body is the full Implication (Conjunction(...) ⇒ Equation(...))
        assert isinstance(rec.body, Implication)

        # constrained: None — Implication body falls through to catch-all
        assert rec.constrained is None
        assert rec.equation_rhs is None

        assert rec.referenced_preds == {"leq"}

    def test_transitivity_complex_antecedent(self) -> None:
        """Same edge case as antisymmetry."""
        rec = _record_by_label(self.index, "transitivity")

        assert rec.guards == ()
        assert isinstance(rec.body, Implication)
        assert rec.constrained is None
        assert rec.equation_rhs is None

        assert rec.referenced_preds == {"leq"}

    def test_leq_not_in_by_constrained_for_property_axioms(self) -> None:
        """antisymmetry and transitivity produce no constrained symbol."""
        # Only reflexivity contributes to by_constrained["leq"]
        assert "leq" in self.index.by_constrained
        labels = {r.label for r in self.index.by_constrained["leq"]}
        assert "antisymmetry" not in labels
        assert "transitivity" not in labels
        assert "reflexivity" in labels


# ─────────────────────────────────────────────────────────────────────────────
# nat_spec — leq_suc_suc
# Guard predicate and constrained predicate are the same symbol
# ─────────────────────────────────────────────────────────────────────────────


class TestNatSpecLeqSucSuc:
    @pytest.fixture(autouse=True)
    def _index(self) -> None:
        self.index = AxiomIndex.from_spec(nat_spec())

    def test_leq_suc_suc(self) -> None:
        rec = _record_by_label(self.index, "leq_suc_suc")

        # variables: (x:Nat, y:Nat)
        assert len(rec.variables) == 2
        assert rec.variables[0].name == "x"
        assert rec.variables[1].name == "y"

        # guards: (Guard("leq", "+", (suc(x), suc(y))),)
        assert len(rec.guards) == 1
        g = rec.guards[0]
        assert g.pred_name == "leq"
        assert g.polarity == "+"
        assert len(g.args) == 2
        # args are FnApp("suc", (Var("x", Nat),)) and FnApp("suc", (Var("y", Nat),))
        assert isinstance(g.args[0], FnApp) and g.args[0].fn_name == "suc"
        assert isinstance(g.args[1], FnApp) and g.args[1].fn_name == "suc"

        # body: PredApp("leq", (x, y)) — the consequent after guard extraction
        assert isinstance(rec.body, PredApp)
        assert rec.body.pred_name == "leq"

        # constrained: leq (predicate)
        assert rec.constrained == ConstrainedSymbol("leq", "predicate")
        assert rec.equation_rhs is None

        assert rec.referenced_preds == {"leq"}
        assert "suc" in rec.referenced_fns

    def test_lt_suc(self) -> None:
        """lt_suc: PredApp guard → constrained = lt predicate."""
        rec = _record_by_label(self.index, "lt_suc")
        assert len(rec.guards) == 1
        assert rec.guards[0].pred_name == "lt"
        assert rec.guards[0].polarity == "+"
        assert rec.constrained == ConstrainedSymbol("lt", "predicate")

    def test_leq_zero_no_guards(self) -> None:
        """leq_zero: bare PredApp, no guards."""
        rec = _record_by_label(self.index, "leq_zero")
        assert rec.guards == ()
        assert rec.constrained == ConstrainedSymbol("leq", "predicate")

    def test_lt_zero_negation(self) -> None:
        """lt_zero: Negation(PredApp) — constrained = lt predicate."""
        rec = _record_by_label(self.index, "lt_zero")
        assert rec.guards == ()
        assert rec.constrained == ConstrainedSymbol("lt", "predicate")

    def test_add_zero(self) -> None:
        """add_zero: simple equation, constrained = add function."""
        rec = _record_by_label(self.index, "add_zero")
        assert rec.guards == ()
        assert rec.constrained == ConstrainedSymbol("add", "function")
        assert isinstance(rec.equation_rhs, Var)

    def test_add_suc(self) -> None:
        """add_suc: simple equation, constrained = add function."""
        rec = _record_by_label(self.index, "add_suc")
        assert rec.guards == ()
        assert rec.constrained == ConstrainedSymbol("add", "function")
        assert isinstance(rec.equation_rhs, FnApp)
        assert rec.equation_rhs.fn_name == "suc"


# ─────────────────────────────────────────────────────────────────────────────
# bug_tracker_spec (from alspec.examples)
# Tests a subset of axioms that cover all interesting structural patterns
# ─────────────────────────────────────────────────────────────────────────────


class TestBugTrackerSpec:
    @pytest.fixture(autouse=True)
    def _index(self) -> None:
        self.index = AxiomIndex.from_spec(bug_tracker_spec())

    def test_get_severity_create_hit_guarded_equation(self) -> None:
        """get_severity_create_hit: eq_id guard + function equation."""
        rec = _record_by_label(self.index, "get_severity_create_hit")

        assert len(rec.guards) == 1
        g = rec.guards[0]
        assert g.pred_name == "eq_id"
        assert g.polarity == "+"

        assert rec.constrained == ConstrainedSymbol("get_severity", "function")

        # equation_rhs: FnApp("classify", (t, b))
        assert isinstance(rec.equation_rhs, FnApp)
        assert rec.equation_rhs.fn_name == "classify"

        assert "get_severity" in rec.referenced_fns
        assert "create_ticket" in rec.referenced_fns
        assert "classify" in rec.referenced_fns
        assert "eq_id" in rec.referenced_preds

    def test_get_severity_resolve_universal_preservation(self) -> None:
        """get_severity_resolve: no guard, universal preservation equation."""
        rec = _record_by_label(self.index, "get_severity_resolve")

        assert rec.guards == ()
        assert rec.constrained == ConstrainedSymbol("get_severity", "function")

        # equation_rhs: FnApp("get_severity", ...)
        assert isinstance(rec.equation_rhs, FnApp)
        assert rec.equation_rhs.fn_name == "get_severity"

    def test_get_status_create_hit_guarded_equation(self) -> None:
        """get_status_create_hit: eq_id guard + status = open equation."""
        rec = _record_by_label(self.index, "get_status_create_hit")

        assert len(rec.guards) == 1
        assert rec.guards[0].pred_name == "eq_id"
        assert rec.guards[0].polarity == "+"

        assert rec.constrained == ConstrainedSymbol("get_status", "function")

        # equation_rhs: FnApp("open", ())
        assert isinstance(rec.equation_rhs, FnApp)
        assert rec.equation_rhs.fn_name == "open"

    def test_get_status_resolve_hit_nested_guards(self) -> None:
        """get_status_resolve_hit: eq_id guard + has_ticket guard (nested implication)."""
        rec = _record_by_label(self.index, "get_status_resolve_hit")

        # Two guards: eq_id(k, k2) then has_ticket(s, k)
        assert len(rec.guards) == 2
        assert rec.guards[0].pred_name == "eq_id"
        assert rec.guards[0].polarity == "+"
        assert rec.guards[1].pred_name == "has_ticket"
        assert rec.guards[1].polarity == "+"

        # body after both guards: Equation(get_status(...), resolved)
        assert isinstance(rec.body, Equation)
        assert rec.constrained == ConstrainedSymbol("get_status", "function")

        # equation_rhs: FnApp("resolved", ())
        assert isinstance(rec.equation_rhs, FnApp)
        assert rec.equation_rhs.fn_name == "resolved"

    def test_is_critical_create_hit_biconditional(self) -> None:
        """is_critical_create_hit: eq_id guard + Biconditional body with PredApp LHS."""
        rec = _record_by_label(self.index, "is_critical_create_hit")

        assert len(rec.guards) == 1
        assert rec.guards[0].pred_name == "eq_id"
        assert rec.guards[0].polarity == "+"

        # body: Biconditional(PredApp("is_critical", ...), Equation(...))
        assert isinstance(rec.body, Biconditional)
        assert rec.constrained == ConstrainedSymbol("is_critical", "predicate")
        assert rec.equation_rhs is None

    def test_is_critical_resolve_biconditional_no_guard(self) -> None:
        """is_critical_resolve: no guard, universal Biconditional."""
        rec = _record_by_label(self.index, "is_critical_resolve")

        assert rec.guards == ()
        assert isinstance(rec.body, Biconditional)
        assert rec.constrained == ConstrainedSymbol("is_critical", "predicate")
        assert rec.equation_rhs is None

    def test_has_ticket_empty_negation(self) -> None:
        """has_ticket_empty: Negation(PredApp) → constrained = has_ticket predicate."""
        rec = _record_by_label(self.index, "has_ticket_empty")
        assert rec.guards == ()
        assert rec.constrained == ConstrainedSymbol("has_ticket", "predicate")
        assert rec.equation_rhs is None

    def test_has_ticket_create_miss_complex_body(self) -> None:
        """has_ticket_create_miss: eq_id(-) guard + Biconditional body."""
        rec = _record_by_label(self.index, "has_ticket_create_miss")
        assert len(rec.guards) == 1
        assert rec.guards[0].polarity == "-"
        assert isinstance(rec.body, Biconditional)
        assert rec.constrained == ConstrainedSymbol("has_ticket", "predicate")

    def test_all_referenced_preds_include_eq_id(self) -> None:
        assert "eq_id" in self.index.all_referenced_preds
        assert "has_ticket" in self.index.all_referenced_preds
        assert "is_critical" in self.index.all_referenced_preds


# ─────────────────────────────────────────────────────────────────────────────
# AxiomIndex structural invariants
# ─────────────────────────────────────────────────────────────────────────────


class TestAxiomIndexInvariants:
    def test_empty_spec_index(self) -> None:
        """An empty spec produces a valid empty index."""
        from alspec.signature import Signature
        from alspec.spec import Spec
        from alspec.sorts import AtomicSort, SortRef

        spec = Spec(
            name="Empty",
            signature=Signature(
                sorts={"X": AtomicSort(SortRef("X"))},
                functions={},
                predicates={},
            ),
            axioms=(),
        )
        idx = AxiomIndex.from_spec(spec)
        assert idx.records == ()
        assert dict(idx.by_constrained) == {}
        assert idx.all_referenced_fns == frozenset()
        assert idx.all_referenced_preds == frozenset()

    def test_by_constrained_keys_match_constrained_names(self) -> None:
        """Every key in by_constrained is the .name of some ConstrainedSymbol."""
        idx = AxiomIndex.from_spec(finite_map_spec())
        for key, recs in idx.by_constrained.items():
            for rec in recs:
                assert rec.constrained is not None
                assert rec.constrained.name == key

    def test_all_fns_is_union_of_record_fns(self) -> None:
        idx = AxiomIndex.from_spec(nat_spec())
        expected: frozenset[str] = frozenset()
        for rec in idx.records:
            expected = expected | rec.referenced_fns
        assert idx.all_referenced_fns == expected

    def test_all_preds_is_union_of_record_preds(self) -> None:
        idx = AxiomIndex.from_spec(nat_spec())
        expected: frozenset[str] = frozenset()
        for rec in idx.records:
            expected = expected | rec.referenced_preds
        assert idx.all_referenced_preds == expected

    def test_records_are_immutable(self) -> None:
        """AxiomRecord and Guard are frozen dataclasses."""
        import dataclasses

        assert AxiomRecord.__dataclass_params__.frozen  # type: ignore[attr-defined]
        assert Guard.__dataclass_params__.frozen  # type: ignore[attr-defined]
        assert ConstrainedSymbol.__dataclass_params__.frozen  # type: ignore[attr-defined]


# ─────────────────────────────────────────────────────────────────────────────
# decompose_axiom — standalone function
# ─────────────────────────────────────────────────────────────────────────────


class TestDecomposeAxiomStandalone:
    def test_bare_predapp_axiom(self) -> None:
        """A bare PredApp formula (no quantifier) decomposed correctly."""
        from alspec.spec import Axiom

        k = var("k", "Key")
        axiom = Axiom(
            label="test_pred",
            formula=PredApp("some_pred", (k,)),
        )
        rec = decompose_axiom(axiom)
        assert rec.label == "test_pred"
        assert rec.variables == ()
        assert rec.guards == ()
        assert rec.constrained == ConstrainedSymbol("some_pred", "predicate")
        assert rec.equation_rhs is None
        assert rec.referenced_preds == {"some_pred"}

    def test_symbol_collection_includes_guard_symbols(self) -> None:
        """Guards' predicate names appear in referenced_preds even after extraction."""
        from alspec.spec import Axiom
        from alspec.terms import Equation

        k1 = var("k1", "Key")
        k2 = var("k2", "Key")
        v = var("v", "Val")
        axiom = Axiom(
            label="guard_test",
            formula=Implication(
                PredApp("my_guard", (k1, k2)),
                Equation(
                    FnApp("my_fn", (k1,)),
                    v,
                ),
            ),
        )
        rec = decompose_axiom(axiom)
        assert len(rec.guards) == 1
        assert rec.guards[0].pred_name == "my_guard"
        # Guard symbol must appear in referenced_preds
        assert "my_guard" in rec.referenced_preds
        assert "my_fn" in rec.referenced_fns

    def test_definedness_body_identifies_fn(self) -> None:
        """Definedness(FnApp(...)) body → constrained = that function."""
        from alspec.spec import Axiom
        from alspec.terms import Definedness

        x = var("x", "Nat")
        axiom = Axiom(
            label="def_pre",
            formula=Definedness(term=FnApp("pre", (x,))),
        )
        rec = decompose_axiom(axiom)
        assert rec.constrained == ConstrainedSymbol("pre", "function")
        assert rec.equation_rhs is None
        assert "pre" in rec.referenced_fns


# ─────────────────────────────────────────────────────────────────────────────
# Phase 2: Adequacy checks — audit_spec
# ─────────────────────────────────────────────────────────────────────────────


class TestAuditSpecBasisNoFalsePositives:
    """Every hand-written basis spec must produce zero unconstrained fn/pred warnings."""

    @pytest.mark.parametrize("spec_fn", __import__("alspec.basis", fromlist=["ALL_BASIS_SPECS"]).ALL_BASIS_SPECS, ids=lambda f: f.__name__)
    def test_basis_specs_no_unconstrained(self, spec_fn) -> None:  # type: ignore[no-untyped-def]
        from alspec.analysis import audit_spec

        spec = spec_fn()
        diagnostics = audit_spec(spec)
        unconstrained = [
            d for d in diagnostics
            if d.check in ("unconstrained_fn", "unconstrained_pred")
        ]
        assert unconstrained == [], f"Unexpected unconstrained symbols in {spec.name}: {unconstrained}"


class TestAuditSpecUnconstrainedFunction:
    """audit_spec detects functions that appear in no axiom."""

    def test_unconstrained_function_detected(self) -> None:
        from alspec.analysis import audit_spec
        from alspec.helpers import atomic, fn
        from alspec.signature import Signature
        from alspec.spec import Spec

        sig = Signature(
            sorts={"Nat": atomic("Nat")},
            functions={
                "zero": fn("zero", [], "Nat"),
                "suc": fn("suc", [("n", "Nat")], "Nat"),
                "unused_fn": fn("unused_fn", [("n", "Nat")], "Nat"),  # never referenced
            },
            predicates={},
        )
        x = var("x", "Nat")
        spec = Spec(
            name="TestUnconstrained",
            signature=sig,
            axioms=(
                Axiom("trivial", forall([x], eq(app("suc", x), app("suc", x)))),
            ),
        )
        diagnostics = audit_spec(spec)
        unconstrained_fns = [d for d in diagnostics if d.check == "unconstrained_fn"]

        # Both 'zero' and 'unused_fn' are absent from the single axiom.
        assert len(unconstrained_fns) == 2
        names = {d.message.split("'")[1] for d in unconstrained_fns}
        assert "unused_fn" in names
        assert "zero" in names

    def test_constrained_function_not_flagged(self) -> None:
        """A function that IS referenced produces no unconstrained_fn diagnostic."""
        from alspec.analysis import audit_spec
        from alspec.helpers import atomic, fn
        from alspec.signature import Signature
        from alspec.spec import Spec

        sig = Signature(
            sorts={"Nat": atomic("Nat")},
            functions={"zero": fn("zero", [], "Nat")},
            predicates={},
        )
        spec = Spec(
            name="ZeroConstrained",
            signature=sig,
            axioms=(Axiom("zero_def", eq(const("zero"), const("zero"))),),
        )
        diagnostics = audit_spec(spec)
        fn_diags = [d for d in diagnostics if d.check == "unconstrained_fn"]
        assert fn_diags == []


class TestAuditSpecUnconstrainedPredicate:
    """audit_spec detects predicates that appear in no axiom."""

    def test_unconstrained_predicate_detected(self) -> None:
        from alspec.analysis import audit_spec
        from alspec.helpers import atomic, fn, pred
        from alspec.signature import Signature
        from alspec.spec import Spec

        sig = Signature(
            sorts={"S": atomic("S")},
            functions={"c": fn("c", [], "S")},
            predicates={
                "used_pred": pred("used_pred", [("x", "S")]),
                "unused_pred": pred("unused_pred", [("x", "S")]),
            },
        )
        x = var("x", "S")
        spec = Spec(
            name="TestUnconstrainedPred",
            signature=sig,
            axioms=(
                Axiom("use_pred", forall([x], PredApp("used_pred", (x,)))),
            ),
        )
        diagnostics = audit_spec(spec)
        unconstrained_preds = [d for d in diagnostics if d.check == "unconstrained_pred"]
        assert len(unconstrained_preds) == 1
        assert "unused_pred" in unconstrained_preds[0].message

    def test_no_predicates_no_warnings(self) -> None:
        """A spec with no predicates cannot have unconstrained_pred warnings."""
        from alspec.analysis import audit_spec
        from alspec.helpers import atomic, fn
        from alspec.signature import Signature
        from alspec.spec import Spec

        sig = Signature(
            sorts={"Nat": atomic("Nat")},
            functions={"zero": fn("zero", [], "Nat")},
            predicates={},
        )
        spec = Spec(
            name="NoPreds",
            signature=sig,
            axioms=(Axiom("z", eq(const("zero"), const("zero"))),),
        )
        diagnostics = audit_spec(spec)
        pred_diags = [d for d in diagnostics if d.check == "unconstrained_pred"]
        assert pred_diags == []


class TestAuditSpecOrphanSort:
    """audit_spec detects sorts not referenced by any function or predicate profile."""

    def test_orphan_sort_detected(self) -> None:
        from alspec.analysis import audit_spec
        from alspec.helpers import atomic, fn
        from alspec.signature import Signature
        from alspec.spec import Spec

        sig = Signature(
            sorts={
                "Nat": atomic("Nat"),
                "Phantom": atomic("Phantom"),  # no function or pred uses it
            },
            functions={"zero": fn("zero", [], "Nat")},
            predicates={},
        )
        spec = Spec(name="TestOrphan", signature=sig, axioms=())
        diagnostics = audit_spec(spec)
        orphans = [d for d in diagnostics if d.check == "orphan_sort"]
        assert len(orphans) == 1
        assert "Phantom" in orphans[0].message

    def test_sort_in_param_is_not_orphaned(self) -> None:
        """A sort used only in a function param is not flagged."""
        from alspec.analysis import audit_spec
        from alspec.helpers import atomic, fn
        from alspec.signature import Signature
        from alspec.spec import Spec

        sig = Signature(
            sorts={
                "Key": atomic("Key"),
                "Val": atomic("Val"),
            },
            functions={
                # Key appears as param, Val as result
                "get": fn("get", [("k", "Key")], "Val"),
            },
            predicates={},
        )
        spec = Spec(name="NoOrphans", signature=sig, axioms=())
        diagnostics = audit_spec(spec)
        orphans = [d for d in diagnostics if d.check == "orphan_sort"]
        assert orphans == []

    def test_sort_used_only_in_pred_param_not_orphaned(self) -> None:
        """A sort used only in a predicate param is not flagged."""
        from alspec.analysis import audit_spec
        from alspec.helpers import atomic, pred
        from alspec.signature import Signature
        from alspec.spec import Spec

        sig = Signature(
            sorts={"Elem": atomic("Elem")},
            functions={},
            predicates={"has": pred("has", [("x", "Elem")])},
        )
        spec = Spec(name="PredSort", signature=sig, axioms=())
        diagnostics = audit_spec(spec)
        orphans = [d for d in diagnostics if d.check == "orphan_sort"]
        assert orphans == []


class TestAuditFlagInScoreSpec:
    """The audit flag in score_spec correctly gates audit warnings."""

    def _make_unconstrained_spec(self) -> "Spec":
        from alspec.helpers import atomic, fn
        from alspec.signature import Signature
        from alspec.spec import Spec

        sig = Signature(
            sorts={"Nat": atomic("Nat")},
            functions={
                "zero": fn("zero", [], "Nat"),
                "suc": fn("suc", [("n", "Nat")], "Nat"),
                "unused_fn": fn("unused_fn", [("n", "Nat")], "Nat"),
            },
            predicates={},
        )
        x = var("x", "Nat")
        return Spec(
            name="TestUnconstrained",
            signature=sig,
            axioms=(
                Axiom("trivial", forall([x], eq(app("suc", x), app("suc", x)))),
            ),
        )

    def test_audit_false_produces_no_audit_warnings(self) -> None:
        from alspec.score import score_spec

        spec = self._make_unconstrained_spec()
        score = score_spec(spec, audit=False)
        assert score.warning_count == 0

    def test_audit_true_produces_audit_warnings(self) -> None:
        from alspec.score import score_spec

        spec = self._make_unconstrained_spec()
        score = score_spec(spec, audit=True)
        assert score.warning_count > 0

    def test_audit_does_not_affect_well_formed(self) -> None:
        from alspec.score import score_spec

        spec = self._make_unconstrained_spec()
        score_without = score_spec(spec, audit=False)
        score_with = score_spec(spec, audit=True)
        assert score_without.well_formed == score_with.well_formed

    def test_audit_does_not_affect_health(self) -> None:
        from alspec.score import score_spec

        spec = self._make_unconstrained_spec()
        score_without = score_spec(spec, audit=False)
        score_with = score_spec(spec, audit=True)
        assert score_without.health == score_with.health

    def test_audit_diagnostics_have_correct_checks(self) -> None:
        from alspec.check import Severity
        from alspec.score import score_spec

        spec = self._make_unconstrained_spec()
        score = score_spec(spec, audit=True)
        audit_diags = [
            d for d in score.diagnostics
            if d.check in ("unconstrained_fn", "unconstrained_pred", "orphan_sort")
        ]
        assert all(d.severity == Severity.WARNING for d in audit_diags)
        assert all(d.axiom is None for d in audit_diags)

# ──────────────────────────────────────────────────────────────────────────────
# Phase 3: Definedness Witness — audit_spec.check == "unwitnessed_partial"
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("spec_fn", ALL_BASIS_SPECS, ids=lambda f: f.__name__)
def test_basis_specs_no_unwitnessed_partials(spec_fn) -> None:  # type: ignore[no-untyped-def]
    """Every partial function in the basis library must be witnessed.

    Concrete witnesses:
    - stack_spec:       pop ← pop_push (RHS = Var), top ← top_push (RHS = Var)
    - list_spec:        hd  ← hd_cons  (RHS = Var), tl  ← tl_cons  (RHS = Var)
    - finite_map_spec:  lookup ← lookup_update_hit (RHS = Var)
    """
    spec = spec_fn()
    diagnostics = audit_spec(spec)
    unwitnessed = [d for d in diagnostics if d.check == "unwitnessed_partial"]
    assert unwitnessed == [], f"Unexpected unwitnessed partials in {spec.name}: {unwitnessed}"


class TestUnwitnessedPartialDetected:
    """A partial function whose only equations have partial RHS must be flagged."""

    def test_both_partials_flagged(self) -> None:
        """f(x) = g(x) — both partial, vacuously satisfied by both undefined."""
        from alspec.helpers import atomic, fn
        from alspec.signature import Signature
        from alspec.spec import Spec

        sig = Signature(
            sorts={"S": atomic("S")},
            functions={
                "c": fn("c", [], "S"),
                "f": fn("f", [("x", "S")], "S", total=False),
                "g": fn("g", [("x", "S")], "S", total=False),
            },
            predicates={},
        )
        x = var("x", "S")
        spec = Spec(
            name="TestUnwitnessed",
            signature=sig,
            axioms=(
                # f(x) = g(x) — RHS is partial, vacuously satisfied
                Axiom("f_eq_g", forall([x], eq(app("f", x), app("g", x)))),
            ),
        )
        diagnostics = audit_spec(spec)
        unwitnessed = [d for d in diagnostics if d.check == "unwitnessed_partial"]
        names = {d.message.split("'")[1] for d in unwitnessed}
        assert "f" in names  # f's only equation has partial RHS
        assert "g" in names  # g is never on the LHS — unconstrained AND unwitnessed


class TestWitnessedByTotalRHS:
    """A partial function with a total-RHS equation must NOT be flagged."""

    def test_total_constant_rhs_witnesses(self) -> None:
        """f(c) = c — RHS is total constant, witnesses f."""
        from alspec.helpers import atomic, fn
        from alspec.signature import Signature
        from alspec.spec import Spec

        sig = Signature(
            sorts={"S": atomic("S")},
            functions={
                "c": fn("c", [], "S"),
                "f": fn("f", [("x", "S")], "S", total=False),
            },
            predicates={},
        )
        spec = Spec(
            name="TestWitnessed",
            signature=sig,
            axioms=(
                # f(c) = c — RHS is total constant, definitely defined
                Axiom("f_c", eq(app("f", const("c")), const("c"))),
            ),
        )
        diagnostics = audit_spec(spec)
        unwitnessed = [d for d in diagnostics if d.check == "unwitnessed_partial"]
        assert unwitnessed == []

    def test_var_rhs_witnesses(self) -> None:
        """f(push(s, e)) = e — Var RHS is definitely defined, witnesses f."""
        spec = stack_spec()
        diagnostics = audit_spec(spec)
        unwitnessed = [d for d in diagnostics if d.check == "unwitnessed_partial"]
        # pop + top are both witnessed, so no unwitnessed_partial
        assert unwitnessed == []


class TestWitnessedByDefinedness:
    """A partial function with only a Definedness assertion must NOT be flagged."""

    def test_iff_definedness_witnesses(self) -> None:
        """def(f(x)) ⇔ p(x) — no equation for f, but definedness is asserted."""
        from alspec.helpers import atomic, fn, pred
        from alspec.signature import Signature
        from alspec.spec import Spec
        from alspec.terms import Definedness

        sig = Signature(
            sorts={"S": atomic("S")},
            functions={
                "c": fn("c", [], "S"),
                "f": fn("f", [("x", "S")], "S", total=False),
            },
            predicates={
                "p": pred("p", [("x", "S")]),
            },
        )
        x = var("x", "S")
        spec = Spec(
            name="TestDefWitnessed",
            signature=sig,
            axioms=(
                # def(f(x)) ⇔ p(x) — no value equation, but definedness is asserted
                Axiom(
                    "f_def",
                    forall(
                        [x],
                        iff(
                            Definedness(app("f", x)),
                            PredApp("p", (x,)),
                        ),
                    ),
                ),
            ),
        )
        diagnostics = audit_spec(spec)
        unwitnessed = [d for d in diagnostics if d.check == "unwitnessed_partial"]
        assert unwitnessed == []

    def test_negated_definedness_in_axiom_witnesses(self) -> None:
        """Even ¬def(f(...)) counts as a Definedness assertion (scanner detects the node)."""
        from alspec.helpers import atomic, fn
        from alspec.signature import Signature
        from alspec.spec import Spec
        from alspec.terms import Definedness, Negation

        sig = Signature(
            sorts={"S": atomic("S")},
            functions={
                "c": fn("c", [], "S"),
                "f": fn("f", [("x", "S")], "S", total=False),
            },
            predicates={},
        )
        k = var("k", "S")
        spec = Spec(
            name="TestNegDefWitnessed",
            signature=sig,
            axioms=(
                # ¬def(f(c)) — the finite_map pattern: explicitly undefined on empty
                Axiom(
                    "f_undef_c",
                    Negation(Definedness(app("f", const("c")))),
                ),
            ),
        )
        diagnostics = audit_spec(spec)
        unwitnessed = [d for d in diagnostics if d.check == "unwitnessed_partial"]
        assert unwitnessed == []


class TestPartialRHSDoesNotWitness:
    """An equation where the RHS is a partial function application must NOT witness."""

    def test_partial_self_equation_does_not_witness(self) -> None:
        """f(c) = f(d) — RHS is partial, does not witness."""
        from alspec.helpers import atomic, fn
        from alspec.signature import Signature
        from alspec.spec import Spec

        sig = Signature(
            sorts={"S": atomic("S"), "T": atomic("T")},
            functions={
                "c": fn("c", [], "S"),
                "d": fn("d", [], "S"),
                "f": fn("f", [("x", "S")], "T", total=False),
            },
            predicates={},
        )
        spec = Spec(
            name="TestPartialRHS",
            signature=sig,
            axioms=(
                # f(c) = f(d) — RHS is partial, does not witness
                Axiom("f_eq", eq(app("f", const("c")), app("f", const("d")))),
            ),
        )
        diagnostics = audit_spec(spec)
        unwitnessed = [d for d in diagnostics if d.check == "unwitnessed_partial"]
        assert len(unwitnessed) == 1
        assert "f" in unwitnessed[0].message

    def test_finite_map_lookup_miss_does_not_witness_alone(self) -> None:
        """Miss equation (lookup(update(M,k1,v), k2) = lookup(M, k2)) has partial RHS.

        The finite_map_spec is fully witnessed because the *hit* axiom has a
        Var RHS. This test verifies the miss axiom in isolation does not witness.
        """
        from alspec.helpers import atomic, fn, pred
        from alspec.signature import Signature
        from alspec.spec import Spec
        from alspec.terms import Negation

        k1 = var("k1", "Key")
        k2 = var("k2", "Key")
        v = var("v", "Val")
        M = var("M", "Map")

        sig = Signature(
            sorts={
                "Key": atomic("Key"),
                "Val": atomic("Val"),
                "Map": atomic("Map"),
            },
            functions={
                "empty": fn("empty", [], "Map"),
                "update": fn("update", [("M", "Map"), ("k", "Key"), ("v", "Val")], "Map"),
                "lookup": fn("lookup", [("M", "Map"), ("k", "Key")], "Val", total=False),
            },
            predicates={
                "eq_key": pred("eq_key", [("k1", "Key"), ("k2", "Key")]),
            },
        )
        spec = Spec(
            name="MapMissOnly",
            signature=sig,
            axioms=(
                # Only the miss axiom: RHS is lookup (partial), does NOT witness
                Axiom(
                    "lookup_miss_only",
                    forall(
                        [M, k1, k2, v],
                        Implication(
                            Negation(PredApp("eq_key", (k1, k2))),
                            eq(
                                app("lookup", app("update", M, k1, v), k2),
                                app("lookup", M, k2),
                            ),
                        ),
                    ),
                ),
            ),
        )
        diagnostics = audit_spec(spec)
        unwitnessed = [d for d in diagnostics if d.check == "unwitnessed_partial"]
        names = {d.message.split("'")[1] for d in unwitnessed}
        assert "lookup" in names

