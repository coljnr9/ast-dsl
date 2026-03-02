#!/usr/bin/env python3
"""Domain Lens Experiment — Wikipedia → Lens → Stage 1 pipeline.

Tests whether structured domain analysis (applied as a "lens" to raw
domain material) improves algebraic specification quality compared to
bare labels or unstructured prose.

Three phases (each cached independently):
  Phase 1: Fetch source material (Wikipedia articles or manual sources)
  Phase 2: Apply analysis lenses via LLM (one call per domain×lens)
  Phase 3: Run Stage 1 with lens output as user prompt, score against golden

Lenses tested:
  bare_label     — Current baseline: "auction simulation" (no source material)
  raw_source     — Dump source article directly as context (control)
  summary        — Unstructured 2-3 paragraph summary (tests: does format matter?)
  ears           — EARS requirements (While/When/If-Then/shall patterns)
  bdd            — Given/When/Then BDD scenarios
  failure_modes  — FMEA-style failure mode enumeration
  entity_lifecycle — Entity-state-transition analysis
  constraints    — Pure behavioral constraints/rules list

Usage:
    # Fetch sources (run once, cached)
    python experiments/domain_lens_experiment.py fetch

    # Apply lenses (run once per lens model, cached)
    python experiments/domain_lens_experiment.py apply-lenses

    # Run Stage 1 experiment
    python experiments/domain_lens_experiment.py run --replicates 3

    # All three phases
    python experiments/domain_lens_experiment.py all --replicates 3

    # Dry run (show what would happen)
    python experiments/domain_lens_experiment.py all --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import dataclasses
import hashlib
import json
import logging
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ─── Alspec imports (adjust if package structure differs) ──────────
from alspec.prompt_chunks import ChunkId, Stage, assemble_prompt
from alspec.eval.stage1_score import score_stage1_output
from alspec.llm import AsyncLLMClient
from alspec.result import Err, Ok

import os

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-5s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ─── Client Singleton ──────────────────────────────────────────────
_CLIENT: AsyncLLMClient | None = None

def get_client() -> AsyncLLMClient:
    """Return the shared AsyncLLMClient (Langfuse-instrumented)."""
    global _CLIENT
    if _CLIENT is not None:
        return _CLIENT
    result = AsyncLLMClient.from_env()
    match result:
        case Ok(client):
            _CLIENT = client
            return client
        case Err(e):
            raise RuntimeError(f"Failed to initialize LLM client: {e}")

# ─── Configuration ─────────────────────────────────────────────────

DATA_DIR = Path("data/lens_experiment")
SOURCES_DIR = DATA_DIR / "sources"
LENSES_DIR = DATA_DIR / "lenses"
RESULTS_DIR = Path("results")

# Foundation chunks for Stage 1 (same as saturation ladder)
FOUNDATION = [
    ChunkId.ROLE_PREAMBLE,
    ChunkId.TYPE_GRAMMAR,
    ChunkId.API_HELPERS,
    ChunkId.OBLIGATION_PATTERN,
]

# Best example set from saturation ladder R3
EXAMPLES = [
    ChunkId.EXAMPLE_RATE_LIMITER,
    ChunkId.EXAMPLE_SESSION_STORE,
    ChunkId.EXAMPLE_DNS_ZONE,
]

# Default models (OpenRouter format — adjust to match your setup)
LENS_MODEL = "google/gemini-2.5-flash-preview"  # cheap model for lens application
SPEC_MODEL = "google/gemini-2.5-flash-preview"  # same as saturation ladder baseline

# ─── Domain → Source Mapping ───────────────────────────────────────

DOMAIN_SOURCES: dict[str, str | None] = {
    # Wikipedia articles (fetched automatically)
    "auction":          "https://en.wikipedia.org/api/rest_v1/page/html/Auction",
    "thermostat":       "https://en.wikipedia.org/api/rest_v1/page/html/Thermostat",
    "bank-account":     "https://en.wikipedia.org/api/rest_v1/page/html/Bank_account",
    "door-lock":        "https://en.wikipedia.org/api/rest_v1/page/html/Lock_(security_device)",
    "email-inbox":      "https://en.wikipedia.org/api/rest_v1/page/html/Email",
    "traffic-light":    "https://en.wikipedia.org/api/rest_v1/page/html/Traffic_light",
    "phone-book":       "https://en.wikipedia.org/api/rest_v1/page/html/Telephone_directory",
    "library-lending":  "https://en.wikipedia.org/api/rest_v1/page/html/Library_circulation",
    "shopping-cart":    "https://en.wikipedia.org/api/rest_v1/page/html/Shopping_cart_software",
    "bug-tracker":      "https://en.wikipedia.org/api/rest_v1/page/html/Bug_tracking_system",
    "inventory":        "https://en.wikipedia.org/api/rest_v1/page/html/Inventory_management_software",
    "access-control":   "https://en.wikipedia.org/api/rest_v1/page/html/Access_control",
    "version-history":  "https://en.wikipedia.org/api/rest_v1/page/html/Version_control",
    # Manual sources (place .txt files in SOURCES_DIR)
    # These domains are CS abstractions — Wikipedia has data structure articles,
    # not domain knowledge. Provide manual sources from textbooks, docs, etc.
    "temperature-sensor": None,  # DS18B20 datasheet or SCADA reference
    "queue":              None,  # Python collections docs or algorithms textbook
    "stack":              None,  # Same — but also our teaching example, so useful control
    "counter":            None,  # PLC programming reference or CODESYS docs
    "bounded-counter":    None,  # Same as counter but with overflow semantics
    "boolean-flag":       None,  # Semaphore/mutex description from concurrency text
    "todo-list":          None,  # TodoMVC spec or task management product page
}

# Domains that have source material (auto-detected at runtime)
def get_sourced_domains() -> list[str]:
    """Return domains that have source .txt files available."""
    return [d for d in DOMAIN_SOURCES if (SOURCES_DIR / f"{d}.txt").exists()]

def get_all_eval_domains() -> list[str]:
    """Return all 20 eval domain IDs."""
    return list(DOMAIN_SOURCES.keys())


# ─── Lens Definitions ──────────────────────────────────────────────

@dataclass
class Lens:
    name: str
    description: str
    system_prompt: str
    needs_source: bool = True  # False for bare_label

LENSES: dict[str, Lens] = {
    "bare_label": Lens(
        name="bare_label",
        description="Current baseline — just the domain label, no source material",
        system_prompt="",  # unused — bare_label skips lens application
        needs_source=False,
    ),

    "raw_source": Lens(
        name="raw_source",
        description="Raw source article dumped as context (control for 'more info' vs 'structured info')",
        system_prompt="",  # unused — raw_source uses source text directly
        needs_source=True,
    ),

    "summary": Lens(
        name="summary",
        description="Unstructured 2-3 paragraph summary (control: does format matter?)",
        system_prompt="""\
