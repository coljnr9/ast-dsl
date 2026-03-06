"""Tests for alspec/cache.py — pipeline cache save/load round-trips."""

import json
from pathlib import Path

import pytest

from alspec.cache import (
    DomainSnapshot,
    Stage1Snapshot,
    Stage2Snapshot,
    _hash_snapshot,
    load_cache,
    restore_signature,
    save_cache,
    snapshot_from_pipeline_result,
)
from alspec.obligation import build_obligation_table
from alspec.prompt_chunks import Stage


class TestSnapshotHashing:
    def test_hash_is_deterministic(self):
        snap = DomainSnapshot(
            domain="counter",
            stage1=Stage1Snapshot(analysis_text="test analysis"),
            stage2=Stage2Snapshot(
                signature_json={"type": "signature", "sorts": {}, "functions": {}, "predicates": {}, "generated_sorts": {}},
                signature_code="sig = Signature(...)",
                signature_analysis="rationale",
            ),
            content_hash="",
        )
        h1 = _hash_snapshot(snap)
        h2 = _hash_snapshot(snap)
        assert h1 == h2
        assert len(h1) == 64  # SHA-256 hex

    def test_different_content_different_hash(self):
        snap1 = DomainSnapshot(domain="counter", stage1=None, stage2=None, content_hash="")
        snap2 = DomainSnapshot(domain="stack", stage1=None, stage2=None, content_hash="")
        assert _hash_snapshot(snap1) != _hash_snapshot(snap2)


class TestSaveLoadRoundTrip:
    def test_round_trip_with_basis_spec(self, tmp_path: Path):
        """Save and load a cache built from a real basis spec."""
        from alspec.basis import stack_spec
        spec = stack_spec()
        sig = spec.signature

        snap = snapshot_from_pipeline_result(
            domain="stack",
            analysis_text="Stack is a LIFO data structure.",
            signature=sig,
            signature_code="sig = Signature(...)",
            signature_analysis="Standard stack with push/pop.",
        )

        cache_dir = tmp_path / "test-cache"
        manifest = save_cache(
            cache_dir,
            {"stack": snap},
            model="test-model",
            lens="entity_lifecycle",
            cache_through=Stage.SIGNATURE,
        )

        assert manifest.content_hash
        assert (cache_dir / "manifest.json").exists()
        assert (cache_dir / "stack.json").exists()

        # Load
        loaded_manifest, loaded_snaps = load_cache(cache_dir)
        assert loaded_manifest.content_hash == manifest.content_hash
        assert loaded_manifest.model == "test-model"
        assert loaded_manifest.cache_through == Stage.SIGNATURE
        assert "stack" in loaded_snaps

        loaded = loaded_snaps["stack"]
        assert loaded.content_hash == snap.content_hash
        assert loaded.stage1 is not None
        assert loaded.stage1.analysis_text == "Stack is a LIFO data structure."
        assert loaded.stage2 is not None
        assert loaded.stage2.signature_code == "sig = Signature(...)"

    def test_restored_signature_builds_obligation_table(self, tmp_path: Path):
        """The critical integration test: restored sig produces valid obligation table."""
        from alspec.basis import stack_spec
        spec = stack_spec()
        sig = spec.signature

        # Inject generated_sorts since stack_spec doesn't have it
        from alspec.signature import GeneratedSortInfo, Signature
        sig = Signature(
            sorts=sig.sorts,
            functions=sig.functions,
            predicates=sig.predicates,
            generated_sorts={
                "Stack": GeneratedSortInfo(constructors=("new", "push"))
            }
        )

        snap = snapshot_from_pipeline_result(
            domain="stack",
            analysis_text=None,
            signature=sig,
            signature_code="sig = ...",
            signature_analysis="rationale",
        )

        cache_dir = tmp_path / "test-cache"
        save_cache(cache_dir, {"stack": snap}, model="m", lens=None, cache_through=Stage.SIGNATURE)
        _, loaded = load_cache(cache_dir)

        restored_sig = restore_signature(loaded["stack"])
        table = build_obligation_table(restored_sig)
        assert len(table.cells) > 0

    def test_save_refuses_existing_directory(self, tmp_path: Path):
        cache_dir = tmp_path / "existing"
        cache_dir.mkdir()
        with pytest.raises(FileExistsError):
            save_cache(cache_dir, {}, model="m", lens=None, cache_through=Stage.SIGNATURE)

    def test_load_fails_on_missing_directory(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            load_cache(tmp_path / "nonexistent")

    def test_load_fails_on_corrupt_hash(self, tmp_path: Path):
        """Detect tampered cache files."""
        from alspec.basis import stack_spec
        spec = stack_spec()

        snap = snapshot_from_pipeline_result(
            domain="stack", analysis_text=None,
            signature=spec.signature,
            signature_code="sig = ...",
            signature_analysis="rationale",
        )

        cache_dir = tmp_path / "corrupt-cache"
        save_cache(cache_dir, {"stack": snap}, model="m", lens=None, cache_through=Stage.SIGNATURE)

        # Tamper with the domain file
        snap_path = cache_dir / "stack.json"
        data = json.loads(snap_path.read_text())
        data["stage2"]["signature_code"] = "TAMPERED"
        snap_path.write_text(json.dumps(data))

        with pytest.raises(ValueError, match="Content hash mismatch"):
            load_cache(cache_dir)

    def test_load_fails_on_missing_domain_file(self, tmp_path: Path):
        """Manifest references a domain whose file doesn't exist."""
        cache_dir = tmp_path / "incomplete"
        cache_dir.mkdir()
        manifest = {
            "created_at": "2026-01-01T00:00:00Z",
            "model": "m",
            "lens": None,
            "domains": ["ghost"],
            "cache_through": "SIGNATURE",
            "content_hash": "abc",
        }
        (cache_dir / "manifest.json").write_text(json.dumps(manifest))
        with pytest.raises(FileNotFoundError, match="ghost"):
            load_cache(cache_dir)
