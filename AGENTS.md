# AGENTS.md

## What This Is

`alspec` is a multi-stage LLM pipeline that generates formal CASL-style algebraic specifications from natural language domain descriptions. The pipeline takes a domain description (e.g., "a library lending system" or an IEC 61131-3 PLC counter datasheet) and produces a complete, scored algebraic specification with sorts, functions, predicates, and axioms.

The underlying Python DSL provides AST types, builder helpers, serialization, and a verified standard library for the formalism described in the CASL Reference Manual, Astesiano et al. (2001), and Sannella & Tarlecki (2012). `THEORY.md` is the canonical in-project theory reference.

## Pipeline Architecture

The pipeline has four stages:

1. **ANALYSIS** (LLM) — Structured domain analysis from source material. Uses a configurable "lens" (e.g., `entity_lifecycle`) to extract domain concepts, state transitions, and key sorts.

2. **SIGNATURE** (LLM) — Generates a `Signature` object with sorts, functions (constructors + observers), predicates, and `generated_sorts` annotations. The LLM produces Python code using the DSL helpers; this code is executed to produce the Signature.

3. **OBLIGATION** (deterministic) — Builds the obligation table (observer × constructor grid), generates mechanical axioms (selector extractions, MISS-case delegations), and produces the skeleton (imports, signature, mechanical axioms, constructor term abbreviations). The LLM never sees this code — it's infrastructure.

4. **AXIOMS** (LLM) — The LLM fills remaining obligation cells via a structured tool call (`submit_axiom_fills`). The skeleton provides the deterministic frame; the LLM provides variable declarations and formula fills. The splicer assembles the final `.py` spec file.

Stage outputs are typed dataclasses defined in `alspec/stages.py`. The pipeline composition lives in `alspec/pipeline.py`.

### Skeleton + Fills Architecture

Stage 4 does **not** ask the LLM to write a complete spec file. Instead:
- The **skeleton** (generated deterministically from the signature) provides: imports, the signature definition, mechanical axioms, constructor term abbreviations, and the `Spec(...)` wrapper.
- The **LLM** returns only: variable declarations and axiom formula fills, via a structured tool call.
- The **splicer** (`splice_fills()` in `skeleton.py`) assembles these into the final executable `.py` file.

This separation means the LLM only writes the parts that require domain reasoning. Syntax errors from mismatched imports or signature re-declaration are structurally impossible.

### The Obligation Table

The obligation table is the mathematical engine of the system. For each generated sort, it creates one cell per (observer, constructor) pair. Each cell must have an axiom: an equation for defined cases, `¬def(...)` for undefined cases, or delegation. Under loose semantics, missing a cell means the function is unconstrained — any behavior is permitted.

Cells are classified by dispatch (PLAIN, HIT, MISS) and tier (SELECTOR_EXTRACT, SELECTOR_FOREIGN, KEY_DISPATCH, BASE_CASE, DOMAIN). Mechanical tiers are filled automatically; DOMAIN cells require LLM reasoning. See `THEORY.md` §8 for the formal treatment.

## Prompt System

The Stage 2 and Stage 4 prompts use a modular **chunk architecture** (`alspec/prompt_chunks.py`). Chunks are registered with stage targets and dependencies, then assembled into system prompts. The winning Stage 4 config is mandatory chunks + primary worked examples (session-store, rate-limiter, dns-zone, connection) + secondary examples (counter, stack, bounded-counter).

**Guiding prompt philosophy: enrich examples over adding rules.** When improving LLM output, always prefer adding or improving worked examples over writing explicit rules or escape hatches. Worked examples teach the LLM in its own modality.

## Environment & Tooling

- **Python ≥ 3.12** required (for `type` statement syntax and `match` statements)
- **`uv`** for dependency management — all Python execution via `uv run`
- **Fish shell** — all terminal commands must use fish syntax
- **Gemini Flash** (`google/gemini-3-flash-preview`) is the primary model, accessed via OpenRouter
- **Langfuse** runs locally for LLM trace inspection; connection details in `.env`

```
OPENROUTER_API_KEY=sk-or-...
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_BASE_URL=http://localhost:3000
```

### Running Things

```fish
# Run the full pipeline for a domain
uv run alspec generate --domain door-lock

# Run the eval battery
uv run alspec eval --domains door-lock,counter --replicates 3 --csv results/test.csv -v

# Run eval with a pinned cache (skip Stages 1-2)
uv run alspec eval --cache cache/baseline-2026-03-09 --replicates 10 --csv results/test.csv

# Score existing spec files
uv run alspec score golden/stack.py golden/door-lock.py -v

# Run tests
uv run pytest tests/ -x -q
```

### Evaluation Infrastructure

The eval system runs the pipeline across a battery of ~17-20 domains at multiple replicates to measure parse rate, coverage, and health.

- **`alspec eval`** — the main CLI eval command with `--cache`, `--save-cache`, `--replicates`, `--save-specs`
- **`scripts/characterize_uncovered.py`** — detailed uncovered-cell analysis with `--cache`, `--save-cache`, `--domains`, `--replicates`
- **Pinned caches** — saved Stage 1/2 outputs in `cache/` directories (e.g., `cache/baseline-2026-03-09/`). Essential for isolating Stage 4 changes from Stage 2 variance.
- **Langfuse sessions** — each eval run creates a Langfuse session for trace inspection
- **Key metrics**: parse rate (does the generated code execute?), well-formed rate (does it pass the checker?), coverage ratio (what fraction of obligation cells have matching axioms?), health (composite score)

