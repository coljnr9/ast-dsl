"""Tests for mechanical axiom generation (Stage 3.5).

Validates generated axioms against golden reference specs, checks
well-sortedness, and verifies round-trip through the axiom matcher.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from alspec.axiom_gen import (
    MechanicalAxiomReport,
    generate_mechanical_axioms,
    render_axiom_to_python,
)
from alspec.axiom_match import CoverageStatus, match_spec_sync
from alspec.check import check_spec
from alspec.helpers import app, eq, forall, iff, implication, negation, pred_app, var
from alspec.obligation import (
    CellDispatch,
    CellTier,
    build_obligation_table,
)
from alspec.spec import Axiom, Spec

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

GOLDEN_DIR = Path(__file__).parent.parent / "golden"
EXAMPLES_DIR = Path(__file__).parent.parent / "examples"


def _load_golden(stem: str):
    """Import a golden spec module by stem (filename without .py).

    Handles hyphens in filenames via importlib.
    """
    module_path = str(GOLDEN_DIR / f"{stem}.py")
    spec_node = importlib.util.spec_from_file_location(stem, module_path)
    if spec_node is None or spec_node.loader is None:
        raise ImportError(f"Cannot load golden spec: {module_path}")
    mod = importlib.util.module_from_spec(spec_node)
    spec_node.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def _load_example(stem: str):
    """Import an example spec module by stem."""
    module_path = str(EXAMPLES_DIR / f"{stem}.py")
    spec_node = importlib.util.spec_from_file_location(stem, module_path)
    if spec_node is None or spec_node.loader is None:
        raise ImportError(f"Cannot load example spec: {module_path}")
    mod = importlib.util.module_from_spec(spec_node)
    spec_node.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def _gen_from_spec(spec: Spec):
    """Run mechanical generator on a pre-built spec."""
    sig = spec.signature
    table = build_obligation_table(sig)
    report = generate_mechanical_axioms(sig, table)
    return sig, table, report


def _gen(spec_fn):
    """Run full pipeline: spec_fn → spec → sig → table → mechanical axioms."""
    spec = spec_fn()
    sig, table, report = _gen_from_spec(spec)
    return spec, sig, table, report


def _find_axiom(report: MechanicalAxiomReport, label: str) -> Axiom:
    """Find a generated axiom by label, or fail the test."""
    for ax in report.axioms:
        if ax.label == label:
            return ax
    available = [a.label for a in report.axioms]
    raise AssertionError(
        f"Axiom '{label}' not found in generated axioms. Available: {available}"
    )


# ---------------------------------------------------------------------------
# TestSelectorExtract
# ---------------------------------------------------------------------------


class TestSelectorExtract:
    """SELECTOR_EXTRACT: sel(ctor(x₁,...,xₙ)) = xᵢ."""

    def test_stack_top_push(self):
        """top(push(s,e)) = e — the canonical selector extraction."""
        mod = _load_golden("stack")
        _, sig, table, report = _gen(mod.stack_spec)

        ax = _find_axiom(report, "top_push_extract")

        s = var("s", "Stack")
        e = var("e", "Elem")
        expected = forall(
            [s, e],
            eq(
                app("top", app("push", s, e)),
                e,
            ),
        )
        assert ax.formula == expected

    def test_stack_pop_push(self):
        """pop(push(s,e)) = s — selector extracting the state component."""
        mod = _load_golden("stack")
        _, sig, table, report = _gen(mod.stack_spec)

        ax = _find_axiom(report, "pop_push_extract")

        s = var("s", "Stack")
        e = var("e", "Elem")
        expected = forall(
            [s, e],
            eq(
                app("pop", app("push", s, e)),
                s,
            ),
        )
        assert ax.formula == expected

    def test_session_store_get_token_create(self):
        """get_token(create(t)) = t — single-param extraction."""
        mod = _load_example("session_store_spec")
        _, sig, table, report = _gen(mod.session_store_spec)

        ax = _find_axiom(report, "get_token_create_extract")

        t = var("t", "Token")
        expected = forall(
            [t],
            eq(
                app("get_token", app("create", t)),
                t,
            ),
        )
        assert ax.formula == expected

    def test_thermostat_get_target_set_target(self):
        """get_target(set_target(th,t)) = t — thermostat selector."""
        mod = _load_golden("thermostat")
        _, sig, table, report = _gen(mod.thermostat_spec)

        ax = _find_axiom(report, "get_target_set_target_extract")

        th = var("th", "Thermostat")
        t = var("t", "Temp")
        expected = forall(
            [th, t],
            eq(
                app("get_target", app("set_target", th, t)),
                t,
            ),
        )
        assert ax.formula == expected

    def test_thermostat_get_current_read_temp(self):
        """get_current(read_temp(th,r)) = r — thermostat selector."""
        mod = _load_golden("thermostat")
        _, sig, table, report = _gen(mod.thermostat_spec)

        ax = _find_axiom(report, "get_current_read_temp_extract")

        th = var("th", "Thermostat")
        r = var("r", "Temp")
        expected = forall(
            [th, r],
            eq(
                app("get_current", app("read_temp", th, r)),
                r,
            ),
        )
        assert ax.formula == expected

    def test_temp_sensor_read_record(self):
        """read(record(s,t)) = t — temperature sensor selector."""
        mod = _load_golden("temperature-sensor")
        _, sig, table, report = _gen(mod.temperature_sensor_spec)

        ax = _find_axiom(report, "read_record_extract")

        s = var("s", "Sensor")
        t = var("t", "Temp")
        expected = forall(
            [s, t],
            eq(
                app("read", app("record", s, t)),
                t,
            ),
        )
        assert ax.formula == expected


# ---------------------------------------------------------------------------
# TestMiss
# ---------------------------------------------------------------------------


class TestMiss:
    """KEY_DISPATCH MISS: ¬eq(k,k2) → obs(ctor(s,...),k2,...) = obs(s,k2,...)."""

    def test_library_get_status_register_miss(self):
        """get_status(register(L,b),b2) = get_status(L,b2) when ¬eq_id(b,b2)."""
        mod = _load_golden("library-lending")
        _, sig, table, report = _gen(mod.library_lending_spec)

        ax = _find_axiom(report, "get_status_register_miss")

        L = var("L", "Library")
        b = var("b", "BookId")
        b2 = var("b2", "BookId")

        expected = forall(
            [L, b, b2],
            implication(
                negation(pred_app("eq_id", b, b2)),
                eq(
                    app("get_status", app("register", L, b), b2),
                    app("get_status", L, b2),
                ),
            ),
        )
        assert ax.formula == expected

    def test_library_has_book_register_miss(self):
        """Predicate MISS: has_book(register(L,b),b2) ↔ has_book(L,b2) when ¬eq_id(b,b2)."""
        mod = _load_golden("library-lending")
        _, sig, table, report = _gen(mod.library_lending_spec)

        ax = _find_axiom(report, "has_book_register_miss")

        L = var("L", "Library")
        b = var("b", "BookId")
        b2 = var("b2", "BookId")

        expected = forall(
            [L, b, b2],
            implication(
                negation(pred_app("eq_id", b, b2)),
                iff(
                    pred_app("has_book", app("register", L, b), b2),
                    pred_app("has_book", L, b2),
                ),
            ),
        )
        assert ax.formula == expected

    def test_todo_get_title_add_miss(self):
        """Multi-param constructor: get_title(add_item(l,k,t),k2) = get_title(l,k2)."""
        mod = _load_golden("todo-list")
        _, sig, table, report = _gen(mod.todo_list_spec)

        ax = _find_axiom(report, "get_title_add_item_miss")

        todo_l = var("l", "TodoList")
        k = var("k", "ItemId")
        t = var("t", "Title")
        k2 = var("k2", "ItemId")

        expected = forall(
            [todo_l, k, t, k2],
            implication(
                negation(pred_app("eq_id", k, k2)),
                eq(
                    app("get_title", app("add_item", todo_l, k, t), k2),
                    app("get_title", todo_l, k2),
                ),
            ),
        )
        assert ax.formula == expected

    def test_library_borrow_miss(self):
        """get_status(borrow(L,b,u),b2) = get_status(L,b2) when ¬eq_id(b,b2)."""
        mod = _load_golden("library-lending")
        _, sig, table, report = _gen(mod.library_lending_spec)

        ax = _find_axiom(report, "get_status_borrow_miss")

        L = var("L", "Library")
        b = var("b", "BookId")
        u = var("u", "UserId")
        b2 = var("b2", "BookId")

        expected = forall(
            [L, b, u, b2],
            implication(
                negation(pred_app("eq_id", b, b2)),
                eq(
                    app("get_status", app("borrow", L, b, u), b2),
                    app("get_status", L, b2),
                ),
            ),
        )
        assert ax.formula == expected


# ---------------------------------------------------------------------------
# TestPreservation
# ---------------------------------------------------------------------------


class TestPreservation:
    """PRESERVATION: obs(ctor(s,...),k2,...) = obs(s,k2,...) — unconditional.

    PRESERVATION tier applies when the observer has a key sort but the
    constructor does NOT take that sort. This is the strongest frame axiom
    (no guard needed, always delegates).
    """

    def test_auction_is_registered_close(self):
        """is_registered(close(a),b) ↔ is_registered(a,b) — close doesn't take Bidder."""
        mod = _load_golden("auction")
        _, sig, table, report = _gen(mod.auction_spec)

        ax = _find_axiom(report, "is_registered_close_preserve")

        a = var("a", "Auction")
        b = var("b", "Bidder")

        expected = forall(
            [a, b],
            iff(
                pred_app("is_registered", app("close", a), b),
                pred_app("is_registered", a, b),
            ),
        )
        assert ax.formula == expected

    def test_base_case_preservation_skipped(self):
        """Nullary constructors classified as PRESERVATION should be skipped (no state var)."""
        mod = _load_golden("library-lending")
        _, sig, table, report = _gen(mod.library_lending_spec)

        # has_book × empty is PRESERVATION tier but has no state param
        # So it should be in cells_skipped, not cells_covered
        skipped_keys = {
            (c.observer_name, c.constructor_name) for c in report.cells_skipped
        }
        assert ("has_book", "empty") in skipped_keys

    def test_selector_foreign_not_generated(self):
        """SELECTOR_FOREIGN cells should NOT be generated by axiom_gen."""
        mod = _load_golden("thermostat")
        spec, sig, table, report = _gen(mod.thermostat_spec)

        labels = [a.label for a in report.axioms]
        # SELECTOR_FOREIGN are NOT generated
        assert "get_target_read_temp_extract" not in labels
        assert "get_current_set_target_extract" not in labels


