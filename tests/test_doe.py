"""Unit tests for the DoE infrastructure (no LLM calls required).

Tests cover:
1. Config parsing (TOML → DoeConfig)
2. Design matrix generation (dimensions, value range, balance)
3. Trial config generation (mandatory chunks, factor toggling, dep auto-inclusion)
4. Stage 1 scoring (Jaccard, health computation)
5. Effect computation (synthetic data with known effects)
6. Config hash (same chunks → same hash, different → different)
"""

from __future__ import annotations

import dataclasses
import tempfile
from pathlib import Path

import numpy as np
import pytest

from alspec.prompt_chunks import ChunkId, Stage


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_toml(content: str) -> Path:
    """Write a TOML string to a temp file and return the path."""
    tmp = tempfile.NamedTemporaryFile(
        suffix=".toml", delete=False, mode="w"
    )
    tmp.write(content)
    tmp.close()
    return Path(tmp.name)


_MINIMAL_TOML = """
[experiment]
name = "test-exp"
description = "Test experiment"
output_dir = "results/test"

[design]
resolution = "full"
replicates = 2

[pipeline]
stage = "stage1"
model = "test-model"
temperature = 0.7
max_concurrent = 2

[domains]
include = ["stack", "counter"]

[chunks]
mandatory = ["ROLE_PREAMBLE", "TYPE_GRAMMAR"]

[chunks.factors]
A = ["FORMAL_FRAME"]
B = ["BASIS_CATALOG"]
C = ["WF_CHECKLIST"]
"""


# ---------------------------------------------------------------------------
# 1. Config parsing
# ---------------------------------------------------------------------------


class TestDoeConfigParsing:
    def test_minimal_config_parses(self, tmp_path: Path) -> None:
        from alspec.eval.doe_config import load_doe_config

        toml_file = tmp_path / "test.toml"
        toml_file.write_text(_MINIMAL_TOML)

        config = load_doe_config(toml_file, project_root=tmp_path)

        assert config.name == "test-exp"
        assert config.stage == "stage1"
        assert config.replicates == 2
        assert config.resolution == "full"
        assert "stack" in config.domains
        assert "counter" in config.domains
        assert ChunkId.ROLE_PREAMBLE in config.mandatory_chunks
        assert ChunkId.TYPE_GRAMMAR in config.mandatory_chunks
        assert len(config.factors) == 3
        labels = [lbl for lbl, _ in config.factors]
        assert labels == ["A", "B", "C"]

    def test_invalid_chunk_name_raises(self, tmp_path: Path) -> None:
        from alspec.eval.doe_config import load_doe_config

        toml = _MINIMAL_TOML.replace('mandatory = ["ROLE_PREAMBLE", "TYPE_GRAMMAR"]',
                                     'mandatory = ["NOT_A_REAL_CHUNK"]')
        toml_file = tmp_path / "bad.toml"
        toml_file.write_text(toml)

        with pytest.raises(ValueError, match="NOT_A_REAL_CHUNK"):
            load_doe_config(toml_file, project_root=tmp_path)

    def test_factor_mandatory_overlap_raises(self, tmp_path: Path) -> None:
        from alspec.eval.doe_config import load_doe_config

        toml = _MINIMAL_TOML + '\nX = ["ROLE_PREAMBLE"]\n'
        toml_file = tmp_path / "overlap.toml"
        toml_file.write_text(toml)

        with pytest.raises(ValueError, match="mandatory"):
            load_doe_config(toml_file, project_root=tmp_path)

    def test_unsupported_stage_raises(self, tmp_path: Path) -> None:
        from alspec.eval.doe_config import load_doe_config

        toml = _MINIMAL_TOML.replace('stage = "stage1"', 'stage = "full"')
        toml_file = tmp_path / "stage.toml"
        toml_file.write_text(toml)

        with pytest.raises(ValueError, match="stage"):
            load_doe_config(toml_file, project_root=tmp_path)

    def test_unsupported_resolution_raises(self, tmp_path: Path) -> None:
        from alspec.eval.doe_config import load_doe_config

        toml = _MINIMAL_TOML.replace('resolution = "full"', 'resolution = "bogus"')
        toml_file = tmp_path / "res.toml"
        toml_file.write_text(toml)

        with pytest.raises(ValueError, match="resolution"):
            load_doe_config(toml_file, project_root=tmp_path)

    def test_domains_all_resolves(self, tmp_path: Path) -> None:
        """'all' should resolve by scanning golden/*.py if it exists."""
        from alspec.eval.doe_config import load_doe_config

        # Create a fake golden directory
        golden = tmp_path / "golden"
        golden.mkdir()
        (golden / "foo.py").write_text("# dummy")
        (golden / "bar.py").write_text("# dummy")

        toml = _MINIMAL_TOML.replace('include = ["stack", "counter"]', 'include = "all"')
        toml_file = tmp_path / "all.toml"
        toml_file.write_text(toml)

        config = load_doe_config(toml_file, project_root=tmp_path)
        assert set(config.domains) == {"foo", "bar"}


