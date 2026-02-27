from alspec import AtomicSort, SortRef


def test_atomic_sort() -> None:
    s = AtomicSort(name=SortRef("Nat"))
    assert s.name == "Nat"
    assert s.kind.value == "atomic"


if __name__ == "__main__":
    test_atomic_sort()
    print("Basic test passed!")