# ---------------------------------------------------------------------------
# TestIntegration
# ---------------------------------------------------------------------------


def _load_all_golden_specs():
    """Load all golden specs that can be imported.

    Returns list of (domain_name, Spec) tuples.
    """
    specs = []

    entries = [
        ("stack", "stack_spec"),
        ("library-lending", "library_lending_spec"),
        ("todo-list", "todo_list_spec"),
        ("thermostat", "thermostat_spec"),
        ("temperature-sensor", "temperature_sensor_spec"),
        ("counter", "counter_spec"),
        ("auction", "auction_spec"),
    ]

    for stem, fn_name in entries:
        mod = _load_golden(stem)
        spec_fn = getattr(mod, fn_name)
        specs.append((stem, spec_fn()))

    # Also session store from examples
    mod = _load_example("session_store_spec")
    specs.append(("session-store", mod.session_store_spec()))

    return specs


class TestIntegration:
    """End-to-end tests: well-sortedness, matcher round-trip, coverage."""

    def test_generated_axioms_pass_well_sortedness(self):
        """ALL generated axioms from ALL golden specs must pass check_spec."""
        for domain_name, spec in _load_all_golden_specs():
            sig = spec.signature
            table = build_obligation_table(sig)
            report = generate_mechanical_axioms(sig, table)

            if len(report.axioms) == 0:
                continue

            # Create a spec with only the mechanical axioms
            mech_spec = Spec(
                name=f"{spec.name}_Mechanical",
                signature=sig,
                axioms=report.axioms,
            )
            checker_result = check_spec(mech_spec)
            assert checker_result.is_well_formed, (
                f"Mechanical axioms for {domain_name} failed well-sortedness: "
                f"{[d.message for d in checker_result.errors]}"
            )

    def test_generated_axioms_cover_correct_cells(self):
        """Generated axioms must match their target cells in the matcher."""
        mod = _load_golden("library-lending")
        spec = mod.library_lending_spec()
        sig = spec.signature
        table = build_obligation_table(sig)
        report = generate_mechanical_axioms(sig, table)

        # Build a spec with ONLY the mechanical axioms
        mech_spec = Spec(name="MechOnly", signature=sig, axioms=report.axioms)
        match_report = match_spec_sync(mech_spec, table, sig)

        # Every cell in report.cells_covered should be COVERED in match_report
        covered_keys = {
            (c.observer_name, c.constructor_name, c.dispatch.value)
            for c in report.cells_covered
        }
        for cc in match_report.coverage:
            key = (
                cc.cell.observer_name,
                cc.cell.constructor_name,
                cc.cell.dispatch.value,
            )
            if key in covered_keys:
                assert cc.status != CoverageStatus.UNCOVERED, (
                    f"Generated axiom for {key} was not recognized by matcher"
                )

    def test_no_axioms_for_hit_or_domain(self):
        """Verify we DON'T generate axioms for HIT, DOMAIN, BASE_CASE, SELECTOR_FOREIGN."""
        mod = _load_golden("library-lending")
        spec = mod.library_lending_spec()
        sig = spec.signature
        table = build_obligation_table(sig)
        report = generate_mechanical_axioms(sig, table)

        allowed_tiers = {
            CellTier.SELECTOR_EXTRACT,
            CellTier.KEY_DISPATCH,
            CellTier.PRESERVATION,
        }

        for cell in report.cells_covered:
            assert cell.tier in allowed_tiers, (
                f"Cell ({cell.observer_name}, {cell.constructor_name}) "
                f"has tier {cell.tier.value} which should not be generated"
            )

            # KEY_DISPATCH cells must be MISS only
            if cell.tier == CellTier.KEY_DISPATCH:
                assert cell.dispatch == CellDispatch.MISS, (
                    f"Cell ({cell.observer_name}, {cell.constructor_name}) "
                    f"is KEY_DISPATCH but dispatch is {cell.dispatch.value}, "
                    f"expected MISS"
                )

    def test_report_counts(self):
        """Verify cells_covered + cells_skipped + LLM_cells = total cells."""
        mod = _load_golden("library-lending")
        spec = mod.library_lending_spec()
        sig = spec.signature
        table = build_obligation_table(sig)
        report = generate_mechanical_axioms(sig, table)

        mechanical_cell_count = len(report.cells_covered) + len(report.cells_skipped)

        # Count how many cells should be mechanical
        expected_mechanical = 0
        for cell in table.cells:
            if cell.tier == CellTier.SELECTOR_EXTRACT:
                expected_mechanical += 1
            elif (
                cell.tier == CellTier.KEY_DISPATCH
                and cell.dispatch == CellDispatch.MISS
            ):
                expected_mechanical += 1
            elif cell.tier == CellTier.PRESERVATION:
                expected_mechanical += 1

        assert mechanical_cell_count == expected_mechanical, (
            f"Expected {expected_mechanical} mechanical cells but got "
            f"{mechanical_cell_count} (covered={len(report.cells_covered)}, "
            f"skipped={len(report.cells_skipped)})"
        )

        # Total should partition
        llm_cells = len(table.cells) - mechanical_cell_count
        assert llm_cells + mechanical_cell_count == len(table.cells)

    def test_stack_produces_exactly_extraction_axioms(self):
        """Stack has only SELECTOR_EXTRACT cells as mechanical."""
        mod = _load_golden("stack")
        _, sig, table, report = _gen(mod.stack_spec)

        # Stack has: pop_push_extract, top_push_extract
        assert len(report.axioms) == 2
        labels = sorted(a.label for a in report.axioms)
        assert labels == ["pop_push_extract", "top_push_extract"]

    def test_library_lending_mechanical_count(self):
        """Library-lending should produce MISS axioms (no inlined PRESERVATION with state)."""
        mod = _load_golden("library-lending")
        _, sig, table, report = _gen(mod.library_lending_spec)

        # Should produce axioms
        assert len(report.axioms) > 0, (
            "Should produce mechanical axioms for library-lending"
        )

        tiers = {c.tier for c in report.cells_covered}
        dispatches = {
            c.dispatch for c in report.cells_covered if c.tier == CellTier.KEY_DISPATCH
        }

        # Should have MISS axioms
        assert CellTier.KEY_DISPATCH in tiers
        assert CellDispatch.MISS in dispatches
        assert CellDispatch.HIT not in dispatches

    def test_auction_has_preservation(self):
        """Auction should produce PRESERVATION axioms for close × is_registered."""
        mod = _load_golden("auction")
        _, sig, table, report = _gen(mod.auction_spec)

        tiers = {c.tier for c in report.cells_covered}
        assert CellTier.PRESERVATION in tiers

    def test_multi_golden_per_axiom_well_sorted(self):
        """Each individual generated axiom must pass well-sortedness."""
        for domain_name, spec in _load_all_golden_specs():
            sig = spec.signature
            table = build_obligation_table(sig)
            report = generate_mechanical_axioms(sig, table)

            for ax in report.axioms:
                mini_spec = Spec(
                    name=f"Mini_{ax.label}",
                    signature=sig,
                    axioms=(ax,),
                )
                result = check_spec(mini_spec)
                assert result.is_well_formed, (
                    f"Axiom {ax.label} from {domain_name} failed: "
                    f"{[d.message for d in result.errors]}"
                )

    def test_todo_list_round_trip(self):
        """Todo-list mechanical axioms round-trip through matcher."""
        mod = _load_golden("todo-list")
        spec = mod.todo_list_spec()
        sig = spec.signature
        table = build_obligation_table(sig)
        report = generate_mechanical_axioms(sig, table)

        mech_spec = Spec(name="MechOnly", signature=sig, axioms=report.axioms)
        match_report = match_spec_sync(mech_spec, table, sig)

        covered_keys = {
            (c.observer_name, c.constructor_name, c.dispatch.value)
            for c in report.cells_covered
        }
        for cc in match_report.coverage:
            key = (
                cc.cell.observer_name,
                cc.cell.constructor_name,
                cc.cell.dispatch.value,
            )
            if key in covered_keys:
                assert cc.status != CoverageStatus.UNCOVERED, (
                    f"Generated axiom for {key} was not recognized by matcher"
                )