You are a technical writer summarizing a system for a software specification team.

Read the following article about a real-world system. Write a clear, comprehensive
summary in 2-3 paragraphs (200-400 words) describing:
- What the system is and its core purpose
- How it works: the key entities, operations, and their relationships
- Important rules, constraints, and edge cases

Write in plain prose. Do NOT use bullet points, numbered lists, or structured formats.
Focus on behavioral facts, not history or implementation details.

ARTICLE:
{source_text}

Write your summary now.""",
    ),

    "ears": Lens(
        name="ears",
        description="EARS requirements — While/When/If-Then/shall patterns (Mavin 2009)",
        system_prompt="""\
You are a requirements engineer using the EARS notation (Easy Approach to
Requirements Syntax) to extract behavioral requirements from domain descriptions.

EARS patterns:
  Ubiquitous:     The <system> shall <response>
  State-driven:   While <precondition>, the <system> shall <response>
  Event-driven:   When <trigger>, the <system> shall <response>
  Unwanted:       If <bad trigger>, then the <system> shall <response>
  Complex:        While <precondition>, when <trigger>, the <system> shall <response>

Read the following article and extract ALL behavioral requirements as EARS statements.
Be thorough — capture:
- Normal operations (what the system does)
- State-dependent behavior (what changes based on current state)
- Preconditions (what must be true before an operation)
- Error/rejection cases (what happens when operations fail)
- Preservation rules (what stays unchanged after operations)
- Scope boundaries (what the system deliberately does NOT do)

