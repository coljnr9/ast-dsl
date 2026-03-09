"""Tests for alspec/axiom_match.py — Axiom-to-cell matching (Phase 4)."""

import dataclasses
import importlib
import logging
import sys
from pathlib import Path


import pytest

from alspec import (
    Axiom,
    Biconditional,
    Equation,
    ExistentialQuant,
    FnApp,
    Spec,
    UniversalQuant,
    Var,
    app,
    conjunction,
    const,
    definedness,
    eq,
    fn,
    forall,
    implication,
    negation,
    pred_app,
    var,
)
from alspec.axiom_match import (
    AxiomCellMatch,
    CellCoverage,
    CoverageStatus,
    MatchKind,
    MatchReport,
    _classify_guard,
    _collect_fn_names,
    _collect_pred_names,
    _find_obs_ctor,
    _is_basis_axiom,
    _is_constructor_def,
    _peel_implications,
    _peel_quantifiers,
    _ctor_root,
    _is_distinctness_axiom,
    _has_observer_on_variable,
    _is_conclusion_definition,
    match_spec_sync,
)
from alspec.obligation import (
    CellDispatch,
    FnKind,
    FnRole,
    ObligationTable,
    PredKind,
    PredRole,
    build_obligation_table,
)


# ---------------------------------------------------------------------------
# Golden spec loader helper
# ---------------------------------------------------------------------------

GOLDEN_DIR = Path(__file__).parent.parent / "golden"


