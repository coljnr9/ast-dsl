import pytest
from alspec.score import score_spec
from alspec.spec import Spec
from alspec.signature import Signature, GeneratedSortInfo
from alspec import atomic, fn, var, app, eq, forall


import importlib.util
import os
from pathlib import Path

def load_golden_spec(name: str) -> Spec:
    """Load a spec from the golden directory by filename (e.g. 'stack' or 'bug-tracker')."""
    base_dir = Path(__file__).parent.parent
    path = base_dir / "golden" / f"{name}.py"
    
    spec_name = name.replace("-", "_")
    module_name = f"golden_{spec_name}"
    
    spec_node = importlib.util.spec_from_file_location(module_name, str(path))
    if spec_node is None or spec_node.loader is None:
        raise ImportError(f"Could not load {path}")
        
    module = importlib.util.module_from_spec(spec_node)
    spec_node.loader.exec_module(module)
    
    # The function name in the file is usually {name}_spec, with dashes replaced by underscores
    fn_name = f"{spec_name}_spec"
    return getattr(module, fn_name)()


@pytest.mark.asyncio
async def test_score_counter_coverage():
    """Counter gets full coverage through score_spec."""
    score = await score_spec(load_golden_spec("counter"), strict=True, audit=True)
    assert score.obligation_cell_count == 4
    assert score.covered_cell_count == 4
    assert score.uncovered_cell_count == 0
    assert score.unmatched_axiom_count == 0
    assert score.coverage_ratio == 1.0


@pytest.mark.asyncio
async def test_score_stack_coverage():
    """Stack gets full coverage (6 cells, 6 axioms)."""
    score = await score_spec(load_golden_spec("stack"), strict=True, audit=True)
    assert score.obligation_cell_count == 6
    assert score.covered_cell_count == 6
    assert score.uncovered_cell_count == 0
    assert score.coverage_ratio == 1.0


@pytest.mark.asyncio
async def test_score_bug_tracker_coverage():
    """Bug tracker has 35 cells, preservation collapses, basis axioms."""
    score = await score_spec(load_golden_spec("bug-tracker"), strict=True, audit=True)
    assert score.obligation_cell_count == 35
    assert score.uncovered_cell_count == 0
    assert score.coverage_ratio == 1.0


@pytest.mark.asyncio
async def test_score_no_generated_sorts():
    """Spec with no generated_sorts gets no coverage data."""
    sig = Signature(
        sorts={"Nat": atomic("Nat")},
        functions={"zero": fn("zero", [], "Nat")},
        predicates={},
    )
    spec = Spec(name="Trivial", signature=sig, axioms=())
    score = await score_spec(spec)
    assert score.obligation_cell_count == 0
    assert score.coverage_ratio is None


@pytest.mark.asyncio
async def test_coverage_diagnostics_in_score():
    """Coverage diagnostics appear in score.diagnostics."""
    score = await score_spec(load_golden_spec("counter"), strict=True, audit=True)
    
    coverage_diags = [d for d in score.diagnostics if d.check == "coverage"]
    assert len(coverage_diags) > 0
    
    # Should have at least the summary INFO diagnostic
    info_diags = [d for d in coverage_diags if d.severity.value == "info"]
    assert len(info_diags) >= 1
    assert "Cell coverage:" in info_diags[0].message


@pytest.mark.asyncio
async def test_uncovered_cell_produces_warning():
    """A spec with a missing axiom produces a coverage WARNING."""
    from alspec import Axiom
    sig = Signature(
        sorts={"S": atomic("S"), "E": atomic("E")},
        functions={
            "new": fn("new", [], "S"),
            "put": fn("put", [("s", "S"), ("e", "E")], "S"),
            "get": fn("get", [("s", "S")], "E"),
        },
        predicates={},
        generated_sorts={
            "S": GeneratedSortInfo(constructors=("new", "put"), selectors={})
        },
    )
    # Only provide axiom for get×put, not get×new → 1 uncovered cell
    s = var("s", "S")
    e = var("e", "E")
    spec = Spec(
        name="Incomplete",
        signature=sig,
        axioms=(
            Axiom(label="get_put", formula=forall([s, e], eq(
                app("get", app("put", s, e)), e
            ))),
        ),
    )
    score = await score_spec(spec, strict=True, audit=True)
    assert score.uncovered_cell_count == 1
    assert score.covered_cell_count == 1
    assert score.obligation_cell_count == 2
    
    # Check WARNING diagnostic exists
    warnings = [d for d in score.diagnostics
                if d.check == "coverage" and d.severity.value == "warning"]
    assert any("get(fn) × new" in d.message for d in warnings)


@pytest.mark.asyncio
async def test_coverage_does_not_affect_health():
    """Coverage warnings must not change health score."""
    from alspec import Axiom
    sig = Signature(
        sorts={"S": atomic("S"), "E": atomic("E")},
        functions={
            "new": fn("new", [], "S"),
            "put": fn("put", [("s", "S"), ("e", "E")], "S"),
            "get": fn("get", [("s", "S")], "E"),
        },
        predicates={},
        generated_sorts={
            "S": GeneratedSortInfo(constructors=("new", "put"), selectors={})
        },
    )
    # Only provide axiom for get×put, not get×new → 1 uncovered cell
    s = var("s", "S")
    e = var("e", "E")
    spec = Spec(
        name="Incomplete",
        signature=sig,
        axioms=(
            Axiom(label="get_put", formula=forall([s, e], eq(
                app("get", app("put", s, e)), e
            ))),
        ),
    )
    score = await score_spec(spec, strict=True, audit=True)
    assert score.health == 1.0  # No checker errors
    assert score.well_formed is True
    assert score.uncovered_cell_count > 0  # But coverage is incomplete