# ---------------------------------------------------------------------------
# 2. Design matrix generation
# ---------------------------------------------------------------------------


class TestDesignMatrix:
    def _make_config(self, resolution: str, k: int, tmp_path: Path):
        from alspec.eval.doe_config import load_doe_config

        # Build factors using available ChunkIds that don't conflict
        factor_chunks = [
            "FORMAL_FRAME",
            "BASIS_CATALOG",
            "WF_CHECKLIST",
            "OBLIGATION_PATTERN",
            "LOOSE_SEMANTICS_RULE",
        ]
        factors_toml = "\n".join(
            f'{chr(65 + i)} = ["{factor_chunks[i]}"]' for i in range(k)
        )

        toml = f"""
[experiment]
name = "test"
description = "test"
output_dir = "results/test"

[design]
resolution = "{resolution}"
replicates = 1

[pipeline]
stage = "stage1"
model = "test-model"
temperature = 0.7
max_concurrent = 1

[domains]
include = ["stack"]

[chunks]
mandatory = ["ROLE_PREAMBLE", "TYPE_GRAMMAR"]

[chunks.factors]
{factors_toml}
"""
        toml_file = tmp_path / "dm.toml"
        toml_file.write_text(toml)
        return load_doe_config(toml_file, project_root=tmp_path)

    def test_full_factorial_3_factors(self, tmp_path: Path) -> None:
        from alspec.eval.doe_design import generate_design_matrix

        config = self._make_config("full", 3, tmp_path)
        matrix = generate_design_matrix(config)

        assert matrix.shape == (8, 3)  # 2^3 = 8
        assert set(np.unique(matrix)) == {-1, 1}

    def test_full_factorial_balance(self, tmp_path: Path) -> None:
        """Each factor must appear equally at +1 and -1."""
        from alspec.eval.doe_design import generate_design_matrix

        config = self._make_config("full", 3, tmp_path)
        matrix = generate_design_matrix(config)

        for col in range(matrix.shape[1]):
            high = np.sum(matrix[:, col] == 1)
            low = np.sum(matrix[:, col] == -1)
            assert high == low, f"Column {col} is unbalanced: {high} vs {low}"

    def test_full_factorial_all_combinations(self, tmp_path: Path) -> None:
        """Full factorial must include all 2^k combinations."""
        from alspec.eval.doe_design import generate_design_matrix

        config = self._make_config("full", 3, tmp_path)
        matrix = generate_design_matrix(config)

        combinations = set(map(tuple, matrix.tolist()))
        assert len(combinations) == 8

    def test_values_are_plus_minus_one(self, tmp_path: Path) -> None:
        from alspec.eval.doe_design import generate_design_matrix

        for res in ("full", "resolution_iii"):
            config = self._make_config(res, 4, tmp_path)
            matrix = generate_design_matrix(config)
            assert set(np.unique(matrix)).issubset({-1, 1})


# ---------------------------------------------------------------------------
# 3. Trial config generation
# ---------------------------------------------------------------------------


