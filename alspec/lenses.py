"""Domain analysis via LLM lenses.

Stage 1 of the pipeline: apply a structured lens to domain source material
to produce a domain analysis that guides signature and axiom generation.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from alspec.llm import AsyncLLMClient, UsageInfo
from alspec.result import Err, Ok

logger = logging.getLogger(__name__)

# --- Configuration & Paths ---
DATA_DIR = Path("data/lens_experiment")
SOURCES_DIR = DATA_DIR / "sources"
LENSES_CACHE_DIR = DATA_DIR / "lenses"
ANALYSIS_CACHE_DIR = Path("data/analysis")

# --- Lens Definitions ---
# System prompts for each lens type.  Source material goes in the user message,
# not substituted into the system prompt.
LENS_PROMPTS: dict[str, str] = {
    "entity_lifecycle": """\
You are a domain analyst identifying the core entities, their lifecycles, and
relationships in a system.

Identify the following from the provided material:

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

Write the entity-lifecycle analysis now.""",
    "summary": """\
You are a technical writer summarizing a system for a software specification team.

Write a clear, comprehensive summary in 2-3 paragraphs (200-400 words) describing:
- What the system is and its core purpose
- How it works: the key entities, operations, and their relationships
- Important rules, constraints, and edge cases

Write in plain prose. Do NOT use bullet points, numbered lists, or structured formats.
Focus on behavioral facts, not history or implementation details.

Write your summary now.""",
}


def load_source(domain: str, source_path: str | None = None) -> str:
    """Load source material for a domain.

    Checks in order:
    1. Explicit source_path if provided
    2. data/lens_experiment/sources/{domain}.txt (cached sources from experiment)
    3. Returns empty string if no source available
    """
    if source_path:
        p = Path(source_path)
        if p.exists():
            return p.read_text()

    cached_source = SOURCES_DIR / f"{domain}.txt"
    if cached_source.exists():
        return cached_source.read_text()

    return ""


def load_sources(domain_id: str, extra_sources: list[Path] | None = None) -> str:
    """Load and concatenate source material for a domain.

    Sources are loaded in order:
    1. Extra sources from --source CLI flag (glob-expanded paths)
    2. Fallback: data/lens_experiment/sources/{domain}.txt

    Returns concatenated text with source headers, or empty string if no sources.
    """
    parts: list[str] = []

    if extra_sources:
        for src_path in extra_sources:
            if src_path.exists():
                parts.append(f"--- Source: {src_path.name} ---\n{src_path.read_text()}")

    if not parts:
        # Fallback to cached Wikipedia source
        cached = SOURCES_DIR / f"{domain_id}.txt"
        if cached.exists():
            parts.append(cached.read_text())

    return "\n\n".join(parts)


async def run_analysis(
    client: AsyncLLMClient,
    domain_id: str,
    domain_description: str,
    model: str,
    *,
    sources: list[Path] | None = None,
    lens_name: str = "entity_lifecycle",
    cached: bool = False,
) -> tuple[str, "StageUsage | None"]:
    """Run Stage 1: Domain Analysis.

    Returns (analysis_text, stage_usage).
    If cached=True, loads from disk and returns (text, None) for usage.
    If no source material available and lens is not 'none', runs lens on
    just the domain_description.
    If lens_name is 'none', returns ('', None).
    """
    from alspec.pipeline import StageUsage

    if lens_name == "none" or not lens_name:
        return "", None

    # Check cache
    cache_file = ANALYSIS_CACHE_DIR / domain_id / f"{lens_name}.txt"
    if cached and cache_file.exists():
        return cache_file.read_text(), None

    # Also check legacy lens cache location
    legacy_cache = LENSES_CACHE_DIR / domain_id / f"{lens_name}.txt"
    if cached and legacy_cache.exists():
        return legacy_cache.read_text(), None

    if lens_name not in LENS_PROMPTS:
        logger.warning("Unknown lens: %s. Skipping domain analysis.", lens_name)
        return "", None

    # Load source material
    source_text = load_sources(domain_id, extra_sources=sources)

    # Build messages
    system_prompt = LENS_PROMPTS[lens_name]

    if source_text:
        user_content = (
            f"Domain: {domain_description}\n\n" f"Source Material:\n\n{source_text}"
        )
    else:
        user_content = f"Domain: {domain_description}"

    messages: list[dict[str, str]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]

    metadata: dict[str, Any] = {
        "lens": lens_name,
        "domain": domain_id,
        "source_len": str(len(source_text)),
        "cached": "false",
    }

    # Use submit_analysis tool for structured extraction
    result = await client.generate_with_analysis_tool(
        messages,
        model=model,
        name=f"Stage 1 (Analysis) - {domain_id}",
        metadata=metadata,
    )

    match result:
        case Ok((analysis_text, usage)):
            # Save to cache
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            cache_file.write_text(analysis_text)
            return analysis_text, StageUsage("analysis", usage)
        case Err(e):
            raise RuntimeError(
                f"Stage 1 (Analysis) failed for {domain_id}/{lens_name}: {e}"
            )


async def apply_lens(
    source_text: str,
    lens_name: str,
    domain: str,
    model: str = "google/gemini-3-flash-preview",
    langfuse_session_id: str | None = None,
) -> str:
    """[DEPRECATED] Apply a lens to source material, returning the analysis text.

    Use run_analysis() instead — it integrates with the formal 4-stage pipeline.
    This function is kept for backward compatibility with experiment scripts.
    """
    if lens_name == "none" or not lens_name:
        return ""

    if lens_name == "raw_source":
        words = source_text.split()
        if len(words) > 2000:
            return " ".join(words[:2000])
        return source_text

    if lens_name not in LENS_PROMPTS:
        logger.warning("Unknown lens: %s. Falling back to bare label.", lens_name)
        return ""

    # Check cache
    cache_file = LENSES_CACHE_DIR / domain / f"{lens_name}.txt"
    if cache_file.exists():
        return cache_file.read_text()

    if not source_text.strip():
        logger.warning(
            "No source material for %s, cannot apply lens %s", domain, lens_name
        )
        return ""

    # LLM application — legacy path using generate_messages
    system_prompt = LENS_PROMPTS[lens_name]
    user_content = f"Domain: {domain}\n\nSource Material:\n\n{source_text}"

    # Initialize client
    client_res = AsyncLLMClient.from_env()
    match client_res:
        case Ok(client):
            pass
        case Err(e):
            raise RuntimeError(f"Failed to initialize LLM client: {e}")

    if langfuse_session_id:
        client._session_id = langfuse_session_id

    metadata: dict[str, Any] = {
        "lens": lens_name,
        "domain": domain,
        "source_len": str(len(source_text)),
        "cached": "false",
    }

    result = await client.generate_messages(
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        model=model,
        name=f"lens-{lens_name}-{domain}",
        metadata=metadata,
    )

    match result:
        case Ok((content, _usage)):
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            cache_file.write_text(content)
            return content
        case Err(e):
            raise RuntimeError(f"Lens call failed for {domain}/{lens_name}: {e}")
