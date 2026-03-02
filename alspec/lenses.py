"""Domain Lenses for Alspec Pipeline.

Provides preprocessing of raw domain material into structured analyses.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from pathlib import Path
from typing import Any

from alspec.llm import AsyncLLMClient
from alspec.result import Err, Ok

logger = logging.getLogger(__name__)

# --- Configuration & Paths ---
DATA_DIR = Path("data/lens_experiment")
SOURCES_DIR = DATA_DIR / "sources"
LENSES_CACHE_DIR = DATA_DIR / "lenses"

# --- Lens Definitions ---
LENS_PROMPTS = {
    "entity_lifecycle": """You are a domain analyst identifying the core entities, their lifecycles, and
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

    "summary": """You are a technical writer summarizing a system for a software specification team.

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

async def apply_lens(
    source_text: str,
    lens_name: str,
    domain: str,
    model: str = "google/gemini-3-flash-preview",
    langfuse_session_id: str | None = None,
) -> str:
    """Apply a lens to source material, returning the analysis text.
    
    - Uses the existing LLM client infrastructure.
    - Traces through Langfuse.
    - Caches results to data/lens_experiment/lenses/{domain}/{lens_name}.txt
    - For raw_source: no LLM call, just truncate to ~2000 words.
    """
    if lens_name == "none" or not lens_name:
        return ""

    if lens_name == "raw_source":
        # Pass raw source through with minimal processing
        words = source_text.split()
        if len(words) > 2000:
            return " ".join(words[:2000])
        return source_text

    if lens_name not in LENS_PROMPTS:
        logger.warning(f"Unknown lens: {lens_name}. Falling back to bare label.")
        return ""

    # Check cache
    cache_file = LENSES_CACHE_DIR / domain / f"{lens_name}.txt"
    if cache_file.exists():
        return cache_file.read_text()

    if not source_text.strip():
        logger.warning(f"No source material for {domain}, cannot apply lens {lens_name}")
        return ""

    # LLM application
    prompt = LENS_PROMPTS[lens_name].replace("{source_text}", source_text)
    
    # Initialize client
    client_res = AsyncLLMClient.from_env()
    match client_res:
        case Ok(client):
            pass
        case Err(e):
            raise RuntimeError(f"Failed to initialize LLM client: {e}")

    # Set session ID for tracing if provided
    if langfuse_session_id:
        client._session_id = langfuse_session_id

    metadata = {
        "lens": lens_name,
        "domain": domain,
        "source_len": len(source_text),
        "cached": False
    }

    result = await client.generate_messages(
        messages=[{"role": "user", "content": prompt}],
        model=model,
        name=f"lens-{lens_name}-{domain}",
        metadata=metadata,
    )

    match result:
        case Ok((content, _usage)):
            # Save to cache
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            cache_file.write_text(content)
            return content
        case Err(e):
            raise RuntimeError(f"Lens call failed for {domain}/{lens_name}: {e}")

def extract_python_code(raw: str) -> str:
    """[DEPRECATED] Extract bare Python code from a markdown-fenced LLM response.
    
    Tool calling (submit_signature) makes this obsolete for production pipeline use.
    """
    pattern = re.compile(
        r"```(?:python|py)\s*\n(.*?)\n?```",
        re.DOTALL | re.IGNORECASE,
    )
    blocks = pattern.findall(raw)
    match blocks:
        case []:
            return raw.strip()
        case [single]:
            return single.strip()
        case multiple:
            return max(multiple, key=len).strip()

def sanitize_unicode(text: str) -> str:
    """[DEPRECATED] Replace problematic Unicode with ASCII equivalents.
    
    Tool calling (submit_signature) eliminates the need for this in production use.
    """
    replacements = {
        "→": "->",
        "←": "<-",
        "≥": ">=",
        "≤": "<=",
        "×": "*",
        "…": "...",
        "\u2260": "!=",  # ≠ 
        "\u2208": "in",  # ∈
        "\u2200": "forall", # ∀
        "\u2203": "exists", # ∃
    }
    for k, v in replacements.items():
        text = text.replace(k, v)
    
    # Optional: strip other non-ASCII if they still cause issues
    # text = text.encode("ascii", "ignore").decode("ascii")
    return text
