"""Round-trip tests for serialization, including Biconditional."""

from alspec import Axiom, PredApp, Signature, Spec, dumps, loads
from alspec.helpers import atomic, forall, iff, pred, var
from alspec.terms import Term


def test_biconditional_round_trip() -> None:
    x = var("x", "Elem")
    y = var("y", "Elem")
    def p(a: Term) -> PredApp:
        return PredApp("p", (a,))

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
