"""Pipeline cache system for alspec.

Saves and loads LLM outputs from specific pipeline stages to allow pinned
upstream runs for experiments.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .prompt_chunks import Stage
from .serialization import signature_from_json, signature_to_json
from .signature import Signature

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Stage1Snapshot:
    """Frozen LLM output from Stage 1 (ANALYSIS)."""
    analysis_text: str


@dataclass(frozen=True)
class Stage2Snapshot:
    """Frozen LLM output from Stage 2 (SIGNATURE)."""
    signature_json: dict[str, Any]   # output of signature_to_json()
    signature_code: str              # raw Python code string the LLM produced
    signature_analysis: str          # LLM's design rationale / chain-of-thought


@dataclass(frozen=True)
class DomainSnapshot:
    """Complete frozen LLM outputs for one domain, up through some stage."""
    domain: str
    stage1: Stage1Snapshot | None    # None if analysis was skipped (no lens)
    stage2: Stage2Snapshot | None    # None if cache_through == ANALYSIS
    content_hash: str                # SHA-256 of this snapshot's serialized content


@dataclass(frozen=True)
class CacheManifest:
    """Metadata for a saved cache directory."""
    created_at: str                  # ISO 8601
    model: str                       # OpenRouter model identifier
    lens: str | None                 # lens name used for Stage 1, or None
    domains: tuple[str, ...]         # domains in this cache (sorted)
    cache_through: Stage             # ANALYSIS or SIGNATURE
    content_hash: str                # SHA-256 of all domain hashes (sorted, concatenated)


def _hash_snapshot(snap: DomainSnapshot) -> str:
    """Compute SHA-256 of a DomainSnapshot's LLM-produced content.

    Excludes the content_hash field itself (circular).
    Deterministic: sorted keys in JSON serialization.
    """
    content: dict[str, Any] = {"domain": snap.domain}
    if snap.stage1 is not None:
        content["stage1"] = {"analysis_text": snap.stage1.analysis_text}
    if snap.stage2 is not None:
        content["stage2"] = {
            "signature_json": snap.stage2.signature_json,
            "signature_code": snap.stage2.signature_code,
            "signature_analysis": snap.stage2.signature_analysis,
        }
    raw = json.dumps(content, sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(raw.encode()).hexdigest()


def _hash_manifest(domain_hashes: list[str]) -> str:
    """Compute SHA-256 of all domain hashes (sorted for determinism)."""
    combined = "|".join(sorted(domain_hashes))
    return hashlib.sha256(combined.encode()).hexdigest()


def save_cache(
    cache_dir: Path,
    snapshots: dict[str, DomainSnapshot],
    *,
    model: str,
    lens: str | None,
    cache_through: Stage,
) -> CacheManifest:
    """Save domain snapshots to disk.

    Directory layout:
        cache_dir/
        ├── manifest.json
        ├── counter.json
        ├── stack.json
        └── ...

    Raises FileExistsError if cache_dir already exists (no silent overwrite).
    """
    if cache_dir.exists():
        raise FileExistsError(
            f"Cache directory already exists: {cache_dir}. "
            f"Remove it first or choose a different path."
        )
    cache_dir.mkdir(parents=True)

    domain_hashes: list[str] = []

    for domain, snap in sorted(snapshots.items()):
        # Verify hash integrity
        computed = _hash_snapshot(snap)
        if snap.content_hash != computed:
            raise ValueError(
                f"Content hash mismatch for domain {domain!r}: "
                f"stored={snap.content_hash[:12]}, computed={computed[:12]}"
            )
        domain_hashes.append(snap.content_hash)

        # Serialize snapshot
        snap_data: dict[str, Any] = {"domain": snap.domain, "content_hash": snap.content_hash}
        if snap.stage1 is not None:
            snap_data["stage1"] = {"analysis_text": snap.stage1.analysis_text}
        if snap.stage2 is not None:
            snap_data["stage2"] = {
                "signature_json": snap.stage2.signature_json,
                "signature_code": snap.stage2.signature_code,
                "signature_analysis": snap.stage2.signature_analysis,
            }

        snap_path = cache_dir / f"{domain}.json"
        snap_path.write_text(json.dumps(snap_data, indent=2, sort_keys=True))

    manifest = CacheManifest(
        created_at=datetime.now(UTC).isoformat(),
        model=model,
        lens=lens,
        domains=tuple(sorted(snapshots.keys())),
        cache_through=cache_through,
        content_hash=_hash_manifest(domain_hashes),
    )

    manifest_data = {
        "created_at": manifest.created_at,
        "model": manifest.model,
        "lens": manifest.lens,
        "domains": list(manifest.domains),
        "cache_through": manifest.cache_through.name,   # Store as "ANALYSIS" or "SIGNATURE"
        "content_hash": manifest.content_hash,
    }
    (cache_dir / "manifest.json").write_text(json.dumps(manifest_data, indent=2))

    logger.info(
        "Cache saved: %s (%d domains, through %s, hash=%s)",
        cache_dir, len(snapshots), cache_through.name, manifest.content_hash[:12],
    )

    return manifest


def load_cache(cache_dir: Path) -> tuple[CacheManifest, dict[str, DomainSnapshot]]:
    """Load a cache directory. Returns (manifest, {domain: snapshot}).

    Raises FileNotFoundError if cache_dir or manifest.json doesn't exist.
    Raises ValueError on any integrity or schema problem.
    """
    if not cache_dir.is_dir():
        raise FileNotFoundError(f"Cache directory not found: {cache_dir}")

    manifest_path = cache_dir / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"No manifest.json in cache directory: {cache_dir}")

    manifest_data = json.loads(manifest_path.read_text())

    try:
        cache_through = Stage[manifest_data["cache_through"]]
    except KeyError:
        raise ValueError(
            f"Invalid cache_through value: {manifest_data.get('cache_through')!r}. "
            f"Expected one of: {[s.name for s in Stage]}"
        ) from None

    manifest = CacheManifest(
        created_at=manifest_data["created_at"],
        model=manifest_data["model"],
        lens=manifest_data.get("lens"),
        domains=tuple(manifest_data["domains"]),
        cache_through=cache_through,
        content_hash=manifest_data["content_hash"],
    )

    snapshots: dict[str, DomainSnapshot] = {}
    domain_hashes: list[str] = []

    for domain in manifest.domains:
        snap_path = cache_dir / f"{domain}.json"
        if not snap_path.exists():
            raise FileNotFoundError(
                f"Manifest lists domain {domain!r} but {snap_path} does not exist"
            )

        snap_data = json.loads(snap_path.read_text())

        stage1: Stage1Snapshot | None = None
        if "stage1" in snap_data:
            stage1 = Stage1Snapshot(analysis_text=snap_data["stage1"]["analysis_text"])

        stage2: Stage2Snapshot | None = None
        if "stage2" in snap_data:
            s2 = snap_data["stage2"]
            stage2 = Stage2Snapshot(
                signature_json=s2["signature_json"],
                signature_code=s2["signature_code"],
                signature_analysis=s2["signature_analysis"],
            )

        stored_hash = snap_data["content_hash"]
        snap = DomainSnapshot(
            domain=domain,
            stage1=stage1,
            stage2=stage2,
            content_hash=stored_hash,
        )

        # Verify hash integrity
        computed = _hash_snapshot(snap)
        if computed != stored_hash:
            raise ValueError(
                f"Content hash mismatch for domain {domain!r}: "
                f"stored={stored_hash[:12]}, computed={computed[:12]}. "
                f"Cache may be corrupt."
            )

        snapshots[domain] = snap
        domain_hashes.append(stored_hash)

    # Verify manifest-level hash
    computed_manifest_hash = _hash_manifest(domain_hashes)
    if computed_manifest_hash != manifest.content_hash:
        raise ValueError(
            f"Manifest content hash mismatch: "
            f"stored={manifest.content_hash[:12]}, computed={computed_manifest_hash[:12]}. "
            f"Cache may be corrupt or tampered with."
        )

    logger.info(
        "Cache loaded: %s (%d domains, through %s, hash=%s)",
        cache_dir, len(snapshots), cache_through.name, manifest.content_hash[:12],
    )

    return manifest, snapshots


def snapshot_from_pipeline_result(
    domain: str,
    analysis_text: str | None,
    signature: Signature,
    signature_code: str,
    signature_analysis: str,
) -> DomainSnapshot:
    """Create a DomainSnapshot from pipeline outputs.

    Computes the content hash automatically.
    Raises ValueError if signature or signature_code is empty/None.
    """
    if not signature_code:
        raise ValueError(f"Cannot create snapshot for {domain!r}: empty signature_code")
    if not signature_analysis:
        raise ValueError(f"Cannot create snapshot for {domain!r}: empty signature_analysis")

    stage1 = Stage1Snapshot(analysis_text=analysis_text) if analysis_text else None
    stage2 = Stage2Snapshot(
        signature_json=signature_to_json(signature),
        signature_code=signature_code,
        signature_analysis=signature_analysis,
    )

    # Create with temporary hash, then compute real hash
    temp = DomainSnapshot(
        domain=domain,
        stage1=stage1,
        stage2=stage2,
        content_hash="",  # placeholder
    )
    real_hash = _hash_snapshot(temp)
    return DomainSnapshot(
        domain=domain,
        stage1=stage1,
        stage2=stage2,
        content_hash=real_hash,
    )


def restore_signature(snapshot: DomainSnapshot) -> Signature:
    """Recover a Signature object from a DomainSnapshot.

    Raises ValueError if snapshot has no Stage 2 data.
    """
    if snapshot.stage2 is None:
        raise ValueError(
            f"Cannot restore signature for {snapshot.domain!r}: "
            f"snapshot has no Stage 2 data"
        )
    return signature_from_json(snapshot.stage2.signature_json)

from alspec.stages import AnalysisOutput, SignatureOutput

def analysis_output_from_snapshot(snapshot: DomainSnapshot) -> AnalysisOutput | None:
    if snapshot.stage1 is None:
        return None
    return AnalysisOutput(
        analysis_text=snapshot.stage1.analysis_text,
        usage=None,
    )

def signature_output_from_snapshot(snapshot: DomainSnapshot) -> SignatureOutput | None:
    if snapshot.stage2 is None:
        return None
    return SignatureOutput(
        signature=restore_signature(snapshot),
        code=snapshot.stage2.signature_code,
        analysis=snapshot.stage2.signature_analysis,
        usage=None,
    )