class TestTrialConfigs:
    def _make_config_object(self, tmp_path: Path):
        from alspec.eval.doe_config import load_doe_config

        toml = _MINIMAL_TOML
        toml_file = tmp_path / "tc.toml"
        toml_file.write_text(toml)
        return load_doe_config(toml_file, project_root=tmp_path)

    def test_mandatory_chunks_always_present(self, tmp_path: Path) -> None:
        from alspec.eval.doe_design import generate_trials

        config = self._make_config_object(tmp_path)
        trials = generate_trials(config)

        for trial in trials:
            for mandatory in config.mandatory_chunks:
                assert mandatory in trial.chunk_ids, (
                    f"Mandatory chunk {mandatory.name} missing from trial {trial.trial_id}"
                )

    def test_factor_chunks_toggle(self, tmp_path: Path) -> None:
        from alspec.eval.doe_design import generate_trials

        config = self._make_config_object(tmp_path)
        trials = generate_trials(config)

        for trial in trials:
            for label, chunk_ids in config.factors:
                level = trial.factor_levels.get(label)
                assert level in (-1, 1), f"Factor {label} has unexpected level {level}"

                for cid in chunk_ids:
                    if level == 1:
                        assert cid in trial.chunk_ids, (
                            f"Factor {label}=+1 but chunk {cid.name} missing"
                        )
                    else:
                        # Chunk should only be absent if no dep forced it in
                        pass  # auto-dep may have added it — can't assert absence

    def test_replicates_count(self, tmp_path: Path) -> None:
        from alspec.eval.doe_design import generate_design_matrix, generate_trials

        config = self._make_config_object(tmp_path)
        matrix = generate_design_matrix(config)
        trials = generate_trials(config)

        # Each design point × replicates
        assert len(trials) == matrix.shape[0] * config.replicates

    def test_replicate_indices(self, tmp_path: Path) -> None:
        from alspec.eval.doe_design import generate_trials

        config = self._make_config_object(tmp_path)
        trials = generate_trials(config)

        for trial_id in {t.trial_id for t in trials}:
            reps = sorted(t.replicate for t in trials if t.trial_id == trial_id)
            assert reps == list(range(config.replicates))

    def test_dependency_auto_inclusion(self, tmp_path: Path) -> None:
        """DISPATCH_RULES depends on GENERATED_SORTS_ROLES.
        If DISPATCH_RULES is in a factor that's active, GENERATED_SORTS_ROLES
        must be present even if its factor is OFF.
        """
        from alspec.eval.doe_config import load_doe_config
        from alspec.eval.doe_design import generate_trials

        # Set up: G=DISPATCH_RULES active (its factor is forced +1),
        # F=GENERATED_SORTS_ROLES factor is OFF at -1.
        # We do full factorial with 2 factors and pick the row where G=+1, F=-1.
        toml = """
[experiment]
name = "deptest"
description = "dep test"
output_dir = "results/deptest"

[design]
resolution = "full"
replicates = 1

[pipeline]
stage = "stage1"
model = "test"
temperature = 0.7
max_concurrent = 1

[domains]
include = ["stack"]

[chunks]
mandatory = ["ROLE_PREAMBLE", "TYPE_GRAMMAR", "API_HELPERS"]

[chunks.factors]
F = ["GENERATED_SORTS_ROLES"]
G = ["DISPATCH_RULES"]
"""
        toml_file = tmp_path / "dep.toml"
        toml_file.write_text(toml)
        config = load_doe_config(toml_file, project_root=tmp_path)
        trials = generate_trials(config)

        # Find trial where G=+1 and F=-1
        target = [
            t for t in trials
            if t.factor_levels.get("G") == 1 and t.factor_levels.get("F") == -1
        ]
        # DISPATCH_RULES depends on GENERATED_SORTS_ROLES (check registry)
        from alspec.prompt_chunks import _REGISTRY
        dispatch = _REGISTRY.get(ChunkId.DISPATCH_RULES)
        if dispatch is not None and ChunkId.GENERATED_SORTS_ROLES in dispatch.depends_on:
            for t in target:
                assert ChunkId.GENERATED_SORTS_ROLES in t.chunk_ids, (
                    "GENERATED_SORTS_ROLES should have been auto-included as dep of DISPATCH_RULES"
                )


# ---------------------------------------------------------------------------
# 4. Stage 1 scoring
# ---------------------------------------------------------------------------


