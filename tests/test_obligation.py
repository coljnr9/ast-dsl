class TestClassifyPredicatesEqualityOnGeneratedSort:
    """RC1: eq_pred on a generated sort must be EQUALITY, not OBSERVER."""

    def test_eq_bool_on_generated_bool(self):
        """eq_bool should be EQUALITY even when Bool is a generated sort."""
        from alspec import Signature, GeneratedSortInfo, atomic, fn, pred
        from alspec.obligation import classify_predicates, PredKind

        sig = Signature(
            sorts={"Light": atomic("Light"), "Bool": atomic("Bool")},
            functions={
                "true": fn("true", [], "Bool"),
                "false": fn("false", [], "Bool"),
                "init": fn("init", [], "Light"),
                "advance": fn("advance", [("l", "Light")], "Light"),
            },
            predicates={
                "eq_bool": pred("eq_bool", [("a", "Bool"), ("b", "Bool")]),
                "is_on": pred("is_on", [("l", "Light")]),
            },
            generated_sorts={
                "Bool": GeneratedSortInfo(constructors=("true", "false"), selectors={}),
                "Light": GeneratedSortInfo(constructors=("init", "advance"), selectors={}),
            },
        )
        roles = classify_predicates(sig)
        assert roles["eq_bool"].kind == PredKind.EQUALITY
        assert roles["eq_bool"].sort == "Bool"
        # is_on remains an observer
        assert roles["is_on"].kind == PredKind.OBSERVER

    def test_eq_color_on_generated_color(self):
        """eq_color should be EQUALITY even when Color is a generated sort."""
        from alspec import Signature, GeneratedSortInfo, atomic, fn, pred
        from alspec.obligation import classify_predicates, PredKind

        sig = Signature(
            sorts={"Color": atomic("Color")},
            functions={
                "red": fn("red", [], "Color"),
                "green": fn("green", [], "Color"),
            },
            predicates={
                "eq_color": pred("eq_color", [("a", "Color"), ("b", "Color")]),
            },
            generated_sorts={
                "Color": GeneratedSortInfo(constructors=("red", "green"), selectors={}),
            },
        )
        roles = classify_predicates(sig)
        assert roles["eq_color"].kind == PredKind.EQUALITY

    def test_no_spurious_obligation_cells_for_eq_on_generated(self):
        """eq_bool should NOT generate obligation cells when Bool is generated."""
        from alspec import Signature, GeneratedSortInfo, atomic, fn, pred
        from alspec.obligation import build_obligation_table

        sig = Signature(
            sorts={"Bool": atomic("Bool")},
            functions={
                "true": fn("true", [], "Bool"),
                "false": fn("false", [], "Bool"),
            },
            predicates={
                "eq_bool": pred("eq_bool", [("a", "Bool"), ("b", "Bool")]),
            },
            generated_sorts={
                "Bool": GeneratedSortInfo(constructors=("true", "false"), selectors={}),
            },
        )
        table = build_obligation_table(sig)
        eq_bool_cells = [c for c in table.cells if c.observer_name == "eq_bool"]