Use the system name from the article. Write 15-30 EARS requirements.

ARTICLE:
{source_text}

Write the EARS requirements now, one per line.""",
    ),

    "bdd": Lens(
        name="bdd",
        description="BDD Given/When/Then scenarios covering normal and error paths",
        system_prompt="""\
You are a QA engineer writing BDD (Behavior-Driven Development) scenarios for
a system specification. Use Gherkin syntax: Given/When/Then.

Read the following article and write scenarios covering:
- Happy paths (normal operations succeed)
- Precondition violations (operations rejected due to invalid state)
- State transitions (system moves between states)
- Edge cases (boundary conditions, empty/full states)
- Query operations (checking current state)
- Error handling (what happens when things go wrong)

Each scenario should have:
  Given <initial state or preconditions>
  When <action or event>
  Then <expected outcome or state change>

Write 15-25 scenarios. Include both positive and negative cases.

ARTICLE:
{source_text}

Write the BDD scenarios now.""",
    ),

    "failure_modes": Lens(
        name="failure_modes",
        description="FMEA-style failure mode enumeration — what can go wrong?",
        system_prompt="""\
You are a reliability engineer performing a Failure Mode Analysis on a system.
Your goal is to identify every way operations can fail, be rejected, or produce
unexpected results.

Read the following article and for each operation or action in the system:
1. List the operation
2. Identify ALL failure modes: What preconditions can be violated? What states
   make the operation invalid? What inputs are rejected?
3. For each failure, describe: What should happen? (rejected? ignored? error state?)
4. Identify what the system must preserve even when failures occur

Also identify:
- States that cannot be reversed (permanent transitions)
- Operations that are impossible in certain states
- Combinations of conditions that create edge cases
- What is deliberately out of scope (operations the system does NOT support)

Be exhaustive. The goal is to find every boundary and constraint.

ARTICLE:
{source_text}

Write the failure mode analysis now.""",
    ),

    "entity_lifecycle": Lens(
        name="entity_lifecycle",
        description="Entity-state-transition analysis — who exists, what states, what transitions",
        system_prompt="""\
You are a domain analyst identifying the core entities, their lifecycles, and
relationships in a system.

Read the following article and identify:

ENTITIES: What are the distinct things in this system? For each entity:
  - What data does it carry?
  - Is it created, modified, or destroyed? How?
  - Does it have states? What are the valid transitions?

OPERATIONS: What actions can be performed? For each:
  - What entities are involved?
  - What preconditions must hold?
  - What changes afterward?
  - What stays the same?

RELATIONSHIPS: How do entities relate to each other?
  - Which entities reference others?
  - Are there ownership or containment relationships?
  - Are there lookup/indexing relationships?

INVARIANTS: What must always be true?
  - Constraints that span multiple entities
  - Properties preserved across all operations
  - Uniqueness or ordering guarantees

ARTICLE:
{source_text}

Write the entity-lifecycle analysis now.""",
    ),

    "constraints": Lens(
        name="constraints",
        description="Pure behavioral constraints/rules — no structure imposed",
        system_prompt="""\
You are a domain expert listing every rule, restriction, and behavioral constraint
that governs a system.

Read the following article and extract every behavioral rule you can find.
Write each rule as a single, clear sentence in domain language. Examples:
  "Only registered bidders can place bids."
  "The auction can be permanently closed."
  "Bids cannot be withdrawn once placed."