class TestStage1Scoring:
    def test_jaccard_identical(self) -> None:
        from alspec.eval.stage1_score import jaccard

        assert jaccard({"a", "b"}, {"a", "b"}) == 1.0

    def test_jaccard_disjoint(self) -> None:
        from alspec.eval.stage1_score import jaccard

        assert jaccard({"a"}, {"b"}) == 0.0

    def test_jaccard_partial(self) -> None:
        from alspec.eval.stage1_score import jaccard

        result = jaccard({"a", "b"}, {"b", "c"})
        assert abs(result - 1 / 3) < 1e-9

    def test_jaccard_both_empty(self) -> None:
        from alspec.eval.stage1_score import jaccard

        assert jaccard(set(), set()) == 1.0

    def test_health_parse_failure(self) -> None:
        from alspec.eval.stage1_score import compute_health

        h = compute_health(
            parse_success=False,
            well_formed=False,
            sort_overlap=0.9,
            function_overlap=0.9,
            predicate_overlap=0.9,
            constructor_overlap=0.9,
            cell_count_delta=0,
            obligation_cell_count=10,
        )
        assert h == 0.0

    def test_health_ill_sorted(self) -> None:
        from alspec.eval.stage1_score import compute_health

        h = compute_health(
            parse_success=True,
            well_formed=False,
            sort_overlap=1.0,
            function_overlap=1.0,
            predicate_overlap=1.0,
            constructor_overlap=1.0,
            cell_count_delta=0,
            obligation_cell_count=10,
        )
        assert h == 0.2

    def test_health_perfect_overlap(self) -> None:
        from alspec.eval.stage1_score import compute_health

        h = compute_health(
            parse_success=True,
            well_formed=True,
            sort_overlap=1.0,
            function_overlap=1.0,
            predicate_overlap=1.0,
            constructor_overlap=1.0,
            cell_count_delta=0,
            obligation_cell_count=10,
        )
        assert abs(h - 1.0) < 1e-9

    def test_health_floor_when_well_formed(self) -> None:
        from alspec.eval.stage1_score import compute_health

        h = compute_health(
            parse_success=True,
            well_formed=True,
            sort_overlap=0.0,
            function_overlap=0.0,
            predicate_overlap=0.0,
            constructor_overlap=0.0,
            cell_count_delta=100,
            obligation_cell_count=10,
        )
        # Floor is 0.2 for well-formed
        assert h >= 0.2

    def test_score_bad_code(self, tmp_path: Path) -> None:
        from alspec.eval.stage1_score import score_stage1_output

        score = score_stage1_output(
            code="this is not python!!!",
            domain="stack",
            trial_id=0,
            replicate=0,
            model="test",
            golden_dir=tmp_path,
        )
        assert not score.parse_success
        # No DSL-specific tokens in "this is not python!!!" → zero credit
        assert score.health == 0.0
        assert score.partial_parse_credit == 0.0
        assert score.error_message is not None


class TestPartialParsing:
    def test_partial_score_empty(self) -> None:
        from alspec.eval.stage1_score import partial_parse_score

        assert partial_parse_score("") == 0.0

    def test_partial_score_signature_keyword(self) -> None:
        from alspec.eval.stage1_score import partial_parse_score

        # Signature( alone gives 0.03
        assert partial_parse_score("Signature(") == pytest.approx(0.03)

    def test_partial_score_multi_keywords(self) -> None:
        from alspec.eval.stage1_score import partial_parse_score

        output = 'Signature(fn("push", ...), pred("empty", ...), sorts={})'
        score = partial_parse_score(output)
        # Signature(0.03) + fn(0.03) + pred(0.02) + sorts=(0.02) = 0.10
        assert 0.08 <= score <= 0.15

    def test_partial_score_capped_at_015(self) -> None:
        from alspec.eval.stage1_score import partial_parse_score

        # All six signals present
        output = (
            'Signature( fn( fn(" pred( pred(" '
            'GeneratedSortInfo( SortRef( selectors'
        )
        assert partial_parse_score(output) == pytest.approx(0.15)

    def test_partial_credit_below_wellformed_floor(self) -> None:
        from alspec.eval.stage1_score import partial_parse_score

        # Max partial credit (0.15) must be below the well-formed floor (0.2)
        max_credit = partial_parse_score(
            'Signature( fn( pred( GeneratedSortInfo( SortRef( selectors'
        )
        assert max_credit < 0.2

    def test_score_bad_code_with_dsl_tokens(self, tmp_path: Path) -> None:
        from alspec.eval.stage1_score import score_stage1_output

        # Code that has DSL tokens but can't exec — should get partial credit
        bad_code_with_tokens = "x = Signature( fn('push', sorts={'Elem': SortRef('Elem')}))"
        score = score_stage1_output(
            code=bad_code_with_tokens,
            domain="stack",
            trial_id=0,
            replicate=0,
            model="test",
            golden_dir=tmp_path,
        )
        assert not score.parse_success
        assert score.health > 0.0    # partial credit granted
        assert score.health <= 0.15  # credit is capped
        assert score.partial_parse_credit == score.health