class TestGenerationConstraint:
    """Check C: Generation constraint on non-constructor functions."""

    def test_observer_returning_generated_sort_no_error(self):
        """Observer of sort H returning generated sort G should not raise."""
        from alspec import Signature, GeneratedSortInfo, atomic, fn
        from alspec.obligation import build_obligation_table

        sig = Signature(
            sorts={
                "User": atomic("User"),
                "Role": atomic("Role"),
                "Name": atomic("Name"),
            },
            functions={
                "viewer": fn("viewer", [], "Role"),
                "editor": fn("editor", [], "Role"),
                "create_user": fn("create_user", [("n", "Name")], "User"),
                "get_role": fn("get_role", [("u", "User")], "Role"),
            },
            predicates={},
            generated_sorts={
                "Role": GeneratedSortInfo(constructors=("viewer", "editor"), selectors={}),
                "User": GeneratedSortInfo(constructors=("create_user",), selectors={}),
            },
        )
        # Should not raise
        table = build_obligation_table(sig)
        # get_role should be an observer of User
        user_cells = [c for c in table.cells if c.generated_sort == "User"]
        assert any(c.observer_name == "get_role" for c in user_cells)

    def test_constant_returning_generated_sort_raises(self):
        """Constant returning a generated sort without being a constructor is a defect."""
        import pytest
        from alspec import Signature, GeneratedSortInfo, atomic, fn
        from alspec.obligation import build_obligation_table, ObligationTableError

        sig = Signature(
            sorts={
                "Role": atomic("Role"),
            },
            functions={
                "viewer": fn("viewer", [], "Role"),
                "editor": fn("editor", [], "Role"),
                "default_role": fn("default_role", [], "Role"),
            },
            predicates={},
            generated_sorts={
                "Role": GeneratedSortInfo(constructors=("viewer", "editor"), selectors={}),
            },
        )
        with pytest.raises(ObligationTableError, match="default_role"):
            build_obligation_table(sig)

    def test_uninterpreted_returning_generated_sort_raises(self):
        """Uninterpreted function returning a generated sort is a defect."""
        import pytest
        from alspec import Signature, GeneratedSortInfo, atomic, fn
        from alspec.obligation import build_obligation_table, ObligationTableError

        sig = Signature(
            sorts={
                "Role": atomic("Role"),
                "String": atomic("String"),
                "Int": atomic("Int"),
            },
            functions={
                "viewer": fn("viewer", [], "Role"),
                "editor": fn("editor", [], "Role"),
                "compute_role": fn("compute_role", [("s", "String"), ("i", "Int")], "Role"),
            },
            predicates={},
            generated_sorts={
                "Role": GeneratedSortInfo(constructors=("viewer", "editor"), selectors={}),
            },
        )
        with pytest.raises(ObligationTableError, match="compute_role"):
            build_obligation_table(sig)



class TestNamespaceInvariant:
    """Namespace invariant (CASL RM §2.3.4): constructors and selectors must be functions."""

    def test_constructor_as_predicate_raises(self):
        import pytest
        from alspec import Signature, GeneratedSortInfo, atomic, fn, pred
        from alspec.obligation import build_obligation_table, ObligationTableError

        sig = Signature(
            sorts={"S": atomic("S")},
            functions={"init": fn("init", [], "S")},
            predicates={"is_valid": pred("is_valid", [("s", "S")])},
            generated_sorts={
                "S": GeneratedSortInfo(constructors=("init", "is_valid"), selectors={}),
            },
        )
        with pytest.raises(ObligationTableError, match="is_valid.*predicate.*function"):
            build_obligation_table(sig)

    def test_selector_as_predicate_raises(self):
        import pytest
        from alspec import Signature, GeneratedSortInfo, atomic, fn, pred
        from alspec.obligation import build_obligation_table, ObligationTableError

        sig = Signature(
            sorts={"S": atomic("S"), "Bool": atomic("Bool")},
            functions={"init": fn("init", [("b", "Bool")], "S")},
            predicates={"sel": pred("sel", [("s", "S")])},
            generated_sorts={
                "S": GeneratedSortInfo(
                    constructors=("init",),
                    selectors={"init": {"sel": "b"}}
                ),
            },
        )
        with pytest.raises(ObligationTableError, match="sel.*predicate.*function"):
            build_obligation_table(sig)

    def test_nonexistent_selector_raises(self):
        import pytest
        from alspec import Signature, GeneratedSortInfo, atomic, fn
        from alspec.obligation import build_obligation_table, ObligationTableError

        sig = Signature(
            sorts={"S": atomic("S"), "Bool": atomic("Bool")},
            functions={"init": fn("init", [("b", "Bool")], "S")},
            predicates={},
            generated_sorts={
                "S": GeneratedSortInfo(
                    constructors=("init",),
                    selectors={"init": {"missing": "b"}}
                ),
            },
        )
        with pytest.raises(ObligationTableError, match="missing.*not found in signature"):
            build_obligation_table(sig)