Include:
- Who can do what (participation rules)
- When actions are allowed or forbidden (preconditions)
- What changes when actions occur (effects)
- What doesn't change when actions occur (preservation)
- What states exist and which transitions are possible (lifecycle)
- What is deliberately not supported (scope boundaries)
- What values are tracked and how they relate (data semantics)

Be thorough. Write 15-30 rules. Each rule should be independently understandable.

ARTICLE:
{source_text}

Write the behavioral rules now, one per line.""",
    ),
}


# ─── Phase 1: Fetch Source Material ────────────────────────────────

def clean_html_to_text(html: str) -> str:
    """Strip HTML tags and clean Wikipedia HTML to plain text."""
    # Remove script/style content
    text = re.sub(r'<(script|style)[^>]*>.*?</\1>', '', html, flags=re.DOTALL)
    # Remove HTML tags but keep content
    text = re.sub(r'<[^>]+>', ' ', text)
    # Decode HTML entities
    import html as html_mod
    text = html_mod.unescape(text)
    # Remove citation brackets
    text = re.sub(r'\[\d+\]', '', text)
    text = re.sub(r'\[citation needed\]', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\[edit\]', '', text)
    # Collapse whitespace
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    # Trim to first ~4000 words (enough context, avoids token explosion in lens phase)
    words = text.split()
    if len(words) > 4000:
        text = ' '.join(words[:4000])
    return text.strip()


def fetch_sources(dry_run: bool = False) -> None:
    """Phase 1: Fetch Wikipedia articles for all mapped domains."""
    import requests

    SOURCES_DIR.mkdir(parents=True, exist_ok=True)

    for domain, url in DOMAIN_SOURCES.items():
        outfile = SOURCES_DIR / f"{domain}.txt"

        if outfile.exists():
            words = len(outfile.read_text().split())
            print(f"  ✓ {domain}: cached ({words} words)")
            continue

        if url is None:
            print(f"  ⚠ {domain}: needs manual source → {outfile}")
            continue

        if dry_run:
            print(f"  … {domain}: would fetch {url}")
            continue

        print(f"  ↓ {domain}: fetching...", end=" ", flush=True)
        try:
            resp = requests.get(url, timeout=30, headers={
                "User-Agent": "AlspecExperiment/1.0 (domain lens research)"
            })
            resp.raise_for_status()
            text = clean_html_to_text(resp.text)
            outfile.write_text(text)
            print(f"{len(text.split())} words")
        except Exception as e:
            print(f"FAILED: {e}")

    # Report status
    have = [d for d in DOMAIN_SOURCES if (SOURCES_DIR / f"{d}.txt").exists()]
    missing = [d for d in DOMAIN_SOURCES if not (SOURCES_DIR / f"{d}.txt").exists()]
    print(f"\n  Sources: {len(have)}/{len(DOMAIN_SOURCES)} domains ready")
    if missing:
        print(f"  Missing: {', '.join(missing)}")
        print(f"  Drop .txt files in {SOURCES_DIR}/ for manual domains")


# ─── Phase 2: Apply Lenses ─────────────────────────────────────────

async def apply_lens_one(
    domain: str,
    lens: Lens,
    source_text: str,
    model: str,
    sem: asyncio.Semaphore,
) -> str:
    """Apply a single lens to a single domain's source text."""
    prompt = lens.system_prompt.replace("{source_text}", source_text)

    client = get_client()
    async with sem:
        result = await client.generate_messages(
            messages=[{"role": "user", "content": prompt}],
            model=model,
            name=f"lens-{lens.name}-{domain}",
        )
    match result:
        case Ok((content, _usage)):
            return content
        case Err(e):
            raise RuntimeError(f"Lens call failed for {domain}/{lens.name}: {e}")


