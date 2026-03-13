"""Round-trip tests for serialization, including Biconditional."""

from alspec import Axiom, PredApp, Signature, Spec, dumps, loads
from alspec.helpers import atomic, forall, iff, pred, pred_app, var
from alspec.terms import Term


def test_biconditional_round_trip() -> None:
    x = var("x", "Elem")
    y = var("y", "Elem")
    def p(a: Term) -> PredApp:
        return pred_app("p", a)

    sig = Signature(
        sorts={"Elem": atomic("Elem")},
        functions={},
        predicates={"p": pred("p", [("x", "Elem")])},
    )
    spec = Spec(
        name="BiconditionalTest",
        signature=sig,
        axioms=(Axiom("iff_test", forall([x, y], iff(p(x), p(y)))),),
    )
    json_str = dumps(spec)
    restored = loads(json_str)
    assert restored == spec


def test_all_basis_round_trip() -> None:
    from alspec.basis import ALL_BASIS_SPECS

    for spec_fn in ALL_BASIS_SPECS:
        sp = spec_fn()
        json_str = dumps(sp)
        restored = loads(json_str)
        assert restored == sp, f"Round-trip failed for {sp.name}"


class TestGeneratedSortsRoundTrip:
    """Verify generated_sorts survive JSON round-trip."""

    def _test_sig(self) -> Signature:
        from alspec.helpers import atomic, fn
        from alspec.signature import GeneratedSortInfo, Signature

        return Signature(
            sorts={"Stack": atomic("Stack"), "Elem": atomic("Elem")},
            functions={
                "new": fn("new", [], "Stack"),
                "push": fn("push", [("S", "Stack"), ("e", "Elem")], "Stack"),
                "top": fn("top", [("S", "Stack")], "Elem", total=False),
            },
            predicates={},
            generated_sorts={
                "Stack": GeneratedSortInfo(
                    constructors=("new", "push"),
                    selectors={"push": {"top": "e"}},
                )
            },
        )

    def test_signature_with_generated_sorts_round_trips(self):
        """A Signature with non-empty generated_sorts must round-trip perfectly."""
        from alspec.serialization import signature_from_json, signature_to_json

        sig = self._test_sig()

        # Precondition: this sig actually has generated_sorts
        assert len(sig.generated_sorts) > 0

        # Round-trip
        json_data = signature_to_json(sig)
        recovered = signature_from_json(json_data)

        # Verify generated_sorts match
        assert set(recovered.generated_sorts.keys()) == set(sig.generated_sorts.keys())
        for sort_name, info in sig.generated_sorts.items():
            rec_info = recovered.generated_sorts[sort_name]
            assert rec_info.constructors == info.constructors
            assert dict(rec_info.selectors) == dict(info.selectors)

    def test_spec_with_generated_sorts_round_trips(self):
        """Full Spec round-trip preserves generated_sorts."""
        from alspec import Spec
        from alspec.serialization import dumps, loads

        sig = self._test_sig()
        spec = Spec(name="TestStack", signature=sig, axioms=())

        json_str = dumps(spec)
        recovered = loads(json_str)

        assert set(recovered.signature.generated_sorts.keys()) == set(
            spec.signature.generated_sorts.keys()
        )
        for sort_name in spec.signature.generated_sorts:
            orig = spec.signature.generated_sorts[sort_name]
            rec = recovered.signature.generated_sorts[sort_name]
            assert rec.constructors == orig.constructors

    def test_signature_without_generated_sorts_round_trips(self):
        """A Signature with empty generated_sorts still round-trips cleanly."""
        from alspec.serialization import signature_from_json, signature_to_json
        from alspec.signature import Signature
        from alspec.sorts import AtomicSort, SortRef

        sig = Signature(
            sorts={"Nat": AtomicSort(name=SortRef("Nat"))},
            functions={},
            predicates={},
        )
        assert len(sig.generated_sorts) == 0

        json_data = signature_to_json(sig)
        recovered = signature_from_json(json_data)
        assert len(recovered.generated_sorts) == 0

    def test_obligation_table_builds_from_round_tripped_signature(self):
        """The critical integration test: can we build an obligation table from a round-tripped sig?"""
        from alspec.obligation import build_obligation_table
        from alspec.serialization import signature_from_json, signature_to_json

        sig = self._test_sig()

        # Build table from original
        table_orig = build_obligation_table(sig)

        # Round-trip the signature
        json_data = signature_to_json(sig)
        recovered_sig = signature_from_json(json_data)

        # Build table from recovered — must produce same structure
        table_recovered = build_obligation_table(recovered_sig)

        assert len(table_orig.cells) == len(table_recovered.cells)
        # Cell keys (observer_name, constructor_name) should match
        orig_keys = {(c.observer_name, c.constructor_name) for c in table_orig.cells}
        rec_keys = {(c.observer_name, c.constructor_name) for c in table_recovered.cells}
        assert orig_keys == rec_keys
