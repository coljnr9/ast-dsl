import pytest
from alspec.prompt_chunks import (
    ChunkId, Concept, Stage, PromptAssemblyError,
    get_chunk, get_all_chunks, chunks_for_stage,
    assemble_prompt, build_default_prompt,
    BOTH, S1, S2,
)


class TestRegistry:
    def test_all_chunks_registered(self):
        """Every ChunkId enum member has a registered chunk."""
        all_chunks = get_all_chunks()
        for cid in ChunkId:
            assert cid in all_chunks, f"{cid.name} not registered"
    
    def test_get_chunk_returns_correct_id(self):
        chunk = get_chunk(ChunkId.ROLE_PREAMBLE)
        assert chunk.id == ChunkId.ROLE_PREAMBLE
    
    def test_get_chunk_unknown_raises(self):
        """Accessing an unregistered chunk raises KeyError."""
        # This shouldn't happen if all ChunkIds are registered,
        # but test the mechanism
        from alspec.prompt_chunks import _REGISTRY
        # Temporarily remove one
        saved = _REGISTRY.pop(ChunkId.ROLE_PREAMBLE)
        try:
            with pytest.raises(KeyError):
                get_chunk(ChunkId.ROLE_PREAMBLE)
        finally:
            _REGISTRY[ChunkId.ROLE_PREAMBLE] = saved
    
    def test_chunks_for_stage1(self):
        """Stage 1 chunks include BOTH and S1, exclude S2-only."""
        s1_chunks = chunks_for_stage(Stage.STAGE1)
        ids = {c.id for c in s1_chunks}
        assert ChunkId.ROLE_PREAMBLE in ids          # BOTH
        assert ChunkId.FORMAL_FRAME in ids            # BOTH
        assert ChunkId.CELL_TIERS not in ids          # S2 only
        assert ChunkId.PARTIAL_FN_PATTERNS not in ids # S2 only
    
    def test_chunks_for_stage2(self):
        s2_chunks = chunks_for_stage(Stage.STAGE2)
        ids = {c.id for c in s2_chunks}
        assert ChunkId.ROLE_PREAMBLE in ids      # BOTH
        assert ChunkId.CELL_TIERS in ids         # S2
        assert ChunkId.PARTIAL_FN_PATTERNS in ids # S2


class TestAssembly:
    def test_simple_assembly(self):
        prompt = assemble_prompt(
            [ChunkId.ROLE_PREAMBLE, ChunkId.FORMAL_FRAME],
            Stage.STAGE1,
        )
        assert "domain modeling expert" in prompt
        assert "Signature" in prompt
    
    def test_unknown_chunk_raises(self):
        """Instead test with a valid chunk in wrong stage."""
        with pytest.raises(PromptAssemblyError, match="not relevant"):
            assemble_prompt(
                [ChunkId.ROLE_PREAMBLE, ChunkId.CELL_TIERS],
                Stage.STAGE1,  # CELL_TIERS is S2-only
            )
    
    def test_missing_dependency_raises(self):
        with pytest.raises(PromptAssemblyError, match="depends on"):
            assemble_prompt(
                [ChunkId.ROLE_PREAMBLE, ChunkId.TYPE_GRAMMAR],  # missing FORMAL_FRAME
                Stage.STAGE1,
            )
    
    def test_dependency_validation_can_be_disabled(self):
        """With validate_deps=False, missing deps don't crash."""
        prompt = assemble_prompt(
            [ChunkId.ROLE_PREAMBLE, ChunkId.TYPE_GRAMMAR],
            Stage.STAGE1,
            validate_deps=False,
        )
        assert "Term" in prompt
    
    def test_stage_validation_can_be_disabled(self):
        """With validate_stage=False, wrong-stage chunks are allowed."""
        prompt = assemble_prompt(
            [ChunkId.ROLE_PREAMBLE, ChunkId.CELL_TIERS],
            Stage.STAGE1,
            validate_stage=False,
            validate_deps=False,
        )
        assert "SELECTOR_EXTRACT" in prompt


