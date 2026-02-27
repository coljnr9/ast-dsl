from alspec.check import check_spec
from alspec.signature import FnParam, FnSymbol, PredSymbol, Signature, Totality
from alspec.sorts import (
    AtomicSort,
    SortRef,
)
from alspec.spec import Axiom, Spec
from alspec.terms import (
    Equation,
    FnApp,
    UniversalQuant,
    Var,
)


def get_base_sig() -> Signature:
    return Signature(
        sorts={"Nat": AtomicSort(SortRef("Nat")), "Bool": AtomicSort(SortRef("Bool"))},
        functions={
            "zero": FnSymbol("zero", (), SortRef("Nat")),
            "suc": FnSymbol("suc", (FnParam("n", SortRef("Nat")),), SortRef("Nat")),
            "add": FnSymbol(
                "add",
                (FnParam("a", SortRef("Nat")), FnParam("b", SortRef("Nat"))),
                SortRef("Nat"),
            ),
            "is_zero": FnSymbol(
                "is_zero", (FnParam("n", SortRef("Nat")),), SortRef("Bool")
            ),
        },
        predicates={
            "leq": PredSymbol(
                "leq", (FnParam("a", SortRef("Nat")), FnParam("b", SortRef("Nat")))
            )
        },
    )


def test_valid_spec() -> None:
    sig = get_base_sig()
    x = Var("x", SortRef("Nat"))
    ax = Axiom(
        label="add_zero",
        formula=UniversalQuant(
            variables=(x,),
            body=Equation(lhs=FnApp("add", (x, FnApp("zero", ()))), rhs=x),
        ),
    )
    spec = Spec("TestSpec", sig, (ax,))
    result = check_spec(spec)
    assert result.is_well_formed
    assert not result.errors


def test_sort_resolved() -> None:
    sig = Signature(
        sorts={"Nat": AtomicSort(SortRef("Nat"))},
        functions={"bad": FnSymbol("bad", (), SortRef("Unknown"))},
        predicates={},
    )
    spec = Spec("Test", sig, ())
    res = check_spec(spec)
    assert not res.is_well_formed
    assert any(e.check == "sort_resolved" for e in res.errors)


def test_sort_name_consistency() -> None:
    sig = Signature(
        sorts={"Nat": AtomicSort(SortRef("BadName"))}, functions={}, predicates={}
    )
    spec = Spec("Test", sig, ())
    res = check_spec(spec)
    assert not res.is_well_formed
    assert any(e.check == "sort_name_consistency" for e in res.errors)


def test_no_empty_sorts() -> None:
    sig = Signature(
        sorts={"Useless": AtomicSort(SortRef("Useless"))}, functions={}, predicates={}
    )
    spec = Spec("Test", sig, ())
    res = check_spec(spec)
    assert any(w.check == "no_empty_sorts" for w in res.warnings)


def test_no_name_collisions() -> None:
    sig = Signature(
        sorts={"x": AtomicSort(SortRef("x"))},
        functions={"x": FnSymbol("x", (), SortRef("x"))},
        predicates={},
    )
    spec = Spec("Test", sig, ())
    res = check_spec(spec)
    assert any(e.check == "no_name_collisions" for e in res.errors)


def test_fn_declared() -> None:
    sig = get_base_sig()
    ax = Axiom(
        label="bad_fn", formula=Equation(FnApp("unknown", ()), FnApp("zero", ()))
    )
    spec = Spec("Test", sig, (ax,))
    res = check_spec(spec)
    assert any(e.check == "fn_declared" for e in res.errors)


def test_fn_arity() -> None:
    sig = get_base_sig()
    ax = Axiom(
        label="bad_arity",
        formula=Equation(
            FnApp("suc", (FnApp("zero", ()), FnApp("zero", ()))), FnApp("zero", ())
        ),
    )
    spec = Spec("Test", sig, (ax,))
    res = check_spec(spec)
    assert any(e.check == "fn_arity" for e in res.errors)


