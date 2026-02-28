"""TOML-based configuration for Design of Experiments runs.

Parses a TOML file into a frozen ``DoeConfig`` dataclass, validating:
- ChunkId names resolve to real enum members
- Mandatory chunks don't overlap with factor chunks
- Stage is supported ("stage1" only for now)
- Domains resolve correctly

Usage::

    config = load_doe_config(Path("experiments/example.toml"))
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

from alspec.prompt_chunks import ChunkId


# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DoeConfig:
    """Fully parsed and validated experiment configuration."""

    # [experiment]
    name: str
    description: str
    output_dir: Path  # absolute path

    # [design]
    resolution: str  # "full" | "resolution_iii" | "resolution_iv" | "resolution_v"
    replicates: int

    # [pipeline]
    stage: str  # "stage1"
    model: str
    temperature: float
    max_concurrent: int

    # [domains]
    domains: tuple[str, ...]  # resolved domain IDs

    # [chunks]
    mandatory_chunks: tuple[ChunkId, ...]
    # Ordered list of factors; each factor is a tuple of ChunkIds
    factors: tuple[tuple[str, tuple[ChunkId, ...]], ...]  # (label, chunk_ids)


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------

_SUPPORTED_STAGES = frozenset({"stage1"})
_SUPPORTED_RESOLUTIONS = frozenset(
    {"full", "resolution_iii", "resolution_iv", "resolution_v"}
)


def load_doe_config(path: Path, *, project_root: Path | None = None) -> DoeConfig:
    """Parse and validate a TOML experiment config file.

    Parameters
    ----------
    path:
        Absolute or relative path to the ``.toml`` config file.
    project_root:
        Used to resolve ``output_dir`` (relative paths) and to locate
        the ``golden/`` directory for domain discovery. Defaults to the
        directory containing the TOML file's parent's parent (i.e. the
        project root when toml lives under ``experiments/``).

    Raises
    ------
    ValueError:
        On any validation error (bad ChunkId, overlap, unsupported stage, etc.)
    FileNotFoundError:
        If the TOML file does not exist.
    """
    path = Path(path).resolve()
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    if project_root is None:
        # experiments/example.toml → experiments/ → project root
        project_root = path.parent.parent

    with path.open("rb") as f:
        raw = tomllib.load(f)

    # ---- [experiment] ----
    experiment = _require_section(raw, "experiment")
    name = _require_str(experiment, "name", "[experiment]")
    description = _require_str(experiment, "description", "[experiment]")
    output_dir_str = _require_str(experiment, "output_dir", "[experiment]")
    output_dir = (project_root / output_dir_str).resolve()

    # ---- [design] ----
    design = _require_section(raw, "design")
    resolution = _require_str(design, "resolution", "[design]")
    if resolution not in _SUPPORTED_RESOLUTIONS:
        raise ValueError(
            f"[design].resolution must be one of {sorted(_SUPPORTED_RESOLUTIONS)}, "
            f"got {resolution!r}"
        )
    replicates = _require_positive_int(design, "replicates", "[design]")

    # ---- [pipeline] ----
    pipeline = _require_section(raw, "pipeline")
    stage = _require_str(pipeline, "stage", "[pipeline]")
    if stage not in _SUPPORTED_STAGES:
        raise ValueError(
            f"[pipeline].stage must be one of {sorted(_SUPPORTED_STAGES)}, "
            f"got {stage!r}"
        )
    model = _require_str(pipeline, "model", "[pipeline]")
    temperature = float(pipeline.get("temperature", 0.7))
    max_concurrent = _require_positive_int(pipeline, "max_concurrent", "[pipeline]")

    # ---- [domains] ----
    domains_section = _require_section(raw, "domains")
    include = domains_section.get("include", "all")
    domains = _resolve_domains(include, project_root)

    # ---- [chunks] ----
    chunks_section = _require_section(raw, "chunks")
    mandatory_raw = chunks_section.get("mandatory", [])
    if not isinstance(mandatory_raw, list):
        raise ValueError("[chunks].mandatory must be a list of ChunkId names")

    mandatory_chunks = tuple(_parse_chunk_ids(mandatory_raw, "[chunks].mandatory"))

    factors_raw = chunks_section.get("factors", {})
    if not isinstance(factors_raw, dict):
        raise ValueError("[chunks.factors] must be a table of label → [ChunkId, ...]")

    factors: list[tuple[str, tuple[ChunkId, ...]]] = []
    mandatory_set = set(mandatory_chunks)
    for label, chunk_names in factors_raw.items():
        if not isinstance(chunk_names, list):
            raise ValueError(
                f"Factor {label!r} in [chunks.factors] must be a list of ChunkId names"
            )
        chunk_ids = tuple(_parse_chunk_ids(chunk_names, f"[chunks.factors].{label}"))
        # Check overlap with mandatory
        overlap = mandatory_set & set(chunk_ids)
        if overlap:
            raise ValueError(
                f"Factor {label!r} contains chunks that are also mandatory: "
                f"{[c.name for c in overlap]}"
            )
        factors.append((label, chunk_ids))

    # Check no chunk appears in two factors
    all_factor_chunks: set[ChunkId] = set()
    for label, chunk_ids in factors:
        dupes = all_factor_chunks & set(chunk_ids)
        if dupes:
            raise ValueError(
                f"Factor {label!r} contains chunks already used in another factor: "
                f"{[c.name for c in dupes]}"
            )
        all_factor_chunks.update(chunk_ids)

    return DoeConfig(
        name=name,
        description=description,
        output_dir=output_dir,
        resolution=resolution,
        replicates=replicates,
        stage=stage,
        model=model,
        temperature=temperature,
        max_concurrent=max_concurrent,
        domains=domains,
        mandatory_chunks=mandatory_chunks,
        factors=tuple(factors),
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _require_section(raw: dict, key: str) -> dict:
    val = raw.get(key)
    if not isinstance(val, dict):
        raise ValueError(f"Missing or invalid section [{key}] in config")
    return val


def _require_str(section: dict, key: str, section_name: str) -> str:
    val = section.get(key)
    if not isinstance(val, str) or not val.strip():
        raise ValueError(f"{section_name}.{key} must be a non-empty string")
    return val


def _require_positive_int(section: dict, key: str, section_name: str) -> int:
    val = section.get(key)
    if not isinstance(val, int) or val < 1:
        raise ValueError(f"{section_name}.{key} must be a positive integer")
    return val


def _parse_chunk_ids(names: list, location: str) -> list[ChunkId]:
    """Convert a list of string names to ChunkId enum members."""
    result: list[ChunkId] = []
    for name in names:
        if not isinstance(name, str):
            raise ValueError(f"{location}: expected string ChunkId name, got {name!r}")
        try:
            cid = ChunkId[name]
        except KeyError:
            valid = [c.name for c in ChunkId]
            raise ValueError(
                f"{location}: {name!r} is not a valid ChunkId. "
                f"Valid names: {valid}"
            ) from None
        result.append(cid)
    return result


def _resolve_domains(include: object, project_root: Path) -> tuple[str, ...]:
    """Resolve the domains list from the config value.

    Accepts ``"all"`` (scan golden/) or a list of specific domain IDs.
    """
    golden_dir = project_root / "golden"

    match include:
        case "all":
            if not golden_dir.exists():
                raise FileNotFoundError(
                    f"golden/ directory not found at {golden_dir}. "
                    "Cannot resolve domains = 'all'."
                )
            ids = sorted(
                p.stem
                for p in golden_dir.glob("*.py")
                if p.name != "__init__.py"
            )
            if not ids:
                raise ValueError(
                    f"No .py files found in {golden_dir}. "
                    "Cannot resolve domains = 'all'."
                )
            return tuple(ids)

        case list() as domain_list:
            for item in domain_list:
                if not isinstance(item, str):
                    raise ValueError(
                        f"[domains].include list must contain strings, got {item!r}"
                    )
            return tuple(domain_list)

        case _:
            raise ValueError(
                f"[domains].include must be \"all\" or a list of domain IDs, "
                f"got {include!r}"
            )