async def apply_lenses(
    model: str = LENS_MODEL,
    concurrency: int = 10,
    dry_run: bool = False,
) -> None:
    """Phase 2: Apply all lenses to all sourced domains."""
    LENSES_DIR.mkdir(parents=True, exist_ok=True)
    sourced = get_sourced_domains()
    sem = asyncio.Semaphore(concurrency)

    # Only lenses that need LLM application
    active_lenses = {k: v for k, v in LENSES.items()
                     if k not in ("bare_label", "raw_source")}

    tasks = []
    for domain in sourced:
        source_text = (SOURCES_DIR / f"{domain}.txt").read_text()
        lens_dir = LENSES_DIR / domain
        lens_dir.mkdir(exist_ok=True)

        for lens_name, lens in active_lenses.items():
            outfile = lens_dir / f"{lens_name}.txt"
            if outfile.exists():
                print(f"  ✓ {domain}/{lens_name}: cached")
                continue

            if dry_run:
                print(f"  … {domain}/{lens_name}: would apply lens")
                continue

            async def _run(d=domain, ln=lens_name, l=lens, st=source_text, of=outfile):
                print(f"  ⚙ {d}/{ln}...", flush=True)
                try:
                    result = await apply_lens_one(d, l, st, model, sem)
                    of.write_text(result)
                    print(f"  ✓ {d}/{ln}: {len(result.split())} words")
                except Exception as e:
                    print(f"  ✗ {d}/{ln}: {e}")

            tasks.append(_run())

    if tasks:
        print(f"\n  Applying {len(tasks)} lens calls ({concurrency} concurrent)...")
        await asyncio.gather(*tasks)
    else:
        print("  All lens outputs cached.")


# ─── Phase 3: Run Stage 1 Experiment ───────────────────────────────

def build_user_prompt(domain: str, lens_name: str) -> str:
    """Construct the user prompt for Stage 1 based on the lens."""
    # Get domain label (used in all arms)
    domain_label = domain.replace("-", " ")

    if lens_name == "bare_label":
        # Current baseline: just the label
        return f"Write an algebraic specification for: {domain_label}"

    source_file = SOURCES_DIR / f"{domain}.txt"
    if not source_file.exists():
        # No source → fall back to bare label
        return f"Write an algebraic specification for: {domain_label}"

    if lens_name == "raw_source":
        # Dump source article as context (truncate to ~2000 words to match lens output length)
        source = source_file.read_text()
        words = source.split()
        if len(words) > 2000:
            source = ' '.join(words[:2000])
        return (
            f"Write an algebraic specification for: {domain_label}\n\n"
            f"Here is reference material about this domain:\n\n{source}"
        )

    # Lens output
    lens_file = LENSES_DIR / domain / f"{lens_name}.txt"
    if not lens_file.exists():
        print(f"  ⚠ Missing lens output: {domain}/{lens_name}, falling back to bare_label")
        return f"Write an algebraic specification for: {domain_label}"

    lens_output = lens_file.read_text()
    return (
        f"Write an algebraic specification for: {domain_label}\n\n"
        f"Here is a domain analysis to guide your specification:\n\n{lens_output}"
    )


def build_system_prompt() -> str:
    """Build the Stage 1 system prompt using foundation + best examples."""
    chunks = FOUNDATION + EXAMPLES
    return assemble_prompt(chunks, Stage.STAGE1, validate_deps=False, validate_stage=False)


def extract_python_code(raw: str) -> str:
    """[DEPRECATED] Extract bare Python code from a markdown-fenced LLM response.
    
    Now unnecessary as the experiment uses tool calling (submit_signature) directly.
    """
    # Match ```python or ```py fences (case-insensitive tag)
    pattern = re.compile(
        r"```(?:python|py)\s*\n(.*?)\n?```",
        re.DOTALL | re.IGNORECASE,
    )
    blocks = pattern.findall(raw)
    match blocks:
        case []:
            # No fenced block found — return raw text; scorer will classify the failure
            return raw.strip()
        case [single]:
            return single.strip()
        case multiple:
            # Multiple blocks: return the longest one (most likely the full spec)
            return max(multiple, key=len).strip()