def test_fn_arg_sorts() -> None:
    sig = get_base_sig()
    ax = Axiom(
        label="bad_sort",
        formula=Equation(
            FnApp("suc", (FnApp("is_zero", (FnApp("zero", ()),)),)), FnApp("zero", ())
        ),  # bool passed to nat
    )
    spec = Spec("Test", sig, (ax,))
    res = check_spec(spec)
    assert any(e.check == "fn_arg_sorts" for e in res.errors)


def test_equation_sort_match() -> None:
    sig = get_base_sig()
    ax = Axiom(
        label="bad_eq",
        formula=Equation(
            FnApp("zero", ()), FnApp("is_zero", (FnApp("zero", ()),))
        ),  # nat = bool
    )
    spec = Spec("Test", sig, (ax,))
    res = check_spec(spec)
    assert any(e.check == "equation_sort_match" for e in res.errors)


def test_var_bound() -> None:
    sig = get_base_sig()
    ax = Axiom(
        label="unbound", formula=Equation(Var("x", SortRef("Nat")), FnApp("zero", ()))
    )
    spec = Spec("Test", sig, (ax,))
    res = check_spec(spec)
    assert any(e.check == "var_bound" for e in res.errors)


def test_var_sort_consistent() -> None:
    sig = get_base_sig()
    v1 = Var("x", SortRef("Nat"))
    v2 = Var("x", SortRef("Bool"))
    ax = Axiom(
        label="inconsistent",
        formula=UniversalQuant(
            variables=(v1, v2), body=Equation(FnApp("zero", ()), FnApp("zero", ()))
        ),
    )
    spec = Spec("Test", sig, (ax,))
    res = check_spec(spec)
    assert any(e.check == "var_sort_consistent" for e in res.errors)


def test_var_used() -> None:
    sig = get_base_sig()
    v = Var("x", SortRef("Nat"))
    ax = Axiom(
        label="unused",
        formula=UniversalQuant(
            variables=(v,), body=Equation(FnApp("zero", ()), FnApp("zero", ()))
        ),
    )
    spec = Spec("Test", sig, (ax,))
    res = check_spec(spec)
    assert any(w.check == "var_used" for w in res.warnings)


def test_obligation_coverage() -> None:
    sig = Signature(
        sorts={"T": AtomicSort(SortRef("T")), "S": AtomicSort(SortRef("S"))},
        functions={
            "con": FnSymbol("con", (), SortRef("T")),
            "obs": FnSymbol(
                "obs", (FnParam("t", SortRef("T")),), SortRef("S"), Totality.TOTAL
            ),
            "obs_partial": FnSymbol(
                "obs_partial",
                (FnParam("t", SortRef("T")),),
                SortRef("S"),
                Totality.PARTIAL,
            ),
        },
        predicates={},
    )
    # no axioms mapping obs(con())
    spec = Spec("Test", sig, ())
    res = check_spec(spec)
    warnings = [w for w in res.warnings if w.check == "obligation_coverage"]
    assert len(warnings) == 1
    assert "Total observer" in warnings[0].message
    assert "obs" in warnings[0].message
    # No warning for obs_partial


def test_trivial_axiom() -> None:
    sig = get_base_sig()
    v = Var("x", SortRef("Nat"))
    ax = Axiom(
        label="tautology", formula=UniversalQuant(variables=(v,), body=Equation(v, v))
    )
    spec = Spec("Test", sig, (ax,))
    res = check_spec(spec)
    assert any(w.check == "trivial_axiom" for w in res.warnings)


def test_duplicate_axiom_labels() -> None:
    sig = get_base_sig()
    ax1 = Axiom(label="dup", formula=Equation(FnApp("zero", ()), FnApp("zero", ())))
    ax2 = Axiom(label="dup", formula=Equation(FnApp("zero", ()), FnApp("zero", ())))
    spec = Spec("Test", sig, (ax1, ax2))
    res = check_spec(spec)
    assert any(e.check == "duplicate_axiom_labels" for e in res.errors)