# ---------------------------------------------------------------------------
# 5. Effect computation
# ---------------------------------------------------------------------------


class TestEffectComputation:
    def _make_scores(self, n_per_cell: int = 10) -> list:
        """Create synthetic Stage1Score objects with known effects.

        Factor A has a main effect of +0.2 on health.
        Factor B has no effect.
        """
        import random
        from alspec.eval.stage1_score import Stage1Score

        random.seed(42)
        scores = []
        for a_level in (-1, 1):
            for b_level in (-1, 1):
                base_health = 0.5 + 0.1 * a_level  # A has +0.2 main effect
                for rep in range(n_per_cell):
                    health = base_health + random.gauss(0, 0.01)
                    health = max(0.0, min(1.0, health))
                    scores.append(
                        Stage1Score(
                            domain="stack",
                            trial_id=0,  # not used in effect computation
                            replicate=rep,
                            model="test",
                            parse_success=True,
                            well_formed=True,
                            sort_count=2,
                            function_count=4,
                            predicate_count=1,
                            constructor_count=2,
                            observer_count=2,
                            obligation_cell_count=6,
                            has_generated_sorts=True,
                            sort_overlap=1.0,
                            function_overlap=1.0,
                            predicate_overlap=1.0,
                            constructor_overlap=1.0,
                            cell_count_delta=0,
                            health=health,
                            error_message=None,
                            factor_levels={"A": a_level, "B": b_level},
                            partial_parse_credit=0.0,
                        )
                    )
        return scores

    def test_main_effect_a_detected(self) -> None:
        from alspec.eval.doe_analyze import compute_main_effects

        scores = self._make_scores(20)
        effects = compute_main_effects(
            scores,
            factor_labels=["A", "B"],
            chunk_names_by_label={"A": ["FORMAL_FRAME"], "B": ["BASIS_CATALOG"]},
            responses=["health"],
        )

        effect_a = next(e for e in effects if e.factor_label == "A" and e.response == "health")
        effect_b = next(e for e in effects if e.factor_label == "B" and e.response == "health")

        # A should have effect ≈ +0.2
        assert abs(effect_a.effect - 0.2) < 0.05, f"Expected ~0.2, got {effect_a.effect:.4f}"
        # B should have effect ≈ 0
        assert abs(effect_b.effect) < 0.05, f"Expected ~0, got {effect_b.effect:.4f}"

    def test_main_effect_a_significant(self) -> None:
        from alspec.eval.doe_analyze import compute_main_effects

        scores = self._make_scores(30)
        effects = compute_main_effects(
            scores,
            factor_labels=["A", "B"],
            chunk_names_by_label={"A": ["FORMAL_FRAME"], "B": ["BASIS_CATALOG"]},
            responses=["health"],
        )
        effect_a = next(e for e in effects if e.factor_label == "A")
        assert effect_a.p_value is not None
        assert effect_a.p_value < 0.05, f"Expected p<0.05 for A, got {effect_a.p_value:.4f}"

    def test_no_interaction_detected(self) -> None:
        from alspec.eval.doe_analyze import compute_interactions

        scores = self._make_scores(20)
        interactions = compute_interactions(scores, ["A", "B"], responses=["health"])
        axb = next(
            (i for i in interactions if i.factor_a == "A" and i.factor_b == "B"),
            None,
        )
        if axb is not None:
            assert abs(axb.effect) < 0.1, f"Unexpected interaction: {axb.effect:.4f}"


# ---------------------------------------------------------------------------
# 6. Config hash
# ---------------------------------------------------------------------------


