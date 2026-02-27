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
    # No warnings expected after removing all advisory checks
    assert not result.warnings


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


def test_duplicate_axiom_labels() -> None:
    sig = get_base_sig()
    ax1 = Axiom(label="dup", formula=Equation(FnApp("zero", ()), FnApp("zero", ())))
    ax2 = Axiom(label="dup", formula=Equation(FnApp("zero", ()), FnApp("zero", ())))
    spec = Spec("Test", sig, (ax1, ax2))
    res = check_spec(spec)
    assert any(e.check == "duplicate_axiom_labels" for e in res.errors)


def test_minimal_bad_spec_errors() -> None:
    """Programmatic bad spec: wrong sort ref, undeclared fn, mismatched equation sorts."""
    # wrong sort reference in function declaration
    sig_bad_sort = Signature(
        sorts={"Nat": AtomicSort(SortRef("Nat"))},
        functions={"f": FnSymbol("f", (FnParam("x", SortRef("Ghost")),), SortRef("Nat"))},
        predicates={},
    )
    res = check_spec(Spec("BadSortRef", sig_bad_sort, ()))
    assert any(e.check == "sort_resolved" for e in res.errors), (
        "Expected sort_resolved error for undeclared param sort"
    )

    # undeclared function in axiom
    sig = get_base_sig()
    ax_undecl = Axiom(
        label="undecl",
        formula=Equation(FnApp("ghost_fn", ()), FnApp("zero", ())),
    )
    res2 = check_spec(Spec("UndeclFn", sig, (ax_undecl,)))
    assert any(e.check == "fn_declared" for e in res2.errors), (
        "Expected fn_declared error for ghost_fn"
    )

    # mismatched equation sorts: Nat = Bool
    ax_mismatch = Axiom(
        label="mismatch",
        formula=Equation(
            FnApp("zero", ()),
            FnApp("is_zero", (FnApp("zero", ()),)),
        ),
    )
    res3 = check_spec(Spec("SortMismatch", sig, (ax_mismatch,)))
    assert any(e.check == "equation_sort_match" for e in res3.errors), (
        "Expected equation_sort_match error for Nat=Bool"
    )


def test_no_advisory_warnings_on_valid_spec() -> None:
    """A valid spec with unused quantifier vars, quantifier-free axioms, etc.
    must produce zero warnings — the advisory checks are gone."""
    sig = get_base_sig()
    # quantifier with a variable that is bound but not used in body
    x = Var("x", SortRef("Nat"))
    ax = Axiom(
        label="unused_var_axiom",
        formula=UniversalQuant(
            variables=(x,),
            body=Equation(FnApp("zero", ()), FnApp("zero", ())),
        ),
    )
    spec = Spec("AdvisoryFree", sig, (ax,))
    res = check_spec(spec)
    assert not res.warnings, f"Expected no warnings, got: {res.warnings}"