class TestDefaultConfigs:
    def test_stage1_default_assembles(self):
        prompt = build_default_prompt(Stage.STAGE1)
        assert len(prompt) > 1000
        assert "domain modeling expert" in prompt
    
    def test_stage2_default_assembles(self):
        prompt = build_default_prompt(Stage.STAGE2)
        assert len(prompt) > 1000
        assert "domain modeling expert" in prompt
    
    def test_stage1_default_has_no_stage2_only_content(self):
        prompt = build_default_prompt(Stage.STAGE1)
        # CELL_TIERS content should NOT appear in Stage 1
        assert "Cell Tiers — How Much Reasoning" not in prompt
    
    def test_stage2_default_has_axiom_patterns(self):
        prompt = build_default_prompt(Stage.STAGE2)
        assert "Negation(Definedness" in prompt


class TestChunkContent:
    """Verify each chunk renders non-empty content."""
    
    @pytest.mark.parametrize("chunk_id", list(ChunkId))
    def test_chunk_renders_nonempty(self, chunk_id):
        chunk = get_chunk(chunk_id)
        content = chunk.render()
        assert isinstance(content, str)
        assert len(content) > 10, f"{chunk_id.name} rendered empty/trivial content"
    
    def test_example_stack_contains_golden_code(self):
        chunk = get_chunk(ChunkId.EXAMPLE_STACK)
        content = chunk.render()
        assert "stack_spec" in content
        assert "pop_new_undef" in content
    
    def test_example_bug_tracker_analysis_has_docstring_not_code(self):
        chunk = get_chunk(ChunkId.EXAMPLE_BUG_TRACKER_ANALYSIS)
        content = chunk.render()
        assert "Step 1: Identify Sorts" in content
        # Should NOT contain the full function definition (code starts after docstring)
        assert "def bug_tracker_spec" not in content
    
    def test_example_bug_tracker_code_has_code_not_docstring(self):
        chunk = get_chunk(ChunkId.EXAMPLE_BUG_TRACKER_CODE)
        content = chunk.render()
        assert "def bug_tracker_spec" in content
    
    def test_example_bug_tracker_full_has_both(self):
        chunk = get_chunk(ChunkId.EXAMPLE_BUG_TRACKER_FULL)
        content = chunk.render()
        assert "Step 1: Identify Sorts" in content
        assert "def bug_tracker_spec" in content


class TestConceptCoverage:
    """Verify that important concepts are covered by at least one chunk per stage."""
    
    def test_key_dispatch_covered_in_stage1(self):
        s1 = chunks_for_stage(Stage.STAGE1)
        all_concepts = frozenset().union(*(c.concepts for c in s1))
        assert Concept.KEY_DISPATCH in all_concepts
    
    def test_loose_semantics_covered_in_both_stages(self):
        for stage in Stage:
            chunks = chunks_for_stage(stage)
            all_concepts = frozenset().union(*(c.concepts for c in chunks))
            assert Concept.LOOSE_SEMANTICS in all_concepts, f"Missing in {stage.name}"
    
    def test_selectors_covered_in_stage1(self):
        s1 = chunks_for_stage(Stage.STAGE1)
        all_concepts = frozenset().union(*(c.concepts for c in s1))
        assert Concept.SELECTORS in all_concepts


class TestPipelineIntegration:
    """Verify the pipeline produces expected content when building prompts."""
    
    def test_stage1_prompt_contains_expected_content(self):
        """Stage 1 prompt should contain signature-relevant content."""
        from alspec.prompt_chunks import Stage, build_default_prompt
        prompt = build_default_prompt(Stage.STAGE1)
        
        # Must have: sort helpers, function classification, obligation table concept
        assert "atomic" in prompt
        assert "fn(" in prompt
        assert "constructor" in prompt.lower()
        assert "observer" in prompt.lower()
        assert "generated_sorts" in prompt
    
    def test_stage2_prompt_contains_expected_content(self):
        """Stage 2 prompt should contain axiom-writing content."""
        from alspec.prompt_chunks import Stage, build_default_prompt
        prompt = build_default_prompt(Stage.STAGE2)
        
        # Must have: axiom patterns, partial function handling, worked example
        assert "Negation(Definedness" in prompt
        assert "eq_id" in prompt
        assert "bug_tracker_spec" in prompt