def prepare_code_for_scorer(code: str) -> str:
    """[DEPRECATED] Make extracted code ready for the scorer's exec() + namespace search.
    
    Now unnecessary as the experiment uses tool calling (submit_signature) directly.
    """
    # Look for a top-level def (not indented)
    func_match = re.search(r"^def\s+(\w+)\s*\(", code, re.MULTILINE)
    if func_match is None:
        return code

    func_name = func_match.group(1)
    # Append a call that handles both Spec-returning and Signature-returning fns
    epilogue = f"""

# --- auto-call appended by domain_lens_experiment ---
_result = {func_name}()
if hasattr(_result, 'signature'):
    # Function returned a Spec; expose the Signature
    sig = _result.signature
else:
    # Function returned a Signature directly
    sig = _result
"""
    return code + epilogue


async def run_one_cell(
    domain: str,
    lens_name: str,
    system_prompt: str,
    model: str,
    replicate: int,
    sem: asyncio.Semaphore,
) -> dict[str, Any]:
    """Run one (domain, lens, replicate) cell and score it."""
    user_prompt = build_user_prompt(domain, lens_name)

    client = get_client()
    t0 = time.time()
    async with sem:
        result = await client.generate_with_tool_call(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            model=model,
            tool_name="submit_signature",
            name=f"lens-s1-{domain}-{lens_name}-r{replicate}",
        )

    match result:
        case Err(e):
            return {
                "domain": domain,
                "lens": lens_name,
                "replicate": replicate,
                "error": str(e),
                "elapsed": time.time() - t0,
            }
        case Ok((analysis, code, _usage)):
            elapsed = time.time() - t0

    # Score against golden spec
    try:
        score = score_stage1_output(code, domain, replicate=replicate, model=model)
        score_dict = dataclasses.asdict(score)
        # Serialize enums to their .value strings for JSON compatibility
        score_dict = {k: (v.value if hasattr(v, 'value') else v) for k, v in score_dict.items()}
    except Exception as e:
        score_dict = {"error": str(e), "parse_ok": False}

    return {
        "domain": domain,
        "lens": lens_name,
        "replicate": replicate,
        "elapsed": elapsed,
        "raw_output": code,  # Use code as raw output for reference
        "analysis": analysis,
        "user_prompt_tokens": len(user_prompt) // 4,  # rough estimate
        **score_dict,
    }


async def run_experiment(
    replicates: int = 3,
    model: str = SPEC_MODEL,
    concurrency: int = 10,
    dry_run: bool = False,
    lenses_to_run: list[str] | None = None,
    domains_to_run: list[str] | None = None,
    session_id: str | None = None,
) -> None:
    """Phase 3: Run Stage 1 for all (domain, lens) cells."""
    # Determine which lenses and domains to run
    all_lenses = list(LENSES.keys()) if lenses_to_run is None else lenses_to_run
    sourced = get_sourced_domains()
    all_domains = domains_to_run or get_all_eval_domains()

    # Filter: lenses needing source only run on sourced domains
    cells = []
    for lens_name in all_lenses:
        lens = LENSES[lens_name]
        for domain in all_domains:
            if lens.needs_source and domain not in sourced:
                continue  # skip unsourced domains for source-dependent lenses
            for rep in range(replicates):
                cells.append((domain, lens_name, rep))

    # Setup
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    run_dir = RESULTS_DIR / f"lens_experiment_{timestamp}"
    run_dir.mkdir(parents=True, exist_ok=True)

    # Set session ID on the shared client for Langfuse grouping
    if session_id is not None:
        client = get_client()
        client._session_id = session_id

    system_prompt = build_system_prompt()
    sys_tokens = len(system_prompt) // 4

    logger.info("="*60)
    logger.info("Domain Lens Experiment")
    logger.info("="*60)
    logger.info("  Lenses:     %s", ', '.join(all_lenses))
    logger.info("  Domains:    %d (%d with sources)", len(all_domains), len(sourced))
    logger.info("  Replicates: %d", replicates)
    logger.info("  Total cells: %d", len(cells))
    logger.info("  Model:      %s", model)
    logger.info("  System prompt: ~%s tokens", f"{sys_tokens:,}")
    logger.info("  Session ID: %s", session_id or "(none)")
    logger.info("  Output dir: %s", run_dir)
    logger.info("="*60)

    if dry_run:
        print("DRY RUN — would execute the above. Exiting.")
        return

    # Run all cells
    sem = asyncio.Semaphore(concurrency)
    results = []
    done = 0

    async def _run(domain, lens_name, rep):
        nonlocal done
        r = await run_one_cell(domain, lens_name, system_prompt, model, rep, sem)
        done += 1
        health = r.get("health", "err")
        status = f"{health:.2f}" if isinstance(health, float) else health
        print(f"  [{done}/{len(cells)}] {domain}/{lens_name}/r{rep}: {status}")
        results.append(r)

    tasks = [_run(d, l, r) for d, l, r in cells]
    await asyncio.gather(*tasks)

    # Save raw results as JSONL (excluding raw_output for size)
    jsonl_path = run_dir / "results.jsonl"
    with open(jsonl_path, "w") as f:
        for r in results:
            row = {
                k: (v.value if hasattr(v, "value") else v)
                for k, v in r.items()
                if k != "raw_output"
            }
            f.write(json.dumps(row) + "\n")

    # Save full results (including raw output) for debugging
    full_path = run_dir / "results_full.jsonl"
    with open(full_path, "w") as f:
        for r in results:
            row = {k: (v.value if hasattr(v, "value") else v) for k, v in r.items()}
            f.write(json.dumps(row) + "\n")

    # Aggregate and save CSV
    write_aggregate_csv(results, run_dir)
    write_per_domain_csv(results, run_dir)

    print(f"\n  Results saved to {run_dir}/")


