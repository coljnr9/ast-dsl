import pytest
from alspec.prompt_chunks import (
    ChunkId, Concept, Stage, PromptAssemblyError,
    get_chunk, get_all_chunks, chunks_for_stage,
    assemble_prompt, build_default_prompt,
    SIG_AX, SIG, AX,
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
    
    def test_chunks_for_signature(self):
        """SIGNATURE chunks include SIG_AX and SIG, exclude AX-only."""
        sig_chunks = chunks_for_stage(Stage.SIGNATURE)
        ids = {c.id for c in sig_chunks}
        assert ChunkId.ROLE_PREAMBLE in ids          # SIG_AX
        assert ChunkId.FORMAL_FRAME in ids            # SIG_AX
        assert ChunkId.CELL_TIERS not in ids          # AX only
        assert ChunkId.PARTIAL_FN_PATTERNS not in ids # AX only
    
    def test_chunks_for_axioms(self):
        ax_chunks = chunks_for_stage(Stage.AXIOMS)
        ids = {c.id for c in ax_chunks}
        assert ChunkId.ROLE_PREAMBLE in ids      # SIG_AX
        assert ChunkId.CELL_TIERS in ids         # AX
        assert ChunkId.PARTIAL_FN_PATTERNS in ids # AX


class TestFourStageEnum:
    """Verify the 4-stage enum is correct."""

    def test_has_four_members(self):
        assert len(Stage) == 4

    def test_stage_names(self):
        names = {s.name for s in Stage}
        assert names == {"ANALYSIS", "SIGNATURE", "OBLIGATION", "AXIOMS"}

    def test_convenience_sets(self):
        assert SIG == frozenset({Stage.SIGNATURE})
        assert AX == frozenset({Stage.AXIOMS})
        assert SIG_AX == frozenset({Stage.SIGNATURE, Stage.AXIOMS})


class TestAssembly:
    def test_simple_assembly(self):
        prompt = assemble_prompt(
            [ChunkId.ROLE_PREAMBLE, ChunkId.FORMAL_FRAME],
            Stage.SIGNATURE,
        )
        assert "domain modeling expert" in prompt
        assert "Signature" in prompt
    
    def test_unknown_chunk_raises(self):
        """Instead test with a valid chunk in wrong stage."""
        with pytest.raises(PromptAssemblyError, match="not relevant"):
            assemble_prompt(
                [ChunkId.ROLE_PREAMBLE, ChunkId.CELL_TIERS],
                Stage.SIGNATURE,  # CELL_TIERS is AX-only
            )
    
    def test_missing_dependency_raises(self):
        with pytest.raises(PromptAssemblyError, match="depends on"):
            assemble_prompt(
                [ChunkId.ROLE_PREAMBLE, ChunkId.TYPE_GRAMMAR],  # missing FORMAL_FRAME
                Stage.SIGNATURE,
            )
    
    def test_dependency_validation_can_be_disabled(self):
        """With validate_deps=False, missing deps don't crash."""
        prompt = assemble_prompt(
            [ChunkId.ROLE_PREAMBLE, ChunkId.TYPE_GRAMMAR],
            Stage.SIGNATURE,
            validate_deps=False,
        )
        assert "Term" in prompt
    
    def test_stage_validation_can_be_disabled(self):
        """With validate_stage=False, wrong-stage chunks are allowed."""
        prompt = assemble_prompt(
            [ChunkId.ROLE_PREAMBLE, ChunkId.CELL_TIERS],
            Stage.SIGNATURE,
            validate_stage=False,
            validate_deps=False,
        )
        assert "SELECTOR_EXTRACT" in prompt


class TestDefaultConfigs:
    def test_signature_default_assembles(self):
        prompt = build_default_prompt(Stage.SIGNATURE)
        assert len(prompt) > 1000
        assert "domain modeling expert" in prompt
    
    def test_axioms_default_assembles(self):
        prompt = build_default_prompt(Stage.AXIOMS)
        assert len(prompt) > 1000
        assert "domain modeling expert" in prompt
    
    def test_signature_default_has_no_axioms_only_content(self):
        prompt = build_default_prompt(Stage.SIGNATURE)
        # CELL_TIERS content should NOT appear in Signature stage
        assert "Cell Tiers — How Much Reasoning" not in prompt
    
    def test_axioms_default_has_axiom_patterns(self):
        prompt = build_default_prompt(Stage.AXIOMS)
        assert "negation(definedness" in prompt


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
        assert 'spec = Spec(name="BugTracker"' in content

    def test_example_session_store_spec_has_axioms(self):
        chunk = get_chunk(ChunkId.EXAMPLE_SESSION_STORE_SPEC)
        content = chunk.render()
        assert "Step 1: Identify Sorts" in content
        assert "Axiom(" in content
        assert "def session_store_spec" not in content

    def test_example_rate_limiter_spec_has_axioms(self):
        chunk = get_chunk(ChunkId.EXAMPLE_RATE_LIMITER_SPEC)
        content = chunk.render()
        assert "Step 1: Identify Sorts" in content
        assert "Axiom(" in content
        assert "def rate_limiter_spec" not in content

    def test_example_dns_zone_spec_has_axioms(self):
        chunk = get_chunk(ChunkId.EXAMPLE_DNS_ZONE_SPEC)
        content = chunk.render()
        assert "Step 1: Identify Sorts" in content
        assert "Axiom(" in content
        assert "def dns_zone_spec" not in content


class TestStageMethodologyChunks:
    """Verify the new stage methodology chunks."""

    def test_signature_methodology_in_default_config(self):
        from alspec.prompt_chunks import Stage, build_default_prompt
        prompt = build_default_prompt(Stage.SIGNATURE)
        assert "Classify predicates" in prompt
        assert "Observer predicate" in prompt or "observer predicate" in prompt
        assert "Helper predicate" in prompt or "helper predicate" in prompt
        assert "submit_signature" in prompt

    def test_axioms_methodology_in_default_config(self):
        from alspec.prompt_chunks import Stage, build_default_prompt
        prompt = build_default_prompt(Stage.AXIOMS)
        assert "MISS cells" in prompt
        assert "submit_axiom_fills" in prompt

    def test_signature_methodology_stage_restriction(self):
        from alspec.prompt_chunks import get_chunk, ChunkId, Stage
        chunk = get_chunk(ChunkId.SIGNATURE_METHODOLOGY)
        assert Stage.SIGNATURE in chunk.stages
        assert Stage.AXIOMS not in chunk.stages

    def test_axioms_methodology_stage_restriction(self):
        from alspec.prompt_chunks import get_chunk, ChunkId, Stage
        chunk = get_chunk(ChunkId.AXIOMS_METHODOLOGY)
        assert Stage.AXIOMS in chunk.stages
        assert Stage.SIGNATURE not in chunk.stages


class TestConceptCoverage:
    """Verify that important concepts are covered by at least one chunk per stage."""
    
    def test_key_dispatch_covered_in_signature(self):
        sig_chunks = chunks_for_stage(Stage.SIGNATURE)
        all_concepts = frozenset().union(*(c.concepts for c in sig_chunks))
        assert Concept.KEY_DISPATCH in all_concepts
    
    def test_loose_semantics_covered_in_sig_and_axioms(self):
        for stage in (Stage.SIGNATURE, Stage.AXIOMS):
            chunks = chunks_for_stage(stage)
            all_concepts = frozenset().union(*(c.concepts for c in chunks))
            assert Concept.LOOSE_SEMANTICS in all_concepts, f"Missing in {stage.name}"
    
    def test_selectors_covered_in_signature(self):
        sig_chunks = chunks_for_stage(Stage.SIGNATURE)
        all_concepts = frozenset().union(*(c.concepts for c in sig_chunks))
        assert Concept.SELECTORS in all_concepts


class TestPipelineIntegration:
    """Verify the pipeline produces expected content when building prompts."""
    
    def test_signature_prompt_contains_expected_content(self):
        """Signature stage prompt should contain signature-relevant content."""
        from alspec.prompt_chunks import Stage, build_default_prompt
        prompt = build_default_prompt(Stage.SIGNATURE)
        
        # Must have: sort helpers, function classification, obligation table concept
        assert "atomic" in prompt
        assert "fn(" in prompt
        assert "constructor" in prompt.lower()
        assert "observer" in prompt.lower()
        assert "generated_sorts" in prompt
    
    def test_axioms_prompt_contains_expected_content(self):
        """Axioms stage prompt should contain axiom-writing content."""
        from alspec.prompt_chunks import Stage, build_default_prompt
        prompt = build_default_prompt(Stage.AXIOMS)
        
        # Must have: axiom patterns, partial function handling
        assert "negation(definedness" in prompt
        # Must have: all three new examples
        assert "Session Store" in prompt
        assert "Rate Limiter" in prompt
        assert "DNS Zone" in prompt
        # Must NOT have: legacy bug tracker references
        assert 'spec = Spec(name="BugTracker"' not in prompt

    def test_axioms_prompt_has_no_bug_tracker_references(self):
        """Axioms stage prompt should contain zero bug-tracker domain vocabulary."""
        from alspec.prompt_chunks import Stage, build_default_prompt
        prompt = build_default_prompt(Stage.AXIOMS)
        
        bug_tracker_terms = [
            "bug_tracker", "has_ticket", "resolve_ticket", "create_ticket",
            "get_assignee", "assign_ticket", "TicketId",
        ]
        for term in bug_tracker_terms:
            assert term not in prompt, f"Bug-tracker term '{term}' found in Axioms prompt"


class TestSubmitAnalysisToolRegistered:
    """Verify the submit_analysis tool is registered in the LLM module."""

    def test_tool_in_registry(self):
        from alspec.llm import _TOOL_REGISTRY
        assert "submit_analysis" in _TOOL_REGISTRY

    def test_tool_has_analysis_field(self):
        from alspec.llm import SUBMIT_ANALYSIS_TOOL
        fn_def = SUBMIT_ANALYSIS_TOOL["function"]
        params = fn_def["parameters"]  # type: ignore[index]
        assert "analysis" in params["properties"]  # type: ignore[index]
        assert "analysis" in params["required"]  # type: ignore[index]


class TestDomainAnalysisInPrompts:
    """Verify domain_analysis flows into the user prompts correctly."""

    def test_signature_user_prompt_includes_analysis(self):
        from alspec.pipeline import _build_signature_user_prompt
        prompt = _build_signature_user_prompt(
            "A simple counter",
            domain_analysis="ENTITIES: Counter with value...",
        )
        assert "ENTITIES: Counter with value" in prompt
        assert "Domain Analysis" in prompt

    def test_signature_user_prompt_omits_analysis_when_none(self):
        from alspec.pipeline import _build_signature_user_prompt
        prompt = _build_signature_user_prompt("A simple counter")
        assert "Domain Analysis" not in prompt

    def test_axioms_user_prompt_excludes_domain_analysis(self):
        """Stage 4 template intentionally drops domain_analysis; confirm it is never rendered."""
        from alspec.pipeline import _build_axioms_user_prompt
        from alspec.skeleton import SkeletonData
        skeleton = SkeletonData(
            imports="...",
            signature_code="sig = Signature(...)",
            mechanical_axiom_lines=(),
            remaining_cells_description="| obs | ctor |",
            spec_name="Counter"
        )
        prompt = _build_axioms_user_prompt(
            domain_description="A simple counter",
            spec_name="Counter",
            skeleton=skeleton,
            signature_analysis="Step 1: ...",
            domain_analysis="ENTITIES: Counter with value...",
        )
        # Even when domain_analysis is supplied, Stage 4 template must NOT render it
        assert "ENTITIES: Counter with value" not in prompt
        assert "Domain Analysis" not in prompt

    def test_axioms_user_prompt_omits_analysis_when_none(self):
        from alspec.pipeline import _build_axioms_user_prompt
        from alspec.skeleton import SkeletonData
        skeleton = SkeletonData(
            imports="...",
            signature_code="sig = Signature(...)",
            mechanical_axiom_lines=(),
            remaining_cells_description="| obs | ctor |",
            spec_name="Counter"
        )
        prompt = _build_axioms_user_prompt(
            domain_description="A simple counter",
            spec_name="Counter",
            skeleton=skeleton,
            signature_analysis="Step 1: ...",
        )
        assert "Domain Analysis" not in prompt

    def test_signature_user_prompt_has_no_methodology(self):
        """Verify generic methodology was moved to system prompt."""
        from alspec.pipeline import _build_signature_user_prompt
        prompt = _build_signature_user_prompt("A bank account system")
        # These should NOT be in the user prompt anymore
        assert "Classify functions" not in prompt
        assert "Mark partial functions" not in prompt
        assert "submit_signature" not in prompt

    def test_axioms_user_prompt_has_no_methodology(self):
        """Verify generic methodology was moved to system prompt."""
        from alspec.pipeline import _build_axioms_user_prompt
        from alspec.skeleton import SkeletonData
        skeleton = SkeletonData(
            imports="...",
            signature_code="sig = Signature(...)",
            mechanical_axiom_lines=(),
            remaining_cells_description="| obs | ctor |",
            spec_name="BankAccount"
        )
        prompt = _build_axioms_user_prompt(
            domain_description="A bank account system",
            spec_name="BankAccount",
            skeleton=skeleton,
            signature_analysis="Step 1: ...",
        )
        # These should NOT be in the user prompt anymore
        assert "Axiom writing rules" not in prompt
        assert "submit_spec" not in prompt
        assert "submit_axiom_fills" not in prompt
        assert "MISS cells" not in prompt