### Caches

Caches save frozen Stage 1/2 LLM outputs to disk so experiments can hold upstream stages constant while varying Stage 4. A cache directory contains `manifest.json` + per-domain JSON snapshots. Always pin caches when comparing Stage 4 changes — running without a cache introduces Stage 2 variance that can mask or fabricate regressions.

## Coding Conventions

### Fail loudly

Do not silently return `None`, empty collections, or default values when something is wrong. Raise exceptions with descriptive messages. Pipeline stages raise typed `StageError` subclasses (`AnalysisError`, `SignatureError`, `ObligationError`, `AxiomError`). The composition layer in `pipeline.py` catches these and converts to `PipelineResult`.

### Strong typing

All AST nodes are `@dataclass(frozen=True)`. All collections in AST nodes are tuples, not lists. Use `SortRef` (a `NewType` over `str`) wherever a sort name appears. Type annotations on every function signature. The `Term` and `Formula` union types are explicit and exhaustive.

### Parse, don't validate

`Term` and `Formula` are structurally distinct and cannot be mixed. `eq()` takes two `Term`s and returns a `Formula`. `Negation` takes a `Formula`, never a `Term`. If you find yourself casting or checking `isinstance` at a boundary, the types are wrong.

### Helpers are the public API

Code that constructs specs should use helpers from `helpers.py` (`fn`, `pred`, `var`, `app`, `const`, `eq`, `forall`, `iff`, etc.) rather than constructing dataclasses directly.

### Axiom methodology

This project uses **loose semantics**. Omitting an axiom does not make a function undefined — it leaves it unconstrained. Every cell in the obligation table must be explicitly filled. See `THEORY.md` for the full treatment.

### Serialization round-trips

Every AST type must serialize to JSON and deserialize back to an identical object. When adding a new AST node: add cases to `formula_to_json`/`formula_from_json` (or the term equivalents), add to the union type, add to `__init__.py` exports, and write a round-trip test.

## Key Design Decisions

**Compiler, not a frontend.** Fail loud and fast. No silent defaults. Strong typing throughout.

**Enrich examples over adding rules.** Worked examples teach the LLM in its own modality. Explicit rules and escape hatches in prompts are a last resort.

**Upstream fixes over downstream patches.** When a coverage failure traces to a missing signature element, fix Stage 2 rather than relaxing the axiom matcher.

**Scoring must be near-perfect.** False positives in coverage are worse than missed coverage. A `definedness`-only axiom covering a HIT cell is semantically under-specified and should not be accepted.

**Golden specs are no longer a strong reference.** LLM-generated specs tend to be richer. Avoid over-indexing on golden specs when evaluating quality.

**Obligation table is the critical foundation.** Finite axioms over constructors generate infinite behavioral coverage via structural induction. This is the mathematical engine of the system.

## Key Files

| File | Role |
|------|------|
| `alspec/stages.py` | Pipeline stage base class, typed stage outputs, all four stage implementations |
| `alspec/pipeline.py` | Thin composition layer: `run_pipeline()` composes stages into `PipelineResult` |
| `alspec/skeleton.py` | Skeleton generation, `splice_fills()`, constructor term abbreviation computation |
| `alspec/obligation.py` | Obligation table builder, cell dispatch/tier classification |
| `alspec/obligation_render.py` | Renders obligation table to Markdown for Stage 4 prompt |
| `alspec/axiom_gen.py` | Mechanical axiom generation (selector extractions, MISS delegations) |
| `alspec/axiom_match.py` | Coverage matcher — maps generated axioms to obligation cells |
| `alspec/prompt_chunks.py` | Chunk registry, dependency resolution, prompt assembly |
| `alspec/worked_example.py` | `WorkedExample` dataclass, `RenderMode` enum, rendering logic |
| `alspec/reference/worked_examples.py` | All worked examples (session-store, rate-limiter, dns-zone, connection, counter, stack, bounded-counter) |
| `alspec/score.py` | Full spec scoring (health, coverage, well-formedness diagnostics) |
| `alspec/check.py` | Well-sortedness checker |
| `alspec/llm.py` | OpenRouter client wrapper with Langfuse tracing |
| `alspec/cache.py` | Pipeline cache system (save/load Stage 1/2 snapshots) |
| `alspec/cli.py` | CLI entry point (`alspec eval`, `alspec generate`, `alspec score`) |
| `alspec/eval/harness.py` | Eval orchestration, `EvalResult`/`EvalRun` types |
| `alspec/eval/report.py` | Summary tables, CSV export, per-replicate aggregation |
| `alspec/eval/taxonomy.py` | Failure classification (parse vs well-formedness subcategories) |
| `alspec/eval/domains.py` | Domain battery definitions with complexity tiers and expected features |
| `scripts/characterize_uncovered.py` | Detailed uncovered-cell analysis script |
| `THEORY.md` | Canonical theory reference (CASL, obligation tables, axiom patterns) |
