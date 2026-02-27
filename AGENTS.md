# AGENTS.md

## What This Is

`alspec` is a Python DSL for constructing many-sorted algebraic specifications. It provides the AST types, builder helpers, serialization, and a verified standard library ("basis") for the formalism described in:

- The CASL Language Summary (Astesiano et al., 2001)
- Sannella & Tarlecki, *Foundations of Algebraic Specification and Formal Software Development* (2012)

A specification in this system consists of **sorts** (types/carrier sets), **function symbols** (typed operations over sorts), **predicate symbols** (typed boolean relations), and **axioms** (universally quantified equations and logical formulas). The DSL encodes these as frozen Python dataclasses with JSON round-trip serialization.

## Why It Exists

This is the formal intermediate representation for **Gravity-Well**, an LLM-powered code generation pipeline that translates natural language specifications into complete Rust applications. The pipeline's earlier versions generated code without a formal language for the intermediate stages, which meant errors weren't caught until Rust compilation — sometimes three pipeline stages after the mistake was introduced.

`alspec` fixes this by providing well-sorted building blocks that each pipeline stage can output and the next stage can validate. The long-term architecture is:

1. **LLM generates a `Spec`** from a natural language description, using the DSL's helpers
2. **Well-sortedness checker validates the spec** immediately (sorts resolve, profiles match, equations are balanced)
3. **Axiom obligations are derived mechanically** from the signature (one axiom per observer × constructor pair)
4. **Rust code is generated** from the validated spec

Steps 2-4 are not yet implemented. The current focus is on getting step 1 right: the DSL, the basis library that teaches LLMs the fundamental patterns, and the reference documentation that serves as the LLM's prompt context.

## Coding Conventions

### Fail loudly

Do not silently return `None`, empty collections, or default values when something is wrong. Raise exceptions with descriptive messages. The `Result[T, E]` type (in `result.py`) is for operations where failure is an expected outcome (LLM calls, I/O), not for programming errors. A malformed AST node should crash, not return `Err`.

### Strong typing

All AST nodes are `@dataclass(frozen=True)`. All collections in AST nodes are tuples, not lists — immutability is a feature. Use `SortRef` (a `NewType` over `str`) wherever a sort name appears, not bare strings. Type annotations on every function signature. Union types for `Term` and `Formula` are explicit and exhaustive — if you add a new AST node, add it to the union.

### Parse, don't validate

The `Term` and `Formula` types are structurally distinct and cannot be mixed. `eq()` takes two `Term`s and returns a `Formula`. `Negation` takes a `Formula`, never a `Term`. If you find yourself casting or checking `isinstance` at a boundary, the types are wrong — fix the types, not the boundary.

### Helpers are the public API

Code that constructs specs — whether in `basis.py`, `examples.py`, tests, or LLM-generated output — should use the helpers from `helpers.py` (`fn`, `pred`, `var`, `app`, `const`, `eq`, `forall`, `iff`, etc.) rather than constructing dataclasses directly. Direct construction is for the helpers themselves and for serialization.

### Axiom methodology

Every observer/derived operation owes one axiom per constructor of its primary argument sort. Partial functions skip the constructor case where they're undefined (e.g., `top` on `new` for Stack). This is the core pattern from CASL and it's what the basis library demonstrates. Any new example or basis spec should follow this structure.

### Serialization round-trips

Every AST type must serialize to JSON (via a `"type"` discriminator field) and deserialize back to an identical object. When adding a new AST node: add a case to `formula_to_json`/`formula_from_json` (or `term_to_json`/`term_from_json`), add it to the `Formula` (or `Term`) union type, add it to `__init__.py` exports, and write a round-trip test.

## Working With the Repo

### Environment

The project requires Python ≥ 3.12 (for `type` statement syntax in `result.py` and `match` statements throughout). Use `uv` to manage the virtual environment and dependencies — it reads `pyproject.toml` directly. If `uv` isn't available, a standard venv with `pip install -e .` works fine.

### Running things

The CLI entry point is in `alspec/cli.py`, invoked via `main.py` or the console script registered in `pyproject.toml`. Check `--help` for available subcommands — these are evolving and may change.

### Tests

Tests live in `tests/`. Run with `pytest`. The most important tests are serialization round-trips (every spec must survive `dumps` → `loads` without change) and the basis library completeness checks.

### LLM integration

`llm.py` wraps the OpenAI SDK pointed at OpenRouter, with automatic Langfuse tracing via the `langfuse.openai` drop-in import. The Langfuse instance runs locally via Docker Compose (separate repo — not part of this project). Connection details go in `.env`:

```
OPENROUTER_API_KEY=sk-or-...
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_BASE_URL=http://localhost:3000
```

### Reference documentation

`gen_reference.py` produces `LANGUAGE_REFERENCE.md` by introspecting live code — it pulls source from example functions, profiles from basis specs, and the type grammar from the AST definitions. This generated document is what gets injected into LLM prompts as context. If you change the DSL, regenerate the reference and check that the type grammar and helper signatures are still accurate.

## Key Design Decisions (and Why)

**Why not use Maude/Hets/CafeOBJ?** These are full specification verification environments. We only need the type checker, not the theorem prover. The well-sortedness check is a tree walk over the AST — ~200 lines of Python, not a C++ runtime with a serialization layer.

**Why predicates separate from functions?** Following CASL. Predicates hold or don't hold — they don't return a sort. This is cleaner than Boolean-valued functions because predicates hold minimally in initial models, which matters for free/generated semantics.

**Why `Biconditional` as a primitive?** CASL has `⇔` as a first-class connective. Without it, LLMs writing predicate equivalence across constructors consistently write one direction of the implication and forget the other. The `iff()` helper prevents this class of errors.

**Why `FiniteMap` in the basis?** It's the fundamental "indexed collection" pattern. Any domain with state lookup (library books, vending machines, user accounts) is a FiniteMap. LLMs that see the `lookup_update_hit` / `lookup_update_miss` axiom pair in the basis learn to apply the pattern to new domains. Without it, they consistently omit the miss case.

**Why frozen dataclasses with tuple fields?** Immutability makes equality checking trivial (round-trip tests are just `==`), prevents accidental mutation of shared AST nodes, and makes the objects hashable for use in sets and dict keys.