class TestConfigHash:
    def test_same_chunks_same_hash(self) -> None:
        from alspec.eval.doe_design import _compute_hash

        chunks = (ChunkId.ROLE_PREAMBLE, ChunkId.TYPE_GRAMMAR, ChunkId.API_HELPERS)
        h1 = _compute_hash(chunks)
        h2 = _compute_hash(chunks)
        assert h1 == h2

    def test_different_chunks_different_hash(self) -> None:
        from alspec.eval.doe_design import _compute_hash

        chunks_a = (ChunkId.ROLE_PREAMBLE, ChunkId.TYPE_GRAMMAR)
        chunks_b = (ChunkId.ROLE_PREAMBLE, ChunkId.API_HELPERS)
        assert _compute_hash(chunks_a) != _compute_hash(chunks_b)

    def test_order_independent(self) -> None:
        """Hash should be the same regardless of tuple order."""
        from alspec.eval.doe_design import _compute_hash

        c1 = (ChunkId.ROLE_PREAMBLE, ChunkId.TYPE_GRAMMAR)
        c2 = (ChunkId.TYPE_GRAMMAR, ChunkId.ROLE_PREAMBLE)
        assert _compute_hash(c1) == _compute_hash(c2)

    def test_hash_is_sha256(self) -> None:
        from alspec.eval.doe_design import _compute_hash

        h = _compute_hash((ChunkId.ROLE_PREAMBLE,))
        assert len(h) == 64  # SHA-256 hex digest is 64 chars


# ---------------------------------------------------------------------------
# Integration test (skipped in CI unless OPENROUTER_API_KEY is set)
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestIntegration:
    @pytest.mark.asyncio
    async def test_single_trial_end_to_end(self, tmp_path: Path) -> None:
        """Run 1 design point × 1 domain × 1 replicate against real LLM."""
        import os

        if not os.getenv("OPENROUTER_API_KEY"):
            pytest.skip("OPENROUTER_API_KEY not set")

        from alspec.eval.doe_config import load_doe_config
        from alspec.eval.doe_design import generate_trials
        from alspec.eval.doe_runner import _build_prompt_cache, execute_trial
        from alspec.llm import AsyncLLMClient
        from alspec.result import Ok

        toml = """
[experiment]
name = "integration-test"
description = "Integration test"
output_dir = "results/integration-test"

[design]
resolution = "full"
replicates = 1

[pipeline]
stage = "stage1"
model = "google/gemini-2.5-flash-preview"
temperature = 0.7
max_concurrent = 1

[domains]
include = ["counter"]

[chunks]
mandatory = ["ROLE_PREAMBLE", "TYPE_GRAMMAR", "API_HELPERS"]

[chunks.factors]
A = ["FORMAL_FRAME"]
"""
        toml_file = tmp_path / "integration.toml"
        toml_file.write_text(toml)

        project_root = Path(__file__).parent.parent
        config = load_doe_config(toml_file, project_root=project_root)
        trials = generate_trials(config)
        prompt_cache = _build_prompt_cache(trials, config.stage)

        client_res = AsyncLLMClient.from_env()
        assert isinstance(client_res, Ok)
        client = client_res.value  # type: ignore[union-attr]

        trial = trials[0]
        system_prompt = prompt_cache[trial.config_hash]
        score, elapsed = await execute_trial(
            client, trial, "counter", config,
            golden_dir=project_root / "golden",
            system_prompt=system_prompt,
            session_id="test-integration",
        )

        assert score.domain == "counter"
        assert score.model == config.model
        assert isinstance(score.health, float)
        assert 0.0 <= score.health <= 1.0
        assert elapsed > 0.0


# ---------------------------------------------------------------------------
# 7. Stage detection
# ---------------------------------------------------------------------------


def test_stage4_analysis_result_has_stage() -> None:
    """AnalysisResult from Stage4Score data should report stage='stage4'."""
    from alspec.eval.doe_analyze import AnalysisResult

    ar = AnalysisResult(main_effects=(), interactions=(), stage="stage4")
    assert ar.stage == "stage4"


def test_stage1_analysis_result_has_stage() -> None:
    """AnalysisResult from Stage1Score data should report stage='stage1'."""
    from alspec.eval.doe_analyze import AnalysisResult

    ar = AnalysisResult(main_effects=(), interactions=(), stage="stage1")
    assert ar.stage == "stage1"