def write_aggregate_csv(results: list[dict], run_dir: Path) -> None:
    """Write aggregate scores per lens."""
    from collections import defaultdict
    import statistics

    by_lens: dict[str, list[float]] = defaultdict(list)
    parse_by_lens: dict[str, list[bool]] = defaultdict(list)
    fuzzy_by_lens: dict[str, list[float]] = defaultdict(list)

    for r in results:
        if "error" in r:
            continue
        lens = r["lens"]
        if "health" in r and isinstance(r["health"], (int, float)):
            by_lens[lens].append(r["health"])
        if "parse_ok" in r:
            parse_by_lens[lens].append(r["parse_ok"])
        if "fuzzy_health" in r and isinstance(r["fuzzy_health"], (int, float)):
            fuzzy_by_lens[lens].append(r["fuzzy_health"])

    path = run_dir / "aggregate.csv"
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["lens", "n", "health_mean", "health_median", "health_std",
                     "fuzzy_mean", "parse_rate"])
        for lens in LENSES:
            if lens not in by_lens:
                continue
            vals = by_lens[lens]
            fvals = fuzzy_by_lens.get(lens, [])
            pvals = parse_by_lens.get(lens, [])
            w.writerow([
                lens,
                len(vals),
                f"{statistics.mean(vals):.4f}",
                f"{statistics.median(vals):.4f}",
                f"{statistics.stdev(vals):.4f}" if len(vals) > 1 else "0",
                f"{statistics.mean(fvals):.4f}" if fvals else "",
                f"{sum(pvals)/len(pvals):.2f}" if pvals else "",
            ])

    print(f"\n  Aggregate scores:")
    with open(path) as f:
        print(f.read())


def write_per_domain_csv(results: list[dict], run_dir: Path) -> None:
    """Write per-domain scores for each lens (median over replicates)."""
    from collections import defaultdict
    import statistics

    # Group: (domain, lens) → [health values]
    groups: dict[tuple[str, str], list[float]] = defaultdict(list)
    for r in results:
        if "error" in r:
            continue
        if "health" in r and isinstance(r["health"], (int, float)):
            groups[(r["domain"], r["lens"])].append(r["health"])

    # Get unique domains and lenses
    domains = sorted({d for d, _ in groups})
    lenses = [l for l in LENSES if any(l == ll for _, ll in groups)]

    path = run_dir / "per_domain.csv"
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["domain"] + lenses)
        for domain in domains:
            row = [domain]
            for lens in lenses:
                vals = groups.get((domain, lens), [])
                row.append(f"{statistics.median(vals):.4f}" if vals else "")
            w.writerow(row)


