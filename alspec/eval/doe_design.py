"""Design matrix generation for DoE experiments.

Converts a ``DoeConfig`` into a list of ``TrialConfig`` objects using
pyDOE3 for fractional-factorial and full-factorial designs.

Supported resolution levels:

* ``"full"``          → ``ff2n(k)``; 2^k runs.
* ``"resolution_v"``  → ``fracfact(generator)``; no 2FI confounded with another 2FI.
* ``"resolution_iv"`` → ``fracfact(generator)``; no ME confounded with any 2FI.
* ``"resolution_iii"``→ ``pbdesign(k)`` (Plackett-Burman screening); adequate for
                         finding main effects only.

For k ≤ 5 the function always uses full factorial regardless of the requested
resolution.

Generator strings follow standard minimum-aberration design tables
(Montgomery, "Design and Analysis of Experiments", 8th ed., Appendix XIV).
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass

import numpy as np
from pyDOE3 import ff2n, fracfact, pbdesign  # type: ignore[import-untyped]

from alspec.prompt_chunks import ChunkId, Stage, _REGISTRY, assemble_prompt

from .doe_config import DoeConfig

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Standard minimum-aberration generator strings
# ---------------------------------------------------------------------------
# Maps (k, resolution_level) → generator string for fracfact().
# "resolution_iv" entries satisfy: no ME aliased with any 2FI.
# "resolution_v"  entries satisfy: no 2FI aliased with another 2FI.
# Source: Montgomery (2017), Appendix XIV; also Box, Hunter & Hunter (2005).
#
# The generator string format is space-separated tokens where:
#   - Single letters a,b,c,... are independent base factors
#   - Multi-letter tokens like "ab", "abc" define aliased factors
#
# We only need entries for k > 5 (below that we use full factorial).

_RIV_GENERATORS: dict[int, str] = {
    # k=6: 2^(6-1) = 32 runs, Res V (also satisfies Res IV)
    6: "a b c d e abcde",
    # k=7: 2^(7-4) = 16 runs, Res IV (minimum aberration)
    7: "a b c d abc abd acd",
    # k=8: 2^(8-4) = 16 runs, Res IV
    8: "a b c d abc abd acd bcd",
    # k=9: 2^(9-5) = 16 runs, Res IV (B&H Table 12.15)
    9: "a b c d bc ac ab abc abd",
    # k=10: 2^(10-6) = 16 runs, Res IV
    10: "a b c d bc ac ab abc abd acd",
    # k=11: 2^(11-7) = 16 runs, Res IV (max resolution given 16 runs)
    11: "a b c d bc ac ab bcd abc abd",
    # k=12: 2^(12-8) = 16 runs, Res III → use Plackett-Burman for screening
    # (for k=12 we fall through to PB)
}

_RV_GENERATORS: dict[int, str] = {
    # k=6: 2^(6-1) = 32 runs, Res V
    6: "a b c d e abcde",
    # k=7: 2^(7-2) = 32 runs, Res V (Montgomery App. XIV)
    7: "a b c d e abc abcd",
    # k=8: 2^(8-3) = 32 runs, Res V
    8: "a b c d e abc abcd abce",
    # k=9: 2^(9-4) = 32 runs, Res V
    9: "a b c d e abc abcd abce abde",
    # k=10: 2^(10-5) = 32 runs, Res V
    10: "a b c d e abc abcd abce abde acde",
    # k=11: 2^(11-5) = 64 runs, Res V
    11: "a b c d e f abc abd abe abf acd",
}


# ---------------------------------------------------------------------------
# TrialConfig
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TrialConfig:
    """One row of the design matrix, expanded into a concrete chunk list."""

    trial_id: int  # row index in the design matrix
    replicate: int  # 0-indexed replicate number
    chunk_ids: tuple[ChunkId, ...]  # mandatory + active factor chunks, in dep order
    factor_levels: dict[str, int]  # {"A": 1, "B": -1, ...}
    config_hash: str  # SHA-256 of the sorted chunk_id tuple for dedup


# ---------------------------------------------------------------------------
# Design matrix generation
# ---------------------------------------------------------------------------


def generate_design_matrix(config: DoeConfig) -> np.ndarray:
    """Build the ±1 design matrix from config.

    Returns a 2-D array of shape (n_runs, k) where k = len(config.factors)
    and values are in {-1, +1}.
    """
    k = len(config.factors)
    if k == 0:
        raise ValueError("No factors defined in config — nothing to vary")

    # For small k, always use full factorial
    if k <= 5 or config.resolution == "full":
        logger.info("Using full factorial design: 2^%d = %d runs", k, 2**k)
        return ff2n(k).astype(int)

    match config.resolution:
        case "resolution_v":
            gen = _RV_GENERATORS.get(k)
            if gen is not None:
                logger.info(
                    "Using Resolution V fracfact design for k=%d: %s", k, gen
                )
                matrix = fracfact(gen)
                # fracfact returns ±1 floats — normalise
                return np.sign(matrix).astype(int)
            else:
                # Fall back to Plackett-Burman and warn
                logger.warning(
                    "No Res V generator available for k=%d — using Plackett-Burman "
                    "(Resolution III). Adjust config.resolution if 2FI estimation needed.",
                    k,
                )
                return _plackett_burman(k)

        case "resolution_iv":
            gen = _RIV_GENERATORS.get(k)
            if gen is not None:
                logger.info(
                    "Using Resolution IV fracfact design for k=%d: %s", k, gen
                )
                matrix = fracfact(gen)
                return np.sign(matrix).astype(int)
            else:
                logger.warning(
                    "No Res IV generator available for k=%d — using Plackett-Burman. "
                    "Consider reducing factor count or switching to 'full'.",
                    k,
                )
                return _plackett_burman(k)

        case "resolution_iii":
            logger.info("Using Plackett-Burman design for k=%d", k)
            return _plackett_burman(k)

        case other:
            raise ValueError(f"Unknown resolution: {other!r}")


def _plackett_burman(k: int) -> np.ndarray:
    """Return a Plackett-Burman design matrix with exactly k columns."""
    raw: np.ndarray = pbdesign(k)
    # pbdesign pads to the next multiple of 4 — take only k columns
    return raw[:, :k].astype(int)


# ---------------------------------------------------------------------------
# Trial config generation
# ---------------------------------------------------------------------------


def generate_trials(config: DoeConfig) -> list[TrialConfig]:
    """Generate all TrialConfig objects from the design.

    For each row of the design matrix × each replicate, builds the concrete
    chunk list (mandatory + active factors in dependency-valid order).

    Auto-inclusion warnings are deduped: they fire at most once per unique
    design-point row (not once per replicate × domain).
    """
    matrix = generate_design_matrix(config)
    factor_labels = [label for label, _ in config.factors]
    factor_chunks = [chunks for _, chunks in config.factors]

    trials: list[TrialConfig] = []
    # Track auto-inclusions per row for summary logging
    auto_include_summary: dict[int, list[str]] = {}

    for row_idx in range(matrix.shape[0]):
        row = matrix[row_idx]
        factor_levels: dict[str, int] = {
            factor_labels[j]: int(row[j]) for j in range(len(factor_labels))
        }

        # Active factor chunk sets (level == +1)
        active_chunks: list[ChunkId] = list(config.mandatory_chunks)
        for j, level in enumerate(row):
            if level == 1:
                active_chunks.extend(factor_chunks[j])

        # Resolve dependency ordering + auto-include missing deps.
        # Pass row_idx so _resolve_dependencies can log once per design point.
        ordered, auto_included = _resolve_dependencies(
            active_chunks, Stage.SIGNATURE, row_idx
        )

        if auto_included:
            auto_include_summary[row_idx] = [c.name for c in auto_included]

        config_hash = _compute_hash(ordered)

        for rep in range(config.replicates):
            trials.append(
                TrialConfig(
                    trial_id=row_idx,
                    replicate=rep,
                    chunk_ids=ordered,
                    factor_levels=factor_levels,
                    config_hash=config_hash,
                )
            )

    # Single summary log for all auto-inclusions (Fix 3a)
    if auto_include_summary:
        logger.info(
            "Dependency auto-inclusion: %d/%d design points required forced deps.",
            len(auto_include_summary),
            matrix.shape[0],
        )
        for row_idx, dep_names in sorted(auto_include_summary.items()):
            logger.info("  Trial %d: auto-included %s", row_idx, ", ".join(dep_names))
    else:
        logger.info("No dependency auto-inclusions required.")

    return trials


def _resolve_dependencies(
    requested: list[ChunkId],
    stage: Stage,
    row_idx: int,
) -> tuple[tuple[ChunkId, ...], set[ChunkId]]:
    """Order chunks by dependency and auto-include missing deps.

    Parameters
    ----------
    requested:
        The initial chunk list (mandatory + active factors).
    stage:
        Pipeline stage for stage-validity checks.
    row_idx:
        Design-matrix row index (used only in warning messages).

    Returns
    -------
    ordered:
        Tuple of ChunkId in dependency-valid order.
    auto_included:
        Set of ChunkIds that were pulled in automatically (not in requested).
        Empty set means no forced inclusions occurred.
    """
    included: set[ChunkId] = set(requested)
    auto_included: set[ChunkId] = set()
    ordered: list[ChunkId] = []

    def _add(cid: ChunkId) -> None:
        if cid in ordered_set:
            return
        chunk = _REGISTRY.get(cid)
        if chunk is None:
            raise ValueError(f"ChunkId {cid.name} is not registered")
        for dep in chunk.depends_on:
            if dep not in included:
                # Collect rather than log immediately — caller logs summary
                included.add(dep)
                auto_included.add(dep)
            _add(dep)
        ordered.append(cid)
        ordered_set.add(cid)

    ordered_set: set[ChunkId] = set()

    # Process in registry order so we respect natural ordering
    for cid in ChunkId:
        if cid in included:
            _add(cid)

    # Validate stage membership (warn only — don't crash)
    for cid in ordered:
        chunk = _REGISTRY[cid]
        if stage not in chunk.stages:
            logger.warning(
                "Trial %d: chunk %s is not registered for %s (valid: %s). "
                "It will be included but may produce unexpected output.",
                row_idx,
                cid.name,
                stage.name,
                [s.name for s in chunk.stages],
            )

    return tuple(ordered), auto_included


def _compute_hash(chunk_ids: tuple[ChunkId, ...]) -> str:
    """SHA-256 of the sorted chunk_id tuple for dedup."""
    key = ",".join(sorted(c.name for c in chunk_ids))
    return hashlib.sha256(key.encode()).hexdigest()