class TestApproachB:
    """Tests for the Approach B prompt generation logic."""

    def test_render_axiom_round_trip(self):
        """Rendered Python code must produce identical Axiom objects when exec'd."""
        from alspec.axiom_gen import render_axiom_to_python
        for domain_name, spec in _load_all_golden_specs():
            sig = spec.signature
            table = build_obligation_table(sig)
            report = generate_mechanical_axioms(sig, table)
            for axiom in report.axioms:
                code = render_axiom_to_python(axiom)
                # Build a namespace with all the helpers
                ns = {}
                exec("from alspec import *", ns)
                exec("from alspec.helpers import *", ns)
                # eval the code which returns the Axiom object
                recovered = eval(code, ns)
                assert recovered == axiom, (
                    f"Round-trip failed for {axiom.label} in {domain_name}: "
                    f"rendered as:\n{code}"
                )

    def test_remaining_cells_exclude_mechanical(self):
        """render_obligation_prompt should not list mechanically covered cells."""
        from alspec.obligation_render import render_obligation_prompt

        for domain_name, spec in _load_all_golden_specs():
            sig = spec.signature
            table = build_obligation_table(sig)
            report = generate_mechanical_axioms(sig, table)
            prompt = render_obligation_prompt(sig, table, report)

            # The mechanical axiom labels should appear in the "already generated" section
            for axiom in report.axioms:
                assert (
                    axiom.label in prompt
                ), f"Mechanical axiom {axiom.label} missing from prompt for {domain_name}"

            # We'll check that a purely mechanical cell is NOT in the remaining list.
            if domain_name == "stack":
                remaining_section = prompt.split("Remaining axiom obligations")[1]
                # top(push(s, e)) should be mechanical (SELECTOR_EXTRACT)
                assert "top(push(s, e))" not in remaining_section