# ─── CLI ───────────────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser(
        description="Domain Lens Experiment — Wikipedia → Lens → Stage 1 pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = p.add_subparsers(dest="command", required=True)

    # fetch
    fetch_p = sub.add_parser("fetch", help="Phase 1: Fetch Wikipedia source articles")
    fetch_p.add_argument("--dry-run", action="store_true")

    # apply-lenses
    lens_p = sub.add_parser("apply-lenses", help="Phase 2: Apply analysis lenses via LLM")
    lens_p.add_argument("--model", default=LENS_MODEL)
    lens_p.add_argument("--concurrency", type=int, default=10)
    lens_p.add_argument("--dry-run", action="store_true")

    # run
    run_p = sub.add_parser("run", help="Phase 3: Run Stage 1 experiment")
    run_p.add_argument("--replicates", type=int, default=3)
    run_p.add_argument("--model", default=SPEC_MODEL)
    run_p.add_argument("--concurrency", type=int, default=10)
    run_p.add_argument("--lenses", nargs="+", help="Subset of lenses to run")
    run_p.add_argument("--domains", nargs="+", help="Subset of domains to run")
    run_p.add_argument("--dry-run", action="store_true")

    # all
    all_p = sub.add_parser("all", help="Run all three phases")
    all_p.add_argument("--replicates", type=int, default=3)
    all_p.add_argument("--model", default=SPEC_MODEL)
    all_p.add_argument("--lens-model", default=LENS_MODEL)
    all_p.add_argument("--concurrency", type=int, default=10)
    all_p.add_argument("--lenses", nargs="+", help="Subset of lenses to run")
    all_p.add_argument("--domains", nargs="+", help="Subset of domains to run")
    all_p.add_argument("--dry-run", action="store_true")

    args = p.parse_args()

    # Generate a session ID for Langfuse grouping
    timestamp = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    session_id = f"domain-lens-{timestamp}"

    # Set session ID on the client eagerly (covers lens calls too)
    client = get_client()
    client._session_id = session_id
    logger.info("Langfuse session ID: %s", session_id)

    if args.command == "fetch":
        print("\n=== Phase 1: Fetch Sources ===\n")
        fetch_sources(dry_run=args.dry_run)

    elif args.command == "apply-lenses":
        print("\n=== Phase 2: Apply Lenses ===\n")
        asyncio.run(apply_lenses(
            model=args.model,
            concurrency=args.concurrency,
            dry_run=args.dry_run,
        ))

    elif args.command == "run":
        print("\n=== Phase 3: Run Experiment ===\n")
        asyncio.run(run_experiment(
            replicates=args.replicates,
            model=args.model,
            concurrency=args.concurrency,
            dry_run=args.dry_run,
            lenses_to_run=args.lenses,
            domains_to_run=args.domains,
            session_id=session_id,
        ))

    elif args.command == "all":
        # Use --model for both phases unless --lens-model explicitly overrides
        lens_model = args.lens_model if args.lens_model != LENS_MODEL else args.model

        print("\n=== Phase 1: Fetch Sources ===\n")
        fetch_sources(dry_run=args.dry_run)

        print("\n=== Phase 2: Apply Lenses ===\n")
        asyncio.run(apply_lenses(
            model=lens_model,
            concurrency=args.concurrency,
            dry_run=args.dry_run,
        ))

        print("\n=== Phase 3: Run Experiment ===\n")
        asyncio.run(run_experiment(
            replicates=args.replicates,
            model=args.model,
            concurrency=args.concurrency,
            dry_run=args.dry_run,
            lenses_to_run=args.lenses,
            domains_to_run=args.domains,
            session_id=session_id,
        ))


if __name__ == "__main__":
    main()
