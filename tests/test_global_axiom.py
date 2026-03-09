"""Tests for GLOBAL axiom recognition in the matcher."""

import pytest

from alspec import (
    Axiom,
    GeneratedSortInfo,
    MatchKind,
    Signature,
    Spec,
    atomic,
    fn,
    forall,
    match_spec_sync,
    negation,
    pred,
    pred_app,
    var,
    eq,
    app,
    const,
    definedness,
    implication,
)
from alspec.obligation import build_obligation_table


def _make_deque_sig() -> Signature:
    """Minimal Deque signature with is_full predicate observer."""
    return Signature(
        sorts={
            "Deque": atomic("Deque"),
            "Elem": atomic("Elem"),
            "Nat": atomic("Nat"),
        },
        functions={
            "empty": fn("empty", [], "Deque"),
            "append": fn("append", [("d", "Deque"), ("e", "Elem")], "Deque"),
            "size": fn("size", [("d", "Deque")], "Nat"),
        },
        predicates={
            "is_full": pred("is_full", [("d", "Deque")]),
        },
        generated_sorts={
            "Deque": GeneratedSortInfo(
                constructors=("empty", "append"),
                selectors={},
            ),
        },
    )


class TestGlobalAxiomRecognition:
    """Test that unconditional universal axioms over generated sorts
    are recognized as GLOBAL and cover all cells for the observer."""

    def test_predicate_observer_global(self):
        """∀d:Deque. ¬is_full(d) should cover all is_full cells."""
        sig = _make_deque_sig()
        table = build_obligation_table(sig)

        d = var("d", "Deque")
        axiom = Axiom(
            label="is_full_global",
            formula=forall([d], negation(pred_app("is_full", d))),
        )
        # Need at least one other axiom to make a valid spec
        size_empty = Axiom(
            label="size_empty",
            formula=forall([d], eq(app("size", const("empty")), const("zero"))),
        )

        spec = Spec(name="Deque", signature=sig, axioms=(axiom, size_empty))
        report = match_spec_sync(spec, table, sig)

        # Find the match for our global axiom
        global_match = next(m for m in report.matches if m.axiom_label == "is_full_global")
        assert global_match.kind == MatchKind.GLOBAL

        # It should cover all cells for is_full
        is_full_cells = [c for c in table.cells if c.observer_name == "is_full"]
        assert len(global_match.cells) == len(is_full_cells)
        assert set(global_match.cells) == set(is_full_cells)

    def test_function_observer_global(self):
        """∀d:Deque. size(d) = zero should be GLOBAL for size."""
        sig = _make_deque_sig()
        # Add a zero constant for the equation RHS
        sig_with_zero = Signature(
            sorts=sig.sorts,
            functions={**sig.functions, "zero": fn("zero", [], "Nat")},
            predicates=sig.predicates,
            generated_sorts=sig.generated_sorts,
        )
        table = build_obligation_table(sig_with_zero)

        d = var("d", "Deque")
        axiom = Axiom(
            label="size_always_zero",
            formula=forall([d], eq(app("size", d), const("zero"))),
        )
        spec = Spec(name="Deque", signature=sig_with_zero, axioms=(axiom,))
        report = match_spec_sync(spec, table, sig_with_zero)

        global_match = next(m for m in report.matches if m.axiom_label == "size_always_zero")
        assert global_match.kind == MatchKind.GLOBAL

        size_cells = [c for c in table.cells if c.observer_name == "size"]
        assert len(global_match.cells) == len(size_cells)

    def test_guarded_axiom_not_global(self):
        """A guarded axiom (with implication) should NOT be GLOBAL — should be DEFINITION."""
        sig = _make_deque_sig()
        # Add a status observer and a constant for the guard
        sig_ext = Signature(
            sorts={**sig.sorts, "Status": atomic("Status")},
            functions={
                **sig.functions,
                "status": fn("status", [("d", "Deque")], "Status"),
                "revealed": fn("revealed", [], "Status"),
            },
            predicates=sig.predicates,
            generated_sorts=sig.generated_sorts,
        )
        table = build_obligation_table(sig_ext)

        d = var("d", "Deque")
        # ∀d:Deque. status(d) ≠ revealed → ¬is_full(d)
        axiom = Axiom(
            label="guarded_is_full",
            formula=forall(
                [d],
                implication(
                    negation(eq(app("status", d), const("revealed"))),
                    negation(pred_app("is_full", d)),
                ),
            ),
        )
        spec = Spec(name="Deque", signature=sig_ext, axioms=(axiom,))
        report = match_spec_sync(spec, table, sig_ext)

        guarded_match = next(m for m in report.matches if m.axiom_label == "guarded_is_full")
        # Should NOT be GLOBAL — it has a guard
        assert guarded_match.kind != MatchKind.GLOBAL

    def test_definedness_global(self):
        """∀d:Deque. ¬def(size(d)) should be GLOBAL for size."""
        sig = _make_deque_sig()
        table = build_obligation_table(sig)

        d = var("d", "Deque")
        axiom = Axiom(
            label="size_undef_global",
            formula=forall([d], negation(definedness(app("size", d)))),
        )
        spec = Spec(name="Deque", signature=sig, axioms=(axiom,))
        report = match_spec_sync(spec, table, sig)

        global_match = next(m for m in report.matches if m.axiom_label == "size_undef_global")
        assert global_match.kind == MatchKind.GLOBAL

    def test_per_constructor_still_works(self):
        """Ensure normal per-constructor axioms still match as DIRECT."""
        sig = _make_deque_sig()
        table = build_obligation_table(sig)

        axiom = Axiom(
            label="is_full_empty",
            formula=negation(pred_app("is_full", const("empty"))),
        )
        spec = Spec(name="Deque", signature=sig, axioms=(axiom,))
        report = match_spec_sync(spec, table, sig)

        direct_match = next(m for m in report.matches if m.axiom_label == "is_full_empty")
        assert direct_match.kind == MatchKind.DIRECT

    def test_non_generated_sort_var_not_global(self):
        """An observer on a Var of a NON-generated sort should NOT be GLOBAL."""
        sig = _make_deque_sig()
        # Add a helper predicate on Elem (not a generated sort)
        sig_ext = Signature(
            sorts=sig.sorts,
            functions=sig.functions,
            predicates={**sig.predicates, "is_special": pred("is_special", [("e", "Elem")])},
            generated_sorts=sig.generated_sorts,
        )
        table = build_obligation_table(sig_ext)

        e = var("e", "Elem")
        axiom = Axiom(
            label="special_global",
            formula=forall([e], negation(pred_app("is_special", e))),
        )
        spec = Spec(name="Deque", signature=sig_ext, axioms=(axiom,))
        report = match_spec_sync(spec, table, sig_ext)

        special_match = next(m for m in report.matches if m.axiom_label == "special_global")
        # is_special is on Elem, not a generated sort, so no obligation cells exist.
        # It should NOT be GLOBAL. It will be DEFINITION or INFRASTRUCTURE.
        assert special_match.kind != MatchKind.GLOBAL
