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
        assert len(eq_bool_cells) == 0, (
            f"eq_bool should not have obligation cells but got {len(eq_bool_cells)}"
        )
