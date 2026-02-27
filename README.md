# many-sorted
Building blocks for many-sorted algebraic specifications.

This package provides a Python DSL for defining signatures, terms, and axioms in the style of CASL (Common Algebraic Specification Language).

## Workspace Structure

- `alspec/`: Core library package
  - `sorts.py`: Atomic, Product, and Coproduct sorts
  - `signature.py`: Signatures consisting of sorts, functions, and predicates
  - `terms.py`: Term AST (Variables, Function Apps, Field Access) and Formulas (Equations, Quantifiers, etc.)
  - `spec.py`: Specifications (Signature + Axioms)
  - `serialization.py`: JSON serialization for all types
- `examples/`: Textbook algebraic specification examples (Peano Nat, Stack, Partial Order)
- `tests/`: Basic test suite

## Usage

Check out `examples/examples.py` for full examples of how to build specifications.

### Running Examples

```bash
python3 examples/examples.py
```

### Quick Look

```python
from alspec import Spec, Signature, AtomicSort, SortRef

# Define a simple sort
nat = AtomicSort(name=SortRef("Nat"))

# Access it in a signature
sig = Signature(
    sorts={"Nat": nat},
    functions={},
    predicates={}
)

spec = Spec(name="MySpec", signature=sig, axioms=())
```

## Development

This project uses `uv` for dependency management and tooling. Here are common commands to use during development:

```bash
# Auto-format code
uv run ruff format .

# Check for linting errors
uv run ruff check .

# Fix auto-fixable linting errors
uv run ruff check --fix .

# Run static type checking
uv run mypy .

# Run the test suite
uv run pytest
```
