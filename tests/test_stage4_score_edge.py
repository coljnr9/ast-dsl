import pytest
from alspec.eval.stage4_score import score_stage4_output
from alspec.signature import Signature, GeneratedSortInfo
from alspec.sorts import AtomicSort, SortRef
from alspec.helpers import fn

@pytest.mark.asyncio
async def test_score_stage4_zero_cells():
    # A signature with no generated sorts has no obligation cells.
    sig = Signature(
        sorts={SortRef("S"): AtomicSort(name=SortRef("S"))},
        functions={},
        predicates={},
        generated_sorts={}
    )
    
    # Minimal valid spec code
    code = """
from alspec.spec import Spec
from alspec.signature import Signature, GeneratedSortInfo
from alspec.sorts import AtomicSort, SortRef
sig = Signature(
    sorts={SortRef("S"): AtomicSort(name=SortRef("S"))},
    functions={},
    predicates={},
    generated_sorts={}
)
spec = Spec("test", sig, ())
"""
    
    score = await score_stage4_output(
        code=code,
        domain="test",
        sig=sig,
    )
    
    assert score.parse_success is True
    assert score.total_cells == 0
    assert score.coverage_ratio is None

@pytest.mark.asyncio
async def test_score_stage4_with_cells():
    # A signature with a generated sort should have obligation cells if observers exist.
    sig = Signature(
        sorts={
            SortRef("S"): AtomicSort(name=SortRef("S")),
            SortRef("E"): AtomicSort(name=SortRef("E"))
        },
        functions={
            "new": fn("new", [], "S"),
            "push": fn("push", [("s", "S"), ("e", "E")], "S"),
            # Observer: top : S -> E
            "top": fn("top", [("s", "S")], "E")
        },
        predicates={},
        generated_sorts={
            "S": GeneratedSortInfo(
                constructors=("new", "push"),
            )
        }
    )
    
    code = """
from alspec.spec import Spec
from alspec.signature import Signature, GeneratedSortInfo
from alspec.sorts import AtomicSort, SortRef
from alspec.helpers import fn
sig = Signature(
    sorts={
        SortRef("S"): AtomicSort(name=SortRef("S")),
        SortRef("E"): AtomicSort(name=SortRef("E"))
    },
    functions={
        "new": fn("new", [], "S"),
        "push": fn("push", [("s", "S"), ("e", "E")], "S"),
        "top": fn("top", [("s", "S")], "E")
    },
    predicates={},
    generated_sorts={
        "S": GeneratedSortInfo(
            constructors=("new", "push"),
        )
    }
)
spec = Spec("test", sig, ())
"""
    
    score = await score_stage4_output(
        code=code,
        domain="test",
        sig=sig,
    )
    
    assert score.parse_success is True
    # top(new) and top(push) -> 2 cells
    assert score.total_cells == 2
    assert score.coverage_ratio == 0.0 # 0/2 covered