def _load_golden(stem: str):
    """Import a golden spec module by stem (filename without .py)."""
    module_path = str(GOLDEN_DIR / f"{stem}.py")
    spec = importlib.util.spec_from_file_location(stem, module_path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


# ===========================================================================
# Unit tests for helpers
# ===========================================================================


class TestPeelQuantifiers:
    def test_strips_forall(self):
        x = var("x", "Nat")
        inner = eq(app("f", x), x)
        f = forall([x], inner)
        assert _peel_quantifiers(f) is inner

    def test_strips_exists(self):
        x = var("x", "Nat")
        inner = eq(app("f", x), x)
        f = ExistentialQuant((x,), inner)
        assert _peel_quantifiers(f) is inner

    def test_nested_quantifiers(self):
        x = var("x", "Nat")
        inner = eq(app("f", x), x)
        f = forall([x], ExistentialQuant((x,), inner))
        assert _peel_quantifiers(f) is inner

    def test_no_quantifier_is_identity(self):
        x = var("x", "Nat")
        f = eq(x, x)
        assert _peel_quantifiers(f) is f


class TestPeelImplications:
    def test_single_implication(self):
        g1 = pred_app("eq_id", var("k", "K"), var("k2", "K"))
        conclusion = eq(app("f", var("x", "X")), var("x", "X"))
        f = implication(g1, conclusion)
        guards, conc = _peel_implications(f)
        assert guards == [g1]
        assert conc is conclusion

    def test_nested_implications(self):
        g1 = pred_app("eq_id", var("k", "K"), var("k2", "K"))
        g2 = pred_app("has_ticket", var("s", "S"), var("k", "K"))
        conclusion = eq(app("f", var("x", "X")), var("x", "X"))
        f = implication(g1, implication(g2, conclusion))
        guards, conc = _peel_implications(f)
        assert len(guards) == 2
        assert guards[0] is g1
        assert guards[1] is g2
        assert conc is conclusion

    def test_no_implication_returns_empty_guards(self):
        conclusion = eq(app("f", var("x", "X")), var("x", "X"))
        guards, conc = _peel_implications(conclusion)
        assert guards == []
        assert conc is conclusion


class TestCtorRoot:
    """Tests for _ctor_root helper."""

    def _make_roles(self) -> dict[str, FnRole]:
        return {
            "push": FnRole("push", FnKind.CONSTRUCTOR, "Stack"),
            "top": FnRole("top", FnKind.OBSERVER, "Stack"),
            "new": FnRole("new", FnKind.CONSTRUCTOR, "Stack"),
        }

    def test_constructor_returns_name(self):
        roles = self._make_roles()
        term = app("push", var("s", "Stack"), var("e", "Elem"))
        assert _ctor_root(term, roles) == "push"

    def test_observer_returns_none(self):
        roles = self._make_roles()
        term = app("top", var("s", "Stack"))
        assert _ctor_root(term, roles) is None

    def test_variable_returns_none(self):
        roles = self._make_roles()
        assert _ctor_root(var("s", "Stack"), roles) is None

    def test_nullary_constructor(self):
        roles = self._make_roles()
        assert _ctor_root(const("new"), roles) == "new"

    def test_unknown_function_returns_none(self):
        roles = self._make_roles()
        term = app("unknown_fn", var("x", "X"))
        assert _ctor_root(term, roles) is None


class TestClassifyGuard:
    """Tests for _classify_guard."""

    def test_positive_eq_pred_returns_hit(self):
        guard = pred_app("eq_id", var("k", "K"), var("k2", "K"))
        assert _classify_guard([guard], {"eq_id"}) == CellDispatch.HIT

    def test_negated_eq_pred_returns_miss(self):
        guard = negation(pred_app("eq_id", var("k", "K"), var("k2", "K")))
        assert _classify_guard([guard], {"eq_id"}) == CellDispatch.MISS

    def test_no_guard_returns_none(self):
        assert _classify_guard([], {"eq_id"}) is None

    def test_non_eq_pred_guard_returns_none(self):
        guard = pred_app("has_ticket", var("s", "S"), var("k", "K"))
        assert _classify_guard([guard], {"eq_id"}) is None

    def test_domain_eq_pred_not_in_cell_preds_returns_none(self):
        """Guard uses eq_code but cell_eq_preds only has eq_id — no match.

        This is the door-lock scenario: eq_code appears in a guard
        but the cell has no eq_pred (PLAIN dispatch).
        """
        guard = pred_app("eq_code", var("c", "Code"), app("get_code", var("l", "Lock")))
        assert _classify_guard([guard], {"eq_id"}) is None

    def test_conjunction_with_eq_pred_member_returns_hit(self):
        """Conjunction containing the eq_pred → HIT."""
        eq_guard = pred_app("eq_id", var("k", "K"), var("k2", "K"))
        state_guard = pred_app("has_ticket", var("s", "S"), var("k", "K"))
        guard = conjunction(eq_guard, state_guard)
        assert _classify_guard([guard], {"eq_id"}) == CellDispatch.HIT

    def test_negated_conjunction_with_eq_pred_returns_miss(self):
        """Negated conjunction containing the eq_pred → MISS."""
        eq_guard = pred_app("eq_id", var("k", "K"), var("k2", "K"))
        state_guard = pred_app("has_ticket", var("s", "S"), var("k", "K"))
        guard = negation(conjunction(eq_guard, state_guard))
        assert _classify_guard([guard], {"eq_id"}) == CellDispatch.MISS

    def test_first_matching_guard_wins(self):
        """Returns on first matching guard, not last."""
        eq_guard = pred_app("eq_id", var("k", "K"), var("k2", "K"))
        other_guard = pred_app("eq_other", var("k", "K"), var("k2", "K"))
        guards = [eq_guard, other_guard]
        assert _classify_guard(guards, {"eq_id"}) == CellDispatch.HIT


class TestIsConstructorDef:
    """Tests for _is_constructor_def."""

    def _make_roles(self) -> dict[str, FnRole]:
        return {
            "inc": FnRole("inc", FnKind.CONSTRUCTOR, "Counter"),
            "is_at_max": FnRole("is_at_max", FnKind.OBSERVER, "Counter"),
        }

    def test_def_iff_guard_is_constructor_def(self):
        roles = self._make_roles()
        c = var("c", "Counter")
        f = Biconditional(
            definedness(app("inc", c)),
            negation(pred_app("is_at_max", c)),
        )
        assert _is_constructor_def(f, roles)

    def test_swapped_sides_also_detected(self):
        roles = self._make_roles()
        c = var("c", "Counter")
        f = Biconditional(
            negation(pred_app("is_at_max", c)),
            definedness(app("inc", c)),
        )
        assert _is_constructor_def(f, roles)

    def test_non_constructor_def_not_detected(self):
        roles = self._make_roles()
        c = var("c", "Counter")
        # Definedness of an OBSERVER (not a constructor)
        f = Biconditional(
            definedness(app("is_at_max", c)),
            pred_app("something", c),
        )
        assert not _is_constructor_def(f, roles)

    def test_plain_equation_is_not_ctor_def(self):
        roles = self._make_roles()
        c = var("c", "Counter")
        f = eq(app("inc", c), c)
        assert not _is_constructor_def(f, roles)


class TestIsBasisAxiom:
    """Tests for _is_basis_axiom."""

    def _make_pred_roles(self) -> dict[str, PredRole]:
        return {
            "eq_id": PredRole("eq_id", PredKind.EQUALITY, "TicketId"),
            "has_ticket": PredRole("has_ticket", PredKind.OBSERVER, "Store"),
        }

    def test_reflexivity_is_basis(self):
        roles = self._make_pred_roles()
        k = var("k", "TicketId")
        f = pred_app("eq_id", k, k)
        assert _is_basis_axiom(f, roles)

    def test_symmetry_is_basis(self):
        roles = self._make_pred_roles()
        k1 = var("k1", "TicketId")
        k2 = var("k2", "TicketId")
        f = implication(pred_app("eq_id", k1, k2), pred_app("eq_id", k2, k1))
        assert _is_basis_axiom(f, roles)

    def test_transitivity_is_basis(self):
        roles = self._make_pred_roles()
        k1 = var("k1", "TicketId")
        k2 = var("k2", "TicketId")
        k3 = var("k3", "TicketId")
        f = implication(
            conjunction(pred_app("eq_id", k1, k2), pred_app("eq_id", k2, k3)),
            pred_app("eq_id", k1, k3),
        )
        assert _is_basis_axiom(f, roles)

    def test_observer_predicate_not_basis(self):
        roles = self._make_pred_roles()
        s = var("s", "Store")
        k = var("k", "TicketId")
        f = pred_app("has_ticket", s, k)
        assert not _is_basis_axiom(f, roles)

    def test_mixed_preds_not_basis(self):
        """Formula with both eq_pred and non-eq_pred is not a basis axiom."""
        roles = self._make_pred_roles()
        k = var("k", "TicketId")
        s = var("s", "Store")
        f = conjunction(pred_app("eq_id", k, k),
            pred_app("has_ticket", s, k))
        assert not _is_basis_axiom(f, roles)

    def test_no_eq_preds_in_roles_not_basis(self):
        """No equality predicates in signature → nothing can be a basis axiom."""
        roles: dict[str, PredRole] = {
            "has_ticket": PredRole("has_ticket", PredKind.OBSERVER, "Store"),
        }
        k = var("k", "TicketId")
        f = pred_app("has_ticket", const("empty"), k)
        assert not _is_basis_axiom(f, roles)


class TestIsDistinctness:
    """Tests for non-generated distinctness axiom detection."""

    def test_negated_equation_of_same_sort_constants(self):
        """¬(red = green) where both are constants of sort Color → DISTINCTNESS."""
        from alspec import Signature, atomic, fn, Axiom, Spec
        from alspec.obligation import build_obligation_table
        from alspec.axiom_match import match_spec_sync
        sig = Signature(
            sorts={"Color": atomic("Color"), "Light": atomic("Light")},
            functions={
                "red": fn("red", [], "Color"),
                "green": fn("green", [], "Color"),
                "yellow": fn("yellow", [], "Color"),
            },
            predicates={},
            generated_sorts={},  # Color is NOT generated
        )
        # Build a minimal spec with just this axiom
        ax = Axiom("color_distinct_rg", negation(eq(const("red"), const("green"))))
        spec = Spec(name="Test", signature=sig, axioms=(ax,))
        table = build_obligation_table(sig)
        report = match_spec_sync(spec, table, sig)
        # Must NOT be in unmatched
        assert "color_distinct_rg" not in report.unmatched_axioms
        # Must be in non_cell_axioms
        assert "color_distinct_rg" in report.non_cell_axioms

    def test_different_sort_constants_not_distinctness(self):
        """¬(red = zero) where sorts differ → should NOT match as distinctness."""
        from alspec import Signature, atomic, fn, Axiom, Spec
        from alspec.obligation import build_obligation_table
        from alspec.axiom_match import match_spec_sync
        sig = Signature(
            sorts={"Color": atomic("Color"), "Nat": atomic("Nat")},
            functions={
                "red": fn("red", [], "Color"),
                "zero": fn("zero", [], "Nat"),
            },
            predicates={},
            generated_sorts={},
        )
        ax = Axiom("cross_sort", negation(eq(const("red"), const("zero"))))
        spec = Spec(name="Test", signature=sig, axioms=(ax,))
        table = build_obligation_table(sig)
        report = match_spec_sync(spec, table, sig)
        assert "cross_sort" in report.unmatched_axioms

    def test_non_nullary_not_distinctness(self):
        """¬(f(x) = g(x)) where f, g take arguments → not distinctness."""
        from alspec import Signature, atomic, fn, Axiom, Spec
        from alspec.obligation import build_obligation_table
        from alspec.axiom_match import match_spec_sync
        sig = Signature(
            sorts={"S": atomic("S")},
            functions={
                "f": fn("f", [("x", "S")], "S"),
                "g": fn("g", [("x", "S")], "S"),
            },
            predicates={},
            generated_sorts={},
        )
        x = var("x", "S")
        ax = Axiom("not_distinct", negation(eq(app("f", x), app("g", x))))
        spec = Spec(name="Test", signature=sig, axioms=(ax,))
        table = build_obligation_table(sig)
        report = match_spec_sync(spec, table, sig)
        assert "not_distinct" in report.unmatched_axioms

    def test_quantified_distinctness(self):
        """forall-wrapped distinctness should still be detected (quantifiers are peeled).."""
        from alspec import Signature, atomic, fn, Axiom, Spec
        from alspec.obligation import build_obligation_table
        from alspec.axiom_match import match_spec_sync
        sig = Signature(
            sorts={"Bool": atomic("Bool")},
            functions={
                "high": fn("high", [], "Bool"),
                "low": fn("low", [], "Bool"),
            },
            predicates={},
            generated_sorts={},
        )
        # Some models wrap distinctness in a vacuous forall
        ax = Axiom("bool_distinct", negation(eq(const("high"), const("low"))))
        spec = Spec(name="Test", signature=sig, axioms=(ax,))
        table = build_obligation_table(sig)
        report = match_spec_sync(spec, table, sig)
        assert "bool_distinct" not in report.unmatched_axioms
        assert "bool_distinct" in report.non_cell_axioms

    def test_negated_eq_predapp_same_sort_constants(self):
        """¬eq_color(red, green) where eq_color is EQUALITY → DISTINCTNESS."""
        from alspec import Signature, atomic, fn, pred, Negation, PredApp, const
        from alspec.obligation import FnRole, FnKind, PredRole, PredKind
        from alspec.axiom_match import _is_distinctness_axiom

        sig = Signature(
            sorts={"Color": atomic("Color"), "Light": atomic("Light")},
            functions={
                "red": fn("red", [], "Color"),
                "green": fn("green", [], "Color"),
            },
            predicates={
                "eq_color": pred("eq_color", [("c1", "Color"), ("c2", "Color")]),
            },
            generated_sorts={},
        )
        fn_roles = {
            "red": FnRole("red", FnKind.CONSTANT, None),
            "green": FnRole("green", FnKind.CONSTANT, None),
        }
        pred_roles = {
            "eq_color": PredRole("eq_color", PredKind.EQUALITY, "Color"),
        }
        f = negation(pred_app("eq_color", const("red"), const("green")))
        assert _is_distinctness_axiom(f, fn_roles, sig, pred_roles=pred_roles)

    def test_negated_eq_predapp_cross_sort_not_distinctness(self):
        """¬eq_color(red, zero) where sorts differ → not distinctness."""
        from alspec import Signature, atomic, fn, pred, Negation, PredApp, const
        from alspec.obligation import FnRole, FnKind, PredRole, PredKind
        from alspec.axiom_match import _is_distinctness_axiom

        sig = Signature(
            sorts={"Color": atomic("Color"), "Nat": atomic("Nat")},
            functions={
                "red": fn("red", [], "Color"),
                "zero": fn("zero", [], "Nat"),
            },
            predicates={
                "eq_color": pred("eq_color", [("c1", "Color"), ("c2", "Color")]),
            },
            generated_sorts={},
        )
        fn_roles = {
            "red": FnRole("red", FnKind.CONSTANT, None),
            "zero": FnRole("zero", FnKind.CONSTANT, None),
        }
        pred_roles = {
            "eq_color": PredRole("eq_color", PredKind.EQUALITY, "Color"),
        }
        f = negation(pred_app("eq_color", const("red"), const("zero")))
        assert not _is_distinctness_axiom(f, fn_roles, sig, pred_roles=pred_roles)

    def test_negated_non_eq_predapp_not_distinctness(self):
        """¬has_ticket(a, b) where has_ticket is OBSERVER → not distinctness."""
        from alspec import Negation, PredApp, const
        from alspec.obligation import FnRole, FnKind, PredRole, PredKind
        from alspec.axiom_match import _is_distinctness_axiom

        fn_roles = {
            "a": FnRole("a", FnKind.CONSTANT, None),
            "b": FnRole("b", FnKind.CONSTANT, None),
        }
        pred_roles = {
            "has_ticket": PredRole("has_ticket", PredKind.OBSERVER, "Store"),
        }
        f = negation(pred_app("has_ticket", const("a"), const("b")))
        assert not _is_distinctness_axiom(f, fn_roles, sig=None, pred_roles=pred_roles)

    def test_negated_eq_predapp_three_args_not_distinctness(self):
        """¬eq_color(a, b, c) with 3 args → not distinctness."""
        from alspec import Negation, PredApp, const
        from alspec.obligation import PredRole, PredKind
        from alspec.axiom_match import _is_distinctness_axiom

        fn_roles = {}
        pred_roles = {
            "eq_color": PredRole("eq_color", PredKind.EQUALITY, "Color"),
        }
        f = negation(pred_app("eq_color", const("a"), const("b"), const("c")))
        assert not _is_distinctness_axiom(f, fn_roles, sig=None, pred_roles=pred_roles)

    def test_negated_eq_predapp_no_pred_roles_backward_compat(self):
        """pred_roles=None (default) → PredApp branch skipped, returns False."""
        from alspec import Negation, PredApp, const
        from alspec.obligation import FnRole, FnKind
        from alspec.axiom_match import _is_distinctness_axiom

        fn_roles = {
            "red": FnRole("red", FnKind.CONSTANT, None),
            "green": FnRole("green", FnKind.CONSTANT, None),
        }
        # PredApp form, but pred_roles not passed → should NOT match
        f = negation(pred_app("eq_color", const("red"), const("green")))
        assert not _is_distinctness_axiom(f, fn_roles, sig=None)

    def test_negated_eq_predapp_same_constant_not_distinctness(self):
        """¬eq_color(red, red) is contradictory, not distinctness."""
        from alspec import Signature, atomic, fn, pred, Negation, PredApp, const
        from alspec.obligation import FnRole, FnKind, PredRole, PredKind
        from alspec.axiom_match import _is_distinctness_axiom

        sig = Signature(
            sorts={"Color": atomic("Color")},
            functions={"red": fn("red", [], "Color")},
            predicates={"eq_color": pred("eq_color", [("c1", "Color"), ("c2", "Color")])},
            generated_sorts={},
        )
        fn_roles = {"red": FnRole("red", FnKind.CONSTANT, None)}
        pred_roles = {"eq_color": PredRole("eq_color", PredKind.EQUALITY, "Color")}
        f = negation(pred_app("eq_color", const("red"), const("red")))
        assert not _is_distinctness_axiom(f, fn_roles, sig, pred_roles=pred_roles)

    def test_predapp_distinctness_full_match(self):
        """Full spec with PredApp-form distinctness → lands in non_cell_axioms."""
        from alspec import Signature, atomic, fn, pred, Axiom, Spec, Negation, PredApp, const
        from alspec.obligation import build_obligation_table
        from alspec.axiom_match import match_spec_sync

        sig = Signature(
            sorts={"Color": atomic("Color"), "Light": atomic("Light")},
            functions={
                "red": fn("red", [], "Color"),
                "green": fn("green", [], "Color"),
                "yellow": fn("yellow", [], "Color"),
            },
            predicates={
                "eq_color": pred("eq_color", [("c1", "Color"), ("c2", "Color")]),
            },
            generated_sorts={},
        )
        ax = Axiom("color_distinct_rg", negation(pred_app("eq_color", const("red"), const("green"))))
        spec = Spec(name="Test", signature=sig, axioms=(ax,))
        table = build_obligation_table(sig)
        report = match_spec_sync(spec, table, sig)
        assert "color_distinct_rg" not in report.unmatched_axioms
        assert "color_distinct_rg" in report.non_cell_axioms

    def test_negated_eq_predapp_generated_sort_constructors(self):
        """¬eq_color(red, green) where Color is generated + red/green are CONSTRUCTOR → DISTINCTNESS."""
        from alspec import Signature, GeneratedSortInfo, atomic, fn, pred, Negation, PredApp, const
        from alspec.obligation import FnRole, FnKind, PredRole, PredKind
        from alspec.axiom_match import _is_distinctness_axiom

        sig = Signature(
            sorts={"Color": atomic("Color")},
            functions={
                "red": fn("red", [], "Color"),
                "green": fn("green", [], "Color"),
            },
            predicates={
                "eq_color": pred("eq_color", [("c1", "Color"), ("c2", "Color")]),
            },
            generated_sorts={
                "Color": GeneratedSortInfo(constructors=("red", "green"), selectors={}),
            },
        )
        fn_roles = {
            "red": FnRole("red", FnKind.CONSTRUCTOR, "Color"),
            "green": FnRole("green", FnKind.CONSTRUCTOR, "Color"),
        }
        pred_roles = {
            "eq_color": PredRole("eq_color", PredKind.EQUALITY, "Color"),
        }
        f = negation(pred_app("eq_color", const("red"), const("green")))
        assert _is_distinctness_axiom(f, fn_roles, sig, pred_roles=pred_roles)

    def test_conjunction_of_equation_distinctness(self):
        """Conjunction of ¬(c₁=c₂) assertions → DISTINCTNESS."""
        from alspec import Signature, atomic, fn, Negation, Conjunction, const
        from alspec.obligation import FnRole, FnKind
        from alspec.axiom_match import _is_distinctness_axiom
        from alspec.helpers import eq

        sig = Signature(
            sorts={"Phase": atomic("Phase")},
            functions={
                "red": fn("red", [], "Phase"),
                "amber": fn("amber", [], "Phase"),
                "green": fn("green", [], "Phase"),
            },
            predicates={},
            generated_sorts={},
        )
        fn_roles = {
            "red": FnRole("red", FnKind.CONSTANT, None),
            "amber": FnRole("amber", FnKind.CONSTANT, None),
            "green": FnRole("green", FnKind.CONSTANT, None),
        }
        f = conjunction(negation(eq(const("red"), const("amber"))),
            negation(eq(const("amber"), const("green"))),
            negation(eq(const("red"), const("green"))))
        assert _is_distinctness_axiom(f, fn_roles, sig)

    def test_conjunction_of_predapp_distinctness(self):
        """Conjunction of ¬eq_phase(c₁, c₂) assertions → DISTINCTNESS."""
        from alspec import Signature, atomic, fn, pred, Negation, Conjunction, PredApp, const
        from alspec.obligation import FnRole, FnKind, PredRole, PredKind
        from alspec.axiom_match import _is_distinctness_axiom

        sig = Signature(
            sorts={"Phase": atomic("Phase")},
            functions={
                "red": fn("red", [], "Phase"),
                "yellow": fn("yellow", [], "Phase"),
                "green": fn("green", [], "Phase"),
            },
            predicates={
                "eq_phase": pred("eq_phase", [("p1", "Phase"), ("p2", "Phase")]),
            },
            generated_sorts={},
        )
        fn_roles = {
            "red": FnRole("red", FnKind.CONSTANT, None),
            "yellow": FnRole("yellow", FnKind.CONSTANT, None),
            "green": FnRole("green", FnKind.CONSTANT, None),
        }
        pred_roles = {
            "eq_phase": PredRole("eq_phase", PredKind.EQUALITY, "Phase"),
        }
        f = conjunction(negation(pred_app("eq_phase", const("red"), const("yellow"))),
            negation(pred_app("eq_phase", const("yellow"), const("green"))),
            negation(pred_app("eq_phase", const("red"), const("green"))))
        assert _is_distinctness_axiom(f, fn_roles, sig, pred_roles=pred_roles)

    def test_conjunction_with_non_distinctness_conjunct(self):
        """Conjunction where one conjunct is not distinctness → False."""
        from alspec import Negation, Conjunction, PredApp, const
        from alspec.obligation import FnRole, FnKind
        from alspec.axiom_match import _is_distinctness_axiom
        from alspec.helpers import eq

        fn_roles = {
            "red": FnRole("red", FnKind.CONSTANT, None),
            "green": FnRole("green", FnKind.CONSTANT, None),
        }
        f = conjunction(
            negation(eq(const("red"), const("green"))),
            pred_app("some_pred", const("red")),  # not distinctness
        )
        assert not _is_distinctness_axiom(f, fn_roles, sig=None)

    def test_empty_conjunction_not_distinctness(self):
        """Empty Conjunction → False (vacuous, not meaningful distinctness)."""
        from alspec import Conjunction
        from alspec.axiom_match import _is_distinctness_axiom

        f = conjunction()
        assert not _is_distinctness_axiom(f, {}, sig=None)

    def test_singleton_conjunction_distinctness(self):
        """Conjunction with one distinctness element → DISTINCTNESS."""
        from alspec import Signature, atomic, fn, Negation, Conjunction, const
        from alspec.obligation import FnRole, FnKind
        from alspec.axiom_match import _is_distinctness_axiom
        from alspec.helpers import eq

        sig = Signature(
            sorts={"Bool": atomic("Bool")},
            functions={
                "true": fn("true", [], "Bool"),
                "false": fn("false", [], "Bool"),
            },
            predicates={},
            generated_sorts={},
        )
        fn_roles = {
            "true": FnRole("true", FnKind.CONSTANT, None),
            "false": FnRole("false", FnKind.CONSTANT, None),
        }
        f = conjunction(negation(eq(const("true"), const("false"))))
        assert _is_distinctness_axiom(f, fn_roles, sig)

    def test_conjunction_distinctness_full_match(self):
        """Bundled distinctness through match_spec_sync → non_cell_axioms."""
        from alspec import Signature, atomic, fn, Axiom, Spec, Negation, Conjunction, const
        from alspec.obligation import build_obligation_table
        from alspec.axiom_match import match_spec_sync
        from alspec.helpers import eq

        sig = Signature(
            sorts={"Phase": atomic("Phase"), "Light": atomic("Light")},
            functions={
                "red": fn("red", [], "Phase"),
                "amber": fn("amber", [], "Phase"),
                "green": fn("green", [], "Phase"),
            },
            predicates={},
            generated_sorts={},
        )
        ax = Axiom("distinct_phases", conjunction(negation(eq(const("red"), const("amber"))),
            negation(eq(const("amber"), const("green"))),
            negation(eq(const("red"), const("green")))))
        spec = Spec(name="Test", signature=sig, axioms=(ax,))
        table = build_obligation_table(sig)
        report = match_spec_sync(spec, table, sig)
        assert "distinct_phases" not in report.unmatched_axioms
        assert "distinct_phases" in report.non_cell_axioms

    def test_multiple_conjunction_distinctness_full_match(self):
        """Two bundled distinctness axioms for different sorts → both in non_cell_axioms."""
        from alspec import Signature, atomic, fn, Axiom, Spec, Negation, Conjunction, const
        from alspec.obligation import build_obligation_table
        from alspec.axiom_match import match_spec_sync
        from alspec.helpers import eq

        sig = Signature(
            sorts={"Phase": atomic("Phase"), "Mode": atomic("Mode")},
            functions={
                "red": fn("red", [], "Phase"),
                "green": fn("green", [], "Phase"),
                "normal": fn("normal", [], "Mode"),
                "flashing": fn("flashing", [], "Mode"),
            },
            predicates={},
            generated_sorts={},
        )
        axioms = (
            Axiom("distinct_phases", conjunction(negation(eq(const("red"), const("green"))))),
            Axiom("distinct_modes", conjunction(negation(eq(const("normal"), const("flashing"))))),
        )
        spec = Spec(name="Test", signature=sig, axioms=axioms)
        table = build_obligation_table(sig)
        report = match_spec_sync(spec, table, sig)
        assert "distinct_phases" not in report.unmatched_axioms
        assert "distinct_modes" not in report.unmatched_axioms
        assert "distinct_phases" in report.non_cell_axioms
        assert "distinct_modes" in report.non_cell_axioms


class TestFindObsCtor:
    """Tests for _find_obs_ctor."""

    def _counter_roles(self):
        fn_roles = {
            "new": FnRole("new", FnKind.CONSTRUCTOR, "Counter"),
            "inc": FnRole("inc", FnKind.CONSTRUCTOR, "Counter"),
            "get_value": FnRole("get_value", FnKind.OBSERVER, "Counter"),
        }
        pred_roles: dict[str, PredRole] = {}
        return fn_roles, pred_roles

    def test_equation_lhs(self):
        fn_roles, pred_roles = self._counter_roles()
        c = var("c", "Counter")
        f = eq(app("get_value", const("new")), const("zero"))
        result = _find_obs_ctor(f, fn_roles, pred_roles)
        assert result == ("get_value", False, "new")

    def test_equation_lhs_with_variable(self):
        fn_roles, pred_roles = self._counter_roles()
        c = var("c", "Counter")
        f = eq(app("get_value", app("inc", c)), app("succ", app("get_value", c)))
        result = _find_obs_ctor(f, fn_roles, pred_roles)
        assert result == ("get_value", False, "inc")

    def test_negation_definedness(self):
        """negation(definedness(obs(ctor(...)))) — used for partial selectors."""
        fn_roles = {
            "new": FnRole("new", FnKind.CONSTRUCTOR, "Stack"),
            "pop": FnRole("pop", FnKind.SELECTOR, "Stack"),
        }
        pred_roles: dict[str, PredRole] = {}
        f = negation(definedness(app("pop", const("new"))))
        result = _find_obs_ctor(f, fn_roles, pred_roles)
        assert result == ("pop", False, "new")

    def test_predapp_observer(self):
        """PredApp with observer on constructor first arg."""
        fn_roles = {
            "new": FnRole("new", FnKind.CONSTRUCTOR, "Stack"),
            "push": FnRole("push", FnKind.CONSTRUCTOR, "Stack"),
        }
        pred_roles = {
            "empty": PredRole("empty", PredKind.OBSERVER, "Stack"),
        }
        f = pred_app("empty", const("new"))
        result = _find_obs_ctor(f, fn_roles, pred_roles)
        assert result == ("empty", True, "new")

    def test_negated_predapp_observer(self):
        """negation(PredApp(obs, (ctor(...),))) — used for push/new predicates."""
        fn_roles = {
            "push": FnRole("push", FnKind.CONSTRUCTOR, "Stack"),
        }
        pred_roles = {
            "empty": PredRole("empty", PredKind.OBSERVER, "Stack"),
        }
        s = var("s", "Stack")
        e = var("e", "Elem")
        f = negation(pred_app("empty", app("push", s, e)))
        result = _find_obs_ctor(f, fn_roles, pred_roles)
        assert result == ("empty", True, "push")

    def test_biconditional_lhs(self):
        """Biconditional with observer on LHS."""
        fn_roles = {
            "new": FnRole("new", FnKind.CONSTRUCTOR, "Thermostat"),
        }
        pred_roles = {
            "heater_on": PredRole("heater_on", PredKind.OBSERVER, "Thermostat"),
            "lt": PredRole("lt", PredKind.OTHER, None),
        }
        f = Biconditional(
            pred_app("heater_on", const("new")),
            pred_app("lt", const("init_current"), const("init_target")),
        )
        result = _find_obs_ctor(f, fn_roles, pred_roles)
        assert result == ("heater_on", True, "new")

    def test_biconditional_rhs_observer(self):
        """Observer on RHS of biconditional is still found."""
        fn_roles = {
            "new": FnRole("new", FnKind.CONSTRUCTOR, "Thermostat"),
        }
        pred_roles = {
            "heater_on": PredRole("heater_on", PredKind.OBSERVER, "Thermostat"),
            "lt": PredRole("lt", PredKind.OTHER, None),
        }
        # Observer on RHS — non-standard but should still be found
        f = Biconditional(
            pred_app("lt", const("a"), const("b")),
            pred_app("heater_on", const("new")),
        )
        result = _find_obs_ctor(f, fn_roles, pred_roles)
        assert result == ("heater_on", True, "new")

    def test_non_observer_returns_none(self):
        """PredApp that is not an observer returns None."""
        fn_roles = {
            "new": FnRole("new", FnKind.CONSTRUCTOR, "Stack"),
        }
        pred_roles = {
            "lt": PredRole("lt", PredKind.OTHER, None),
        }
        f = pred_app("lt", const("new"), const("new"))
        assert _find_obs_ctor(f, fn_roles, pred_roles) is None

    def test_unrecognized_formula_returns_none(self):
        """Formula with no observer/constructor pattern returns None."""
        fn_roles: dict[str, FnRole] = {}
        pred_roles: dict[str, PredRole] = {}
        # Simple equation with no recognized roles
        f = eq(var("x", "X"), var("y", "Y"))
        assert _find_obs_ctor(f, fn_roles, pred_roles) is None


class TestWalkFormulaFnsDefensive:
    """_walk_formula_fns should not crash on FnApp in formula position."""

    def test_fnapp_in_negation_does_not_crash(self):
        """FnApp inside Negation (LLM error) should extract fn names, not crash."""
        # Simulates: negation(app("is_read", app("receive", i, m), m2))
        malformed = negation(app("is_read", app("receive", var("i", "Inbox"), var("m", "Msg")), var("m2", "Msg")))
        # Should not raise TypeError
        names = _collect_fn_names(malformed)
        assert "is_read" in names
        assert "receive" in names

    def test_fnapp_in_conjunction_does_not_crash(self):
        """FnApp inside Conjunction should not crash."""
        malformed = conjunction(
            pred_app("some_pred", var("x", "X")),
            app("some_fn", var("y", "Y")),  # FnApp where Formula expected
        )
        names = _collect_fn_names(malformed)
        assert "some_fn" in names
        assert "some_pred" not in names  # _collect_fn_names doesn't collect pred names


# ===========================================================================
# Golden spec integration tests
# ===========================================================================


class TestMatchCounter:
    """Counter: 4 axioms, 4 PLAIN cells, all DIRECT, full coverage."""

    def setup_method(self):
        mod = _load_golden("counter")
        spec = mod.counter_spec()
        table = build_obligation_table(spec.signature)
        self.report = match_spec_sync(spec, table, spec.signature)

    def test_no_unmatched_axioms(self):
        assert len(self.report.unmatched_axioms) == 0

    def test_no_uncovered_cells(self):
        assert len(self.report.uncovered_cells) == 0

    def test_no_non_cell_axioms(self):
        assert len(self.report.non_cell_axioms) == 0

    def test_all_direct(self):
        for m in self.report.matches:
            assert m.kind == MatchKind.DIRECT, (
                f"Axiom {m.axiom_label!r} expected DIRECT, got {m.kind}"
            )

    def test_each_axiom_covers_one_cell(self):
        for m in self.report.matches:
            assert len(m.cells) == 1, (
                f"Axiom {m.axiom_label!r} expected 1 cell, got {len(m.cells)}"
            )

    def test_four_axioms_matched(self):
        assert len(self.report.matches) == 4


class TestMatchStack:
    """Stack: 6 axioms, 6 PLAIN cells, all DIRECT, full coverage.

    Includes selector axioms: SELECTOR_EXTRACT (eq) and SELECTOR_FOREIGN (¬def).
    """

    def setup_method(self):
        mod = _load_golden("stack")
        spec = mod.stack_spec()
        table = build_obligation_table(spec.signature)
        self.report = match_spec_sync(spec, table, spec.signature)

    def test_no_unmatched_axioms(self):
        assert len(self.report.unmatched_axioms) == 0

    def test_no_uncovered_cells(self):
        assert len(self.report.uncovered_cells) == 0

    def test_no_non_cell_axioms(self):
        assert len(self.report.non_cell_axioms) == 0

    def test_all_direct(self):
        for m in self.report.matches:
            assert m.kind == MatchKind.DIRECT, (
                f"Axiom {m.axiom_label!r} expected DIRECT, got {m.kind}"
            )

    def test_six_axioms(self):
        assert len(self.report.matches) == 6

    def test_pop_new_undef_matched(self):
        """pop_new_undef (SELECTOR_FOREIGN) matches (pop, new) PLAIN cell."""
        pop_new = [m for m in self.report.matches if m.axiom_label == "pop_new_undef"]
        assert len(pop_new) == 1
        assert pop_new[0].kind == MatchKind.DIRECT
        assert len(pop_new[0].cells) == 1
        cell = pop_new[0].cells[0]
        assert cell.observer_name == "pop"
        assert cell.constructor_name == "new"

    def test_empty_predicate_matches(self):
        """empty_new and not_empty_push match predicate observer cells."""
        empty_new = [m for m in self.report.matches if m.axiom_label == "empty_new"]
        assert len(empty_new) == 1
        assert empty_new[0].cells[0].observer_name == "empty"
        assert empty_new[0].cells[0].constructor_name == "new"


class TestMatchBoundedCounter:
    """Bounded counter: partial constructor, inc_def is CONSTRUCTOR_DEF."""

    def setup_method(self):
        mod = _load_golden("bounded-counter")
        spec = mod.bounded_counter_spec()
        table = build_obligation_table(spec.signature)
        self.report = match_spec_sync(spec, table, spec.signature)
        self.spec = spec

    def test_inc_def_is_constructor_def(self):
        inc_def = [m for m in self.report.matches if m.axiom_label == "inc_def"]
        assert len(inc_def) == 1
        assert inc_def[0].kind == MatchKind.CONSTRUCTOR_DEF
        assert inc_def[0].cells == ()

    def test_no_unmatched_axioms(self):
        assert len(self.report.unmatched_axioms) == 0

    def test_no_uncovered_cells(self):
        assert len(self.report.uncovered_cells) == 0

    def test_inc_def_in_non_cell_axioms(self):
        assert "inc_def" in self.report.non_cell_axioms

    def test_observer_axioms_are_direct(self):
        """val_new, val_inc, max_val_new, etc. are DIRECT."""
        for m in self.report.matches:
            if m.axiom_label != "inc_def":
                assert m.kind == MatchKind.DIRECT, (
                    f"Axiom {m.axiom_label!r} expected DIRECT, got {m.kind}"
                )


class TestMatchDoorLock:
    """Door lock: eq_code in domain guards but PLAIN cells for get_state."""

    def setup_method(self):
        mod = _load_golden("door-lock")
        spec = mod.door_lock_spec()
        table = build_obligation_table(spec.signature)
        self.report = match_spec_sync(spec, table, spec.signature)

    def test_eq_code_basis_axioms(self):
        """3 eq_code basis axioms classified as BASIS."""
        basis = [m for m in self.report.matches if m.kind == MatchKind.BASIS]
        assert len(basis) == 3
        basis_labels = {m.axiom_label for m in basis}
        assert "eq_code_refl" in basis_labels
        assert "eq_code_sym" in basis_labels
        assert "eq_code_trans" in basis_labels

    def test_no_unmatched_axioms(self):
        assert len(self.report.unmatched_axioms) == 0

    def test_no_uncovered_cells(self):
        assert len(self.report.uncovered_cells) == 0

    def test_get_state_lock_cells_are_plain(self):
        """CRITICAL: get_state_lock axioms must match PLAIN cells.

        The obligation table has no HIT/MISS for (get_state, lock) because
        get_state takes only Lock as param. The eq_code guard in the axiom
        is a domain-level guard, not the cell's eq_pred.
        """
        lock_axioms = [
            m for m in self.report.matches
            if m.axiom_label in ("get_state_lock_hit", "get_state_lock_miss")
        ]
        assert len(lock_axioms) == 2
        for m in lock_axioms:
            for cell in m.cells:
                assert cell.dispatch == CellDispatch.PLAIN, (
                    f"Axiom {m.axiom_label!r} matched {cell.dispatch} cell — "
                    f"eq_code guard was falsely interpreted as key dispatch"
                )

    def test_get_code_new_is_selector_extract(self):
        """get_code is a selector of new — the new cell should be covered."""
        get_code_new = [
            m for m in self.report.matches if m.axiom_label == "get_code_new"
        ]
        assert len(get_code_new) == 1
        assert get_code_new[0].kind == MatchKind.DIRECT

    def test_multi_covered_cells_from_hit_miss_axioms(self):
        """get_state_lock_hit and get_state_lock_miss both match PLAIN (multi-covered)."""
        lock_cell_coverages = [
            cc for cc in self.report.coverage
            if cc.cell.observer_name == "get_state"
            and cc.cell.constructor_name == "lock"
        ]
        assert len(lock_cell_coverages) == 1
        assert lock_cell_coverages[0].status == CoverageStatus.MULTI_COVERED
        assert len(lock_cell_coverages[0].axiom_labels) == 2


class TestMatchThermostat:
    """Thermostat: biconditional predicates, no partial functions."""

    def setup_method(self):
        mod = _load_golden("thermostat")
        spec = mod.thermostat_spec()
        table = build_obligation_table(spec.signature)
        self.report = match_spec_sync(spec, table, spec.signature)

    def test_no_unmatched_axioms(self):
        assert len(self.report.unmatched_axioms) == 0

    def test_no_uncovered_cells(self):
        assert len(self.report.uncovered_cells) == 0

    def test_heater_on_axioms_are_direct(self):
        """heater_on axioms use biconditional — verify they match correctly."""
        heater_axioms = [
            m for m in self.report.matches if "heater_on" in m.axiom_label
        ]
        assert len(heater_axioms) == 3
        for m in heater_axioms:
            assert m.kind == MatchKind.DIRECT, (
                f"Axiom {m.axiom_label!r} expected DIRECT, got {m.kind}"
            )

    def test_nine_total_axioms(self):
        assert len(self.report.matches) == 9


class TestMatchBugTracker:
    """Bug tracker: key dispatch, preservation, basis axioms, 32 total."""

    def setup_method(self):
        mod = _load_golden("bug-tracker")
        spec = mod.bug_tracker_spec()
        table = build_obligation_table(spec.signature)
        self.report = match_spec_sync(spec, table, spec.signature)

    def test_three_basis_axioms(self):
        """eq_id basis: reflexivity, symmetry, transitivity."""
        basis = [m for m in self.report.matches if m.kind == MatchKind.BASIS]
        assert len(basis) == 3
        basis_labels = {m.axiom_label for m in basis}
        assert "eq_id_refl" in basis_labels
        assert "eq_id_sym" in basis_labels
        assert "eq_id_trans" in basis_labels

    def test_preservation_axioms_exist(self):
        """Preservation axioms cover all keys for their observer/constructor."""
        preservation = [m for m in self.report.matches if m.kind == MatchKind.PRESERVATION]
        assert len(preservation) > 0

    def test_get_severity_resolve_is_preservation(self):
        """get_severity_resolve covers both HIT and MISS — preservation."""
        m = next(
            (x for x in self.report.matches if x.axiom_label == "get_severity_resolve"),
            None,
        )
        assert m is not None
        assert m.kind == MatchKind.PRESERVATION

    def test_get_severity_assign_is_preservation(self):
        m = next(
            (x for x in self.report.matches if x.axiom_label == "get_severity_assign"),
            None,
        )
        assert m is not None
        assert m.kind == MatchKind.PRESERVATION

    def test_create_hit_axioms_are_direct(self):
        """get_status_create_hit, etc. match the HIT cell directly."""
        hit_axioms = [
            m for m in self.report.matches
            if m.axiom_label.endswith("_create_hit")
        ]
        for m in hit_axioms:
            assert m.kind == MatchKind.DIRECT
            assert len(m.cells) == 1
            assert m.cells[0].dispatch == CellDispatch.HIT

    def test_create_miss_axioms_are_direct(self):
        """get_status_create_miss etc. match the MISS cell directly."""
        miss_axioms = [
            m for m in self.report.matches
            if m.axiom_label.endswith("_create_miss")
        ]
        for m in miss_axioms:
            assert m.kind == MatchKind.DIRECT
            assert len(m.cells) == 1
            assert m.cells[0].dispatch == CellDispatch.MISS


    def test_no_unmatched_axioms(self):
        assert len(self.report.unmatched_axioms) == 0

    def test_no_uncovered_cells(self):
        """Bug-tracker golden now has all 3 missing ¬def axioms for partial observers
        on the empty constructor (get_status_empty_undef, get_severity_empty_undef,
        get_assignee_empty_undef). Coverage should be complete.
        """
        assert len(self.report.uncovered_cells) == 0

    def test_thirty_two_axioms(self):
        assert len(self.report.matches) == 32


class TestMatchQueue:
    """Queue: multiple axioms per (dequeue, enqueue) cell (MULTI_COVERED)."""

    def setup_method(self):
        mod = _load_golden("queue")
        spec = mod.queue_spec()
        table = build_obligation_table(spec.signature)
        self.report = match_spec_sync(spec, table, spec.signature)
        self.spec = spec

    def test_no_unmatched_axioms(self):
        assert len(self.report.unmatched_axioms) == 0

    def test_dequeue_enqueue_cell_multi_covered(self):
        """dequeue_empty_enqueue and dequeue_nonempty_enqueue both cover (dequeue, enqueue)."""
        dequeue_enqueue = [
            cc for cc in self.report.coverage
            if cc.cell.observer_name == "dequeue"
            and cc.cell.constructor_name == "enqueue"
        ]
        assert len(dequeue_enqueue) == 1
        assert dequeue_enqueue[0].status == CoverageStatus.MULTI_COVERED
        assert len(dequeue_enqueue[0].axiom_labels) == 2
        assert "dequeue_empty_enqueue" in dequeue_enqueue[0].axiom_labels
        assert "dequeue_nonempty_enqueue" in dequeue_enqueue[0].axiom_labels

    def test_front_enqueue_cell_multi_covered(self):
        """front_empty_enqueue and front_nonempty_enqueue both cover (front, enqueue)."""
        front_enqueue = [
            cc for cc in self.report.coverage
            if cc.cell.observer_name == "front"
            and cc.cell.constructor_name == "enqueue"
        ]
        assert len(front_enqueue) == 1
        assert front_enqueue[0].status == CoverageStatus.MULTI_COVERED

    def test_no_uncovered_cells(self):
        assert len(self.report.uncovered_cells) == 0


# ===========================================================================
# Additional golden spec tests (smoke tests)
# ===========================================================================


GOLDEN_STEMS = [
    "counter",
    "stack",
    "queue",
    "thermostat",
    "bounded-counter",
    "door-lock",
    "bug-tracker",
    "bank-account",
    "boolean-flag",
    "traffic-light",
    "phone-book",
    "temperature-sensor",
    "inventory",
    "shopping-cart",
    "access-control",
    "library-lending",
    "auction",
    "email-inbox",
    "todo-list",
    "version-history",
]

# Specs where the matcher handles every axiom pattern (strict assertion).
# Specs NOT in this set have known exceptional axiom patterns:
#   - access-control: distinctness axioms (negation(Equation(const, const)))
#                     and can_access_def (derived pred with Var first arg).
#   - email-inbox: pred_zero/pred_suc (Nat helper axioms for uninterpreted fns).
# These are legitimately UNMATCHED — they don't follow the obs(ctor(...)) pattern.
ZERO_UNMATCHED_SPECS = set(GOLDEN_STEMS) - {"email-inbox"}

# Specs expected to have full cell coverage (zero UNCOVERED cells).
EXPECTED_FULL_COVERAGE_SPECS = {
    "counter",
    "stack",
    "queue",
    "thermostat",
    "bounded-counter",
    "door-lock",
    "bug-tracker",
}


def _get_spec_fn_name(stem: str) -> str:
    """Map stem to the spec factory function name."""
    return stem.replace("-", "_") + "_spec"


@pytest.mark.parametrize("stem", GOLDEN_STEMS)
def test_golden_spec_runs_without_error(stem: str):
    """Smoke test: match_spec_sync completes without crashing for all golden specs."""
    import sys
    mod = _load_golden(stem)
    fn_name = _get_spec_fn_name(stem)
    spec = getattr(mod, fn_name)()
    table = build_obligation_table(spec.signature)
    report = match_spec_sync(spec, table, spec.signature)

    # Report diagnostics (visible with pytest -s)
    if report.unmatched_axioms:
        print(
            f"\n[{stem}] UNMATCHED: {list(report.unmatched_axioms)}", file=sys.stderr
        )
    if report.uncovered_cells:
        print(
            f"\n[{stem}] UNCOVERED: "
            + str([
                f"({c.observer_name}, {c.constructor_name}, {c.dispatch.value})"
                for c in report.uncovered_cells
            ]),
            file=sys.stderr,
        )


@pytest.mark.parametrize("stem", sorted(ZERO_UNMATCHED_SPECS))
def test_golden_spec_no_unmatched(stem: str):
    """For all specs except known exceptions, no axiom should be UNMATCHED."""
    mod = _load_golden(stem)
    fn_name = _get_spec_fn_name(stem)
    spec = getattr(mod, fn_name)()
    table = build_obligation_table(spec.signature)
    report = match_spec_sync(spec, table, spec.signature)

    assert len(report.unmatched_axioms) == 0, (
        f"[{stem}] Unexpected UNMATCHED axioms: {list(report.unmatched_axioms)}"
    )


@pytest.mark.parametrize("stem", sorted(EXPECTED_FULL_COVERAGE_SPECS))
def test_golden_spec_full_coverage(stem: str):
    """Selected golden specs should have full cell coverage."""
    mod = _load_golden(stem)
    fn_name = _get_spec_fn_name(stem)
    spec = getattr(mod, fn_name)()
    table = build_obligation_table(spec.signature)
    report = match_spec_sync(spec, table, spec.signature)

    uncovered_desc = [
        f"({c.observer_name}, {c.constructor_name}, {c.dispatch.value})"
        for c in report.uncovered_cells
    ]
    assert len(report.uncovered_cells) == 0, (
        f"[{stem}] Unexpected UNCOVERED cells: {uncovered_desc}"
    )


# ===========================================================================
# Edge case tests
# ===========================================================================


class TestEdgeCases:
    def test_preservation_covers_both_hit_and_miss_cells(self):
        """Preservation axiom matches both HIT and MISS cells."""
        # Use bug-tracker: get_severity_resolve is preservation
        mod = _load_golden("bug-tracker")
        spec = mod.bug_tracker_spec()
        table = build_obligation_table(spec.signature)
        report = match_spec_sync(spec, table, spec.signature)

        m = next(
            x for x in report.matches if x.axiom_label == "get_severity_resolve"
        )
        assert m.kind == MatchKind.PRESERVATION
        dispatches = {c.dispatch for c in m.cells}
        assert CellDispatch.HIT in dispatches
        assert CellDispatch.MISS in dispatches

    def test_constructor_def_not_matched_as_cell(self):
        """iff(definedness(ctor), guard) should NOT match any cell."""
        mod = _load_golden("bounded-counter")
        spec = mod.bounded_counter_spec()
        table = build_obligation_table(spec.signature)
        report = match_spec_sync(spec, table, spec.signature)

        inc_def = next(x for x in report.matches if x.axiom_label == "inc_def")
        assert inc_def.kind == MatchKind.CONSTRUCTOR_DEF
        assert inc_def.cells == ()

    def test_unmatched_axiom_produces_warning(self, caplog):
        """Unmatched axioms produce WARNING-level log messages."""
        # Create a spec with a malformed/unrecognizable axiom
        from alspec import Axiom, GeneratedSortInfo, Signature, Spec, atomic, fn, var

        sig = Signature(
            sorts={"Counter": atomic("Counter"), "Nat": atomic("Nat")},
            functions={
                "new": fn("new", [], "Counter"),
                "get_value": fn("get_value", [("c", "Counter")], "Nat"),
                "zero": fn("zero", [], "Nat"),
            },
            predicates={},
            generated_sorts={
                "Counter": GeneratedSortInfo(constructors=("new",), selectors={})
            },
        )
        x = var("x", "Nat")
        # This axiom has no obs(ctor(...)) pattern recognizable by the matcher
        unrecognizable = Axiom(
            label="mystery_axiom",
            formula=pred_app("some_random_pred", x),
        )
        spec = Spec(
            name="TestSpec",
            signature=sig,
            axioms=(unrecognizable,),
        )
        table = build_obligation_table(sig)

        with caplog.at_level(logging.WARNING, logger="alspec.axiom_match"):
            report = match_spec_sync(spec, table, sig)

        assert "mystery_axiom" in report.unmatched_axioms
        assert any("UNMATCHED" in r.message for r in caplog.records)

    def test_collect_pred_names_traverses_all_connectives(self):
        """_collect_pred_names should find preds in nested formulas."""
        p1 = pred_app("pred_a", var("x", "X"))
        p2 = pred_app("pred_b", var("y", "Y"))
        f = implication(
            conjunction(p1),
            Biconditional(p2, p1),
        )
        names = _collect_pred_names(f)
        assert "pred_a" in names
        assert "pred_b" in names

    def test_collect_fn_names_traverses_all_connectives(self):
        """_collect_fn_names should find fn names in nested formulas."""
        f = forall(
            [var("x", "X")],
            eq(
                app("outer_fn", app("inner_fn", var("x", "X"))),
                const("const_fn"),
            ),
        )
        names = _collect_fn_names(f)
        assert "outer_fn" in names
        assert "inner_fn" in names
        assert "const_fn" in names

    def test_match_report_is_frozen(self):
        """MatchReport is a frozen dataclass — direct attribute assignment raises."""
        mod = _load_golden("counter")
        spec = mod.counter_spec()
        table = build_obligation_table(spec.signature)
        report = match_spec_sync(spec, table, spec.signature)
        with pytest.raises((AttributeError, dataclasses.FrozenInstanceError)):
            report.matches = ()  # type: ignore[misc]


class TestInfrastructureAxioms:
    """RC2: Infrastructure axioms on non-generated sorts."""

    def test_geq_zero_base_is_infrastructure(self):
        from alspec import (
    Axiom,
    GeneratedSortInfo,
    Signature,
    Spec,
    atomic,
    const,
    definedness,
    fn,
    forall,
    implication,
    negation,
    pred,
    pred_app,
    var,
)
        from alspec.obligation import build_obligation_table
        from alspec.axiom_match import match_spec_sync, MatchKind

        sig = Signature(
            sorts={"Counter": atomic("Counter"), "Nat": atomic("Nat")},
            functions={
                "zero": fn("zero", [], "Nat"),
                "succ": fn("succ", [("n", "Nat")], "Nat"),
                "new": fn("new", [], "Counter"),
                "inc": fn("inc", [("c", "Counter")], "Counter"),
                "get_cv": fn("get_cv", [("c", "Counter")], "Nat"),
            },
            predicates={
                "geq": pred("geq", [("a", "Nat"), ("b", "Nat")]),
            },
            generated_sorts={
                "Counter": GeneratedSortInfo(constructors=("new", "inc"), selectors={}),
            },
        )
        n = var("n", "Nat")
        spec = Spec(
            name="Test",
            signature=sig,
            axioms=(
                Axiom("geq_zero_base", forall([n], pred_app("geq", n, const("zero")))),
            ),
        )
        table = build_obligation_table(sig)
        report = match_spec_sync(spec, table, sig)
        m = report.matches[0]
        assert m.kind == MatchKind.INFRASTRUCTURE
        assert m.axiom_label == "geq_zero_base"

    def test_infrastructure_with_observer_is_not_infrastructure(self):
        """A formula that uses an observer fn should NOT be INFRASTRUCTURE."""
        from alspec import (
    Axiom,
    GeneratedSortInfo,
    Signature,
    Spec,
    app,
    atomic,
    const,
    definedness,
    fn,
    forall,
    implication,
    negation,
    pred,
    pred_app,
    var,
)
        from alspec.obligation import build_obligation_table
        from alspec.axiom_match import match_spec_sync, MatchKind

        sig = Signature(
            sorts={"S": atomic("S"), "Nat": atomic("Nat")},
            functions={
                "new": fn("new", [], "S"),
                "get": fn("get", [("s", "S")], "Nat"),
                "zero": fn("zero", [], "Nat"),
            },
            predicates={
                "geq": pred("geq", [("a", "Nat"), ("b", "Nat")]),
            },
            generated_sorts={
                "S": GeneratedSortInfo(constructors=("new",), selectors={}),
            },
        )
        s = var("s", "S")
        spec = Spec(
            name="Test",
            signature=sig,
            axioms=(
                # geq(get(s), zero) — uses observer 'get', so NOT infrastructure
                Axiom("not_infra", forall([s], pred_app("geq", app("get", s), const("zero")))),
            ),
        )
        table = build_obligation_table(sig)
        report = match_spec_sync(spec, table, sig)
        m = report.matches[0]
        assert m.kind != MatchKind.INFRASTRUCTURE


class TestDistinctnessAxioms:
    """RC3: No-confusion axioms between constructors."""

    def test_negation_of_constructor_equality_is_distinctness(self):
        from alspec import (
    Axiom,
    GeneratedSortInfo,
    Signature,
    Spec,
    atomic,
    const,
    definedness,
    eq,
    fn,
    implication,
    negation,
    pred_app,
)
        from alspec.obligation import build_obligation_table
        from alspec.axiom_match import match_spec_sync, MatchKind

        sig = Signature(
            sorts={"Color": atomic("Color")},
            functions={
                "red": fn("red", [], "Color"),
                "green": fn("green", [], "Color"),
            },
            predicates={},
            generated_sorts={
                "Color": GeneratedSortInfo(constructors=("red", "green"), selectors={}),
            },
        )
        spec = Spec(
            name="Test",
            signature=sig,
            axioms=(
                Axiom("red_neq_green", negation(eq(const("red"), const("green")))),
            ),
        )
        table = build_obligation_table(sig)
        report = match_spec_sync(spec, table, sig)
        m = report.matches[0]
        assert m.kind == MatchKind.DISTINCTNESS

    def test_same_constructor_negation_is_not_distinctness(self):
        """¬(red = red) is not a valid distinctness axiom."""
        from alspec import (
    Axiom,
    GeneratedSortInfo,
    Signature,
    Spec,
    atomic,
    const,
    definedness,
    eq,
    fn,
    implication,
    negation,
    pred_app,
)
        from alspec.obligation import build_obligation_table
        from alspec.axiom_match import match_spec_sync, MatchKind

        sig = Signature(
            sorts={"Color": atomic("Color")},
            functions={
                "red": fn("red", [], "Color"),
                "green": fn("green", [], "Color"),
            },
            predicates={},
            generated_sorts={
                "Color": GeneratedSortInfo(constructors=("red", "green"), selectors={}),
            },
        )
        spec = Spec(
            name="Test",
            signature=sig,
            axioms=(
                Axiom("red_neq_red", negation(eq(const("red"), const("red")))),
            ),
        )
        table = build_obligation_table(sig)
        report = match_spec_sync(spec, table, sig)
        m = report.matches[0]
        assert m.kind != MatchKind.DISTINCTNESS


class TestBuriedObsCtorPattern:
    """RC4: obs(ctor(...)) nested one level deep in wrapper functions."""

    def test_succ_wrapping_obs_ctor(self):
        """succ(get_cv(decrement(c))) = get_cv(c) should match get_cv × decrement."""
        from alspec import (
    Axiom,
    GeneratedSortInfo,
    Signature,
    Spec,
    app,
    atomic,
    const,
    definedness,
    eq,
    fn,
    forall,
    implication,
    negation,
    pred_app,
    var,
)
        from alspec.obligation import build_obligation_table
        from alspec.axiom_match import match_spec_sync, MatchKind

        sig = Signature(
            sorts={"Counter": atomic("Counter"), "Nat": atomic("Nat")},
            functions={
                "zero": fn("zero", [], "Nat"),
                "succ": fn("succ", [("n", "Nat")], "Nat"),
                "new": fn("new", [], "Counter"),
                "decrement": fn("decrement", [("c", "Counter")], "Counter", total=False),
                "get_cv": fn("get_cv", [("c", "Counter")], "Nat"),
            },
            predicates={},
            generated_sorts={
                "Counter": GeneratedSortInfo(
                    constructors=("new", "decrement"), selectors={}
                ),
            },
        )
        c = var("c", "Counter")
        spec = Spec(
            name="Test",
            signature=sig,
            axioms=(
                Axiom(
                    "get_cv_decrement",
                    forall(
                        [c],
                        implication(
                            definedness(app("decrement", c)),
                            eq(
                                app("succ", app("get_cv", app("decrement", c))),
                                app("get_cv", c),
                            ),
                        ),
                    ),
                ),
            ),
        )
        table = build_obligation_table(sig)
        report = match_spec_sync(spec, table, sig)
        m = report.matches[0]
        assert m.kind in (MatchKind.DIRECT, MatchKind.PRESERVATION), (
            f"Expected DIRECT or PRESERVATION, got {m.kind}: {m.reason}"
        )
        assert any(c.observer_name == "get_cv" and c.constructor_name == "decrement"
                    for c in m.cells)


class TestDefinitionAxioms:
    """RC5: Derived observer definitions (biconditionals)."""

    def test_pred_observer_biconditional_is_definition(self):
        """is_red(l) ↔ eq_color(get_color(l), red) should be DEFINITION."""
        from alspec import (
    Axiom,
    Biconditional,
    GeneratedSortInfo,
    Signature,
    Spec,
    app,
    atomic,
    const,
    definedness,
    fn,
    forall,
    implication,
    negation,
    pred,
    pred_app,
    var,
)
        from alspec.obligation import build_obligation_table
        from alspec.axiom_match import match_spec_sync, MatchKind

        sig = Signature(
            sorts={"Light": atomic("Light"), "Color": atomic("Color")},
            functions={
                "init": fn("init", [], "Light"),
                "advance": fn("advance", [("l", "Light")], "Light"),
                "red": fn("red", [], "Color"),
                "get_color": fn("get_color", [("l", "Light")], "Color"),
            },
            predicates={
                "is_red": pred("is_red", [("l", "Light")]),
                "eq_color": pred("eq_color", [("a", "Color"), ("b", "Color")]),
            },
            generated_sorts={
                "Light": GeneratedSortInfo(
                    constructors=("init", "advance"), selectors={}
                ),
            },
        )
        l = var("l", "Light")
        spec = Spec(
            name="Test",
            signature=sig,
            axioms=(
                Axiom(
                    "is_red_def",
                    forall(
                        [l],
                        Biconditional(
                            pred_app("is_red", l),
                            pred_app("eq_color", app("get_color", l), const("red")),
                        ),
                    ),
                ),
            ),
        )
        table = build_obligation_table(sig)
        report = match_spec_sync(spec, table, sig)
        m = report.matches[0]
        assert m.kind == MatchKind.DEFINITION

    def test_contains_def_lookup_is_definition(self):
        """contains(b, n) ↔ def(lookup(b, n)) should be DEFINITION."""
        from alspec import (
    Axiom,
    Biconditional,
    GeneratedSortInfo,
    Signature,
    Spec,
    app,
    atomic,
    definedness,
    fn,
    forall,
    implication,
    negation,
    pred,
    pred_app,
    var,
)
        from alspec.obligation import build_obligation_table
        from alspec.axiom_match import match_spec_sync, MatchKind

        sig = Signature(
            sorts={"Book": atomic("Book"), "Name": atomic("Name"), "Number": atomic("Number")},
            functions={
                "empty": fn("empty", [], "Book"),
                "add": fn("add", [("b", "Book"), ("n", "Name"), ("num", "Number")], "Book"),
                "lookup": fn("lookup", [("b", "Book"), ("n", "Name")], "Number", total=False),
            },
            predicates={
                "contains": pred("contains", [("b", "Book"), ("n", "Name")]),
                "eq_name": pred("eq_name", [("a", "Name"), ("b", "Name")]),
            },
            generated_sorts={
                "Book": GeneratedSortInfo(constructors=("empty", "add"), selectors={}),
            },
        )
        b = var("b", "Book")
        n = var("n", "Name")
        spec = Spec(
            name="Test",
            signature=sig,
            axioms=(
                Axiom(
                    "contains_def_lookup",
                    forall(
                        [b, n],
                        Biconditional(
                            pred_app("contains", b, n),
                            definedness(app("lookup", b, n)),
                        ),
                    ),
                ),
            ),
        )
        table = build_obligation_table(sig)
        report = match_spec_sync(spec, table, sig)
        m = report.matches[0]
        assert m.kind == MatchKind.DEFINITION

    def test_obs_ctor_biconditional_is_not_definition(self):
        """A biconditional with obs(ctor(...)) should match cells, not DEFINITION."""
        from alspec import (
    Axiom,
    Biconditional,
    GeneratedSortInfo,
    Signature,
    Spec,
    app,
    atomic,
    const,
    definedness,
    fn,
    forall,
    implication,
    negation,
    pred,
    pred_app,
    var,
)
        from alspec.obligation import build_obligation_table
        from alspec.axiom_match import match_spec_sync, MatchKind

        sig = Signature(
            sorts={"Light": atomic("Light"), "Color": atomic("Color")},
            functions={
                "init": fn("init", [], "Light"),
                "advance": fn("advance", [("l", "Light")], "Light"),
                "red": fn("red", [], "Color"),
                "get_color": fn("get_color", [("l", "Light")], "Color"),
            },
            predicates={
                "is_red": pred("is_red", [("l", "Light")]),
                "eq_color": pred("eq_color", [("a", "Color"), ("b", "Color")]),
            },
            generated_sorts={
                "Light": GeneratedSortInfo(
                    constructors=("init", "advance"), selectors={}
                ),
            },
        )
        l = var("l", "Light")
        spec = Spec(
            name="Test",
            signature=sig,
            axioms=(
                # is_red(advance(l)) ↔ ... — has obs(ctor(...)) pattern, should be cell match
                Axiom(
                    "is_red_advance",
                    forall(
                        [l],
                        Biconditional(
                            pred_app("is_red", app("advance", l)),
                            pred_app("eq_color", app("get_color", app("advance", l)), const("red")),
                        ),
                    ),
                ),
            ),
        )
        table = build_obligation_table(sig)
        report = match_spec_sync(spec, table, sig)
        m = report.matches[0]
        # Should match cells, not be classified as DEFINITION
        assert m.kind != MatchKind.DEFINITION
        assert m.kind in (MatchKind.DIRECT, MatchKind.PRESERVATION)


class TestCompositionalObserver:
    """Sprint 2: pred_obs(fn_obs(ctor(...))) compositional observer peeling."""

    def test_is_true_get_q_init(self):
        """is_true(get_q(init)) should match cell get_q × init."""
        from alspec import (
    Axiom,
    Biconditional,
    GeneratedSortInfo,
    Signature,
    Spec,
    app,
    atomic,
    const,
    definedness,
    fn,
    forall,
    implication,
    negation,
    pred,
    pred_app,
    var,
)
        from alspec.obligation import build_obligation_table
        from alspec.axiom_match import match_spec_sync, MatchKind

        sig = Signature(
            sorts={
                "Counter": atomic("Counter"),
                "Bool": atomic("Bool"),
                "Word": atomic("Word"),
            },
            functions={
                "true": fn("true", [], "Bool"),
                "false": fn("false", [], "Bool"),
                "zero": fn("zero", [], "Word"),
                "init": fn("init", [], "Counter"),
                "step": fn("step", [("c", "Counter"), ("cu", "Bool")], "Counter"),
                "get_q": fn("get_q", [("c", "Counter")], "Bool"),
                "get_cv": fn("get_cv", [("c", "Counter")], "Word"),
            },
            predicates={
                "is_true": pred("is_true", [("b", "Bool")]),
                "geq": pred("geq", [("w1", "Word"), ("w2", "Word")]),
            },
            generated_sorts={
                "Counter": GeneratedSortInfo(constructors=("init", "step"), selectors={}),
                "Bool": GeneratedSortInfo(constructors=("true", "false"), selectors={}),
                "Word": GeneratedSortInfo(constructors=("zero",), selectors={}),
            },
        )
        spec = Spec(
            name="Test",
            signature=sig,
            axioms=(
                Axiom(
                    "get_q_init",
                    Biconditional(
                        pred_app("is_true", app("get_q", const("init"))),
                        pred_app("geq", app("get_cv", const("init")), const("zero")),
                    ),
                ),
            ),
        )
        table = build_obligation_table(sig)
        report = match_spec_sync(spec, table, sig)
        m = report.matches[0]
        assert m.kind != MatchKind.UNMATCHED, f"Expected match, got UNMATCHED: {m.reason}"
        assert any(
            c.observer_name == "get_q" and c.constructor_name == "init"
            for c in m.cells
        ), f"Expected get_q × init cell, got {[(c.observer_name, c.constructor_name) for c in m.cells]}"

    def test_negated_is_true_get_q_init(self):
        """¬is_true(get_q(init)) should also match cell get_q × init."""
        from alspec import (
    Axiom,
    GeneratedSortInfo,
    Signature,
    Spec,
    app,
    atomic,
    const,
    definedness,
    fn,
    implication,
    negation,
    pred,
    pred_app,
    var,
)
        from alspec.obligation import build_obligation_table
        from alspec.axiom_match import match_spec_sync, MatchKind

        sig = Signature(
            sorts={
                "Counter": atomic("Counter"),
                "Bool": atomic("Bool"),
            },
            functions={
                "true": fn("true", [], "Bool"),
                "false": fn("false", [], "Bool"),
                "init": fn("init", [], "Counter"),
                "step": fn("step", [("c", "Counter"), ("cu", "Bool")], "Counter"),
                "get_q": fn("get_q", [("c", "Counter")], "Bool"),
            },
            predicates={
                "is_true": pred("is_true", [("b", "Bool")]),
            },
            generated_sorts={
                "Counter": GeneratedSortInfo(constructors=("init", "step"), selectors={}),
                "Bool": GeneratedSortInfo(constructors=("true", "false"), selectors={}),
            },
        )
        spec = Spec(
            name="Test",
            signature=sig,
            axioms=(
                Axiom(
                    "get_q_init_false",
                    negation(pred_app("is_true", app("get_q", const("init")))),
                ),
            ),
        )
        table = build_obligation_table(sig)
        report = match_spec_sync(spec, table, sig)
        m = report.matches[0]
        assert m.kind != MatchKind.UNMATCHED, f"Expected match, got UNMATCHED: {m.reason}"
        assert any(
            c.observer_name == "get_q" and c.constructor_name == "init"
            for c in m.cells
        )

    def test_is_true_get_q_step_with_guards(self):
        """is_true(get_q(step(c, cu))) ↔ ... should match cell get_q × step."""
        from alspec import (
    Axiom,
    Biconditional,
    GeneratedSortInfo,
    Signature,
    Spec,
    app,
    atomic,
    const,
    definedness,
    fn,
    forall,
    implication,
    pred,
    pred_app,
    var,
)
        from alspec.obligation import build_obligation_table
        from alspec.axiom_match import match_spec_sync, MatchKind

        sig = Signature(
            sorts={
                "Counter": atomic("Counter"),
                "Bool": atomic("Bool"),
                "Word": atomic("Word"),
            },
            functions={
                "true": fn("true", [], "Bool"),
                "false": fn("false", [], "Bool"),
                "zero": fn("zero", [], "Word"),
                "init": fn("init", [], "Counter"),
                "step": fn("step", [("c", "Counter"), ("cu", "Bool")], "Counter"),
                "get_q": fn("get_q", [("c", "Counter")], "Bool"),
                "get_cv": fn("get_cv", [("c", "Counter")], "Word"),
                "get_pv": fn("get_pv", [("c", "Counter")], "Word"),
            },
            predicates={
                "is_true": pred("is_true", [("b", "Bool")]),
                "geq": pred("geq", [("w1", "Word"), ("w2", "Word")]),
            },
            generated_sorts={
                "Counter": GeneratedSortInfo(constructors=("init", "step"), selectors={}),
                "Bool": GeneratedSortInfo(constructors=("true", "false"), selectors={}),
                "Word": GeneratedSortInfo(constructors=("zero",), selectors={}),
            },
        )
        c = var("c", "Counter")
        cu = var("cu", "Bool")
        spec = Spec(
            name="Test",
            signature=sig,
            axioms=(
                Axiom(
                    "get_q_step",
                    forall(
                        [c, cu],
                        Biconditional(
                            pred_app("is_true", app("get_q", app("step", c, cu))),
                            pred_app("geq", app("get_cv", app("step", c, cu)),
                                app("get_pv", app("step", c, cu))),
                        ),
                    ),
                ),
            ),
        )
        table = build_obligation_table(sig)
        report = match_spec_sync(spec, table, sig)
        m = report.matches[0]
        assert m.kind != MatchKind.UNMATCHED, f"Expected match, got UNMATCHED: {m.reason}"
        assert any(
            c.observer_name == "get_q" and c.constructor_name == "step"
            for c in m.cells
        )

    def test_direct_pred_obs_still_works(self):
        """alarm_flag(convert_t(d, temp)) should still match directly (no peeling)."""
        from alspec import (
    Axiom,
    Biconditional,
    GeneratedSortInfo,
    Signature,
    Spec,
    app,
    atomic,
    definedness,
    fn,
    forall,
    implication,
    pred,
    pred_app,
    var,
)
        from alspec.obligation import build_obligation_table
        from alspec.axiom_match import match_spec_sync, MatchKind

        sig = Signature(
            sorts={"Device": atomic("Device"), "Temp": atomic("Temp")},
            functions={
                "power_up": fn("power_up", [], "Device"),
                "convert_t": fn("convert_t", [("d", "Device"), ("t", "Temp")], "Device"),
                "get_temp": fn("get_temp", [("d", "Device")], "Temp"),
            },
            predicates={
                "alarm_flag": pred("alarm_flag", [("d", "Device")]),
                "is_hot": pred("is_hot", [("t", "Temp")]),
            },
            generated_sorts={
                "Device": GeneratedSortInfo(
                    constructors=("power_up", "convert_t"), selectors={}
                ),
            },
        )
        d = var("d", "Device")
        t = var("t", "Temp")
        spec = Spec(
            name="Test",
            signature=sig,
            axioms=(
                Axiom(
                    "alarm_convert",
                    forall(
                        [d, t],
                        Biconditional(
                            pred_app("alarm_flag", app("convert_t", d, t)),
                            pred_app("is_hot", app("get_temp", app("convert_t", d, t))),
                        ),
                    ),
                ),
            ),
        )
        table = build_obligation_table(sig)
        report = match_spec_sync(spec, table, sig)
        m = report.matches[0]
        assert m.kind != MatchKind.UNMATCHED
        # Should match alarm_flag × convert_t DIRECTLY (no peeling needed)
        assert any(
            c.observer_name == "alarm_flag" and c.constructor_name == "convert_t"
            for c in m.cells
        )

    def test_non_observer_wrapping_MATCHES(self):
        """geq(get_highest_bid(reveal(a)), ...) should now match via peeling.

        geq is PredKind.OTHER, but because we now try extracting from all PredApps
        (Fix C), it finds the buried get_highest_bid × reveal.
        """
        from alspec import (
    Axiom,
    GeneratedSortInfo,
    Signature,
    Spec,
    app,
    atomic,
    definedness,
    fn,
    forall,
    implication,
    pred,
    pred_app,
    var,
)
        from alspec.obligation import build_obligation_table
        from alspec.axiom_match import match_spec_sync, MatchKind

        sig = Signature(
            sorts={
                "Auction": atomic("Auction"),
                "Amount": atomic("Amount"),
            },
            functions={
                "create": fn("create", [("r", "Amount")], "Auction"),
                "reveal": fn("reveal", [("a", "Auction")], "Auction"),
                "get_highest_bid": fn("get_highest_bid", [("a", "Auction")], "Amount", total=False),
                "get_reserve": fn("get_reserve", [("a", "Auction")], "Amount"),
            },
            predicates={
                # geq over Amount — Amount is NOT generated, so geq is PredKind.OTHER
                "geq": pred("geq", [("a1", "Amount"), ("a2", "Amount")]),
            },
            generated_sorts={
                "Auction": GeneratedSortInfo(
                    constructors=("create", "reveal"), selectors={}
                ),
            },
        )
        a = var("a", "Auction")
        spec = Spec(
            name="Test",
            signature=sig,
            axioms=(
                Axiom(
                    "hbid_reveal_logic",
                    forall(
                        [a],
                        implication(
                            definedness(app("get_highest_bid", app("reveal", a))),
                            pred_app("geq", app("get_highest_bid", app("reveal", a)),
                                app("get_reserve", a)),
                        ),
                    ),
                ),
            ),
        )
        table = build_obligation_table(sig)
        report = match_spec_sync(spec, table, sig)
        m = report.matches[0]
        # geq is PredKind.OTHER — but Fix C enables peeling through it.
        assert m.kind != MatchKind.UNMATCHED
        assert any(
            c.observer_name == "get_highest_bid" and c.constructor_name == "reveal"
            for c in m.cells
        )

    def test_non_observer_pred_with_buried_obs_ctor(self):
        """PredApp(OTHER, (obs(ctor(...)),)) should extract the inner obs×ctor."""
        from alspec import PredApp, var, app
        from alspec.obligation import FnRole, FnKind, PredRole, PredKind
        from alspec.axiom_match import _find_obs_ctor
        fn_roles = {
            "init": FnRole("init", FnKind.CONSTRUCTOR, "CTU"),
            "get_q": FnRole("get_q", FnKind.OBSERVER, "CTU"),
            "zero": FnRole("zero", FnKind.CONSTANT, None),
        }
        pred_roles = {
            "is_true": PredRole("is_true", PredKind.OTHER, None),
        }
        # is_true(get_q(init(w))) — is_true is OTHER but get_q(init) is obs×ctor
        w = var("w", "Word")
        f = pred_app("is_true", app("get_q", app("init", w)))
        result = _find_obs_ctor(f, fn_roles, pred_roles)
        assert result == ("get_q", False, "init")

    def test_non_observer_pred_second_arg_obs_ctor(self):
        """obs(ctor) in second arg of non-observer pred should also match."""
        from alspec import PredApp, var, app
        from alspec.obligation import FnRole, FnKind, PredRole, PredKind
        from alspec.axiom_match import _find_obs_ctor
        fn_roles = {
            "reveal": FnRole("reveal", FnKind.CONSTRUCTOR, "Auction"),
            "get_highest_bid": FnRole("get_highest_bid", FnKind.OBSERVER, "Auction"),
            "get_reserve": FnRole("get_reserve", FnKind.OBSERVER, "Auction"),
        }
        pred_roles = {
            "geq": PredRole("geq", PredKind.OTHER, None),
        }
        a = var("a", "Auction")
        # geq(get_highest_bid(reveal(a)), get_reserve(a))
        # First arg has obs×ctor, second has obs(var) — first should match
        f = pred_app("geq", app("get_highest_bid", app("reveal", a)),
            app("get_reserve", a))
        result = _find_obs_ctor(f, fn_roles, pred_roles)
        assert result == ("get_highest_bid", False, "reveal")

    def test_biconditional_with_non_observer_pred_both_sides(self):
        """iff(is_true(get_q(init(w))), ge(zero, w)) should find get_q×init."""
        from alspec import Biconditional, PredApp, var, app, const
        from alspec.obligation import FnRole, FnKind, PredRole, PredKind
        from alspec.axiom_match import _find_obs_ctor
        fn_roles = {
            "init": FnRole("init", FnKind.CONSTRUCTOR, "CTU"),
            "get_q": FnRole("get_q", FnKind.OBSERVER, "CTU"),
            "zero": FnRole("zero", FnKind.CONSTANT, None),
        }
        pred_roles = {
            "is_true": PredRole("is_true", PredKind.OTHER, None),
            "ge": PredRole("ge", PredKind.OTHER, None),
        }
        w = var("w", "Word")
        f = Biconditional(
            pred_app("is_true", app("get_q", app("init", w))),
            pred_app("ge", const("zero"), w),
        )
        result = _find_obs_ctor(f, fn_roles, pred_roles)
        assert result == ("get_q", False, "init")


class TestHasObserverOnVariable:
    """Unit tests for the _has_observer_on_variable helper."""

    def test_equation_with_fn_observer(self):
        from alspec import var, app, const, eq
        from alspec.obligation import FnRole, FnKind, PredRole
        from alspec.axiom_match import _has_observer_on_variable

        fn_roles = {
            "get_status": FnRole("get_status", FnKind.OBSERVER, "Thermostat"),
            "on": FnRole("on", FnKind.CONSTANT, None),
        }
        pred_roles: dict[str, PredRole] = {}
        th = var("th", "Thermostat")
        f = eq(app("get_status", th), const("on"))
        assert _has_observer_on_variable(f, fn_roles, pred_roles) is True

    def test_equation_with_ctor_root_is_false(self):
        """obs(ctor(...)) should NOT match — that's a cell axiom."""
        from alspec import var, app, const, eq
        from alspec.obligation import FnRole, FnKind, PredRole
        from alspec.axiom_match import _has_observer_on_variable

        fn_roles = {
            "get_status": FnRole("get_status", FnKind.OBSERVER, "Thermostat"),
            "create": FnRole("create", FnKind.CONSTRUCTOR, "Thermostat"),
            "on": FnRole("on", FnKind.CONSTANT, None),
        }
        pred_roles: dict[str, PredRole] = {}
        t = var("t", "Temp")
        # obs(ctor(t)) = on — this is a cell axiom, not a definition
        # But _has_observer_on_variable only checks if first arg is Var
        # The ctor check is handled by _is_conclusion_definition calling _find_obs_ctor first
        f = eq(app("get_status", app("create", t)), const("on"))
        # get_status's first arg is FnApp("create",...), not Var → False
        assert _has_observer_on_variable(f, fn_roles, pred_roles) is False

    def test_negated_pred_observer(self):
        from alspec import var, pred_app, negation
        from alspec.obligation import FnRole, PredRole, PredKind
        from alspec.axiom_match import _has_observer_on_variable

        fn_roles: dict[str, FnRole] = {}
        pred_roles = {"is_active": PredRole("is_active", PredKind.OBSERVER, "Device")}
        d = var("d", "Device")
        f = negation(pred_app("is_active", d))
        assert _has_observer_on_variable(f, fn_roles, pred_roles) is True

    def test_non_observer_pred_is_false(self):
        from alspec import var, pred_app
        from alspec.obligation import FnRole, PredRole, PredKind
        from alspec.axiom_match import _has_observer_on_variable

        fn_roles: dict[str, FnRole] = {}
        pred_roles = {"lt": PredRole("lt", PredKind.OTHER, None)}
        t = var("t", "Temp")
        f = pred_app("lt", t, t)
        assert _has_observer_on_variable(f, fn_roles, pred_roles) is False


class TestImplicationFormDefinitions:
    """Implication-form definitions should be classified as DEFINITION, not UNMATCHED."""

    def test_guarded_equation_definition(self):
        """is_heating(th) → get_status(th) = on should be DEFINITION."""
        from alspec import (
            Axiom, Signature, Spec, atomic, fn, pred, var, app, const,
            forall, implication, eq, pred_app, GeneratedSortInfo,
        )
        from alspec.obligation import build_obligation_table
        from alspec.axiom_match import match_spec_sync, MatchKind

        sig = Signature(
            sorts={
                "Thermostat": atomic("Thermostat"),
                "Temp": atomic("Temp"),
                "Status": atomic("Status"),
            },
            functions={
                "on": fn("on", [], "Status"),
                "off": fn("off", [], "Status"),
                "create": fn("create", [("t", "Temp")], "Thermostat"),
                "set_target": fn("set_target", [("th", "Thermostat"), ("t", "Temp")], "Thermostat"),
                "get_target": fn("get_target", [("th", "Thermostat")], "Temp"),
                "get_current": fn("get_current", [("th", "Thermostat")], "Temp"),
                "get_status": fn("get_status", [("th", "Thermostat")], "Status"),
            },
            predicates={
                "lt": pred("lt", [("a", "Temp"), ("b", "Temp")]),
                "is_heating": pred("is_heating", [("th", "Thermostat")]),
            },
            generated_sorts={
                "Thermostat": GeneratedSortInfo(
                    constructors=("create", "set_target"),
                    selectors={"create": {"get_target": "Temp", "get_current": "Temp"},
                               "set_target": {"get_target": "Temp"}},
                ),
                "Status": GeneratedSortInfo(constructors=("on", "off"), selectors={}),
            },
        )

        th = var("th", "Thermostat")
        spec = Spec(
            name="Test",
            signature=sig,
            axioms=(
                # Implication-form definition: guard → obs(var) = val
                Axiom("get_status_def_on", forall([th],
                    implication(
                        pred_app("is_heating", th),
                        eq(app("get_status", th), const("on")),
                    ))),
                Axiom("get_status_def_off", forall([th],
                    implication(
                        negation(pred_app("is_heating", th)),
                        eq(app("get_status", th), const("off")),
                    ))),
            ),
        )

        table = build_obligation_table(sig)
        report = match_spec_sync(spec, table, sig)

        for m in report.matches:
            assert m.kind == MatchKind.DEFINITION, (
                f"Axiom {m.axiom_label!r} expected DEFINITION, got {m.kind.value}: {m.reason}"
            )
        assert len(report.unmatched_axioms) == 0

    def test_guarded_predicate_definition(self):
        """guard → pred_app(obs, var) should be DEFINITION."""
        from alspec import (
            Axiom, Signature, Spec, atomic, fn, pred, var, app, const,
            forall, implication, pred_app, negation, GeneratedSortInfo,
        )
        from alspec.obligation import build_obligation_table
        from alspec.axiom_match import match_spec_sync, MatchKind

        sig = Signature(
            sorts={
                "Device": atomic("Device"),
                "Temp": atomic("Temp"),
            },
            functions={
                "power_on": fn("power_on", [], "Device"),
                "cycle": fn("cycle", [("d", "Device"), ("t", "Temp")], "Device"),
                "get_temp": fn("get_temp", [("d", "Device")], "Temp"),
            },
            predicates={
                "is_active": pred("is_active", [("d", "Device")]),
                "has_reading": pred("has_reading", [("d", "Device")]),
            },
            generated_sorts={
                "Device": GeneratedSortInfo(
                    constructors=("power_on", "cycle"), selectors={},
                ),
            },
        )

        d = var("d", "Device")
        spec = Spec(
            name="Test",
            signature=sig,
            axioms=(
                # guard → pred observer on variable
                Axiom("has_reading_from_active", forall([d],
                    implication(
                        pred_app("is_active", d),
                        pred_app("has_reading", d),
                    ))),
            ),
        )

        table = build_obligation_table(sig)
        report = match_spec_sync(spec, table, sig)

        m = report.matches[0]
        assert m.kind == MatchKind.DEFINITION, (
            f"Expected DEFINITION, got {m.kind.value}: {m.reason}"
        )
