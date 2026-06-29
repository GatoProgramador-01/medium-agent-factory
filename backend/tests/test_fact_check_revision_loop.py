"""
RED-phase TDD tests for revision → fact_check graph wiring.

Current state  (FAILS): g.add_edge("revision", "quality_analysis")
Target state   (PASSES): g.add_edge("revision", "fact_check")
"""
import pytest
from app.agents.orchestrator import build_graph


def _edge_pairs(compiled) -> set[tuple[str, str]]:
    return {(e.source, e.target) for e in compiled.get_graph().edges}


class TestRevisionLoopIncludesFactCheck:
    def setup_method(self):
        self.compiled = build_graph()
        self.edges = _edge_pairs(self.compiled)

    def test_revision_routes_to_fact_check_not_quality_analysis(self):
        assert ("revision", "fact_check") in self.edges, (
            "revision must route to fact_check so revised content is verified"
        )
        assert ("revision", "quality_analysis") not in self.edges, (
            "revision must NOT skip directly to quality_analysis"
        )

    def test_fact_check_appears_twice_in_full_pipeline_path(self):
        # title_optimization sits between content_generation and fact_check
        assert ("content_generation", "title_optimization") in self.edges, (
            "content_generation must route to title_optimization first"
        )
        assert ("title_optimization", "fact_check") in self.edges, (
            "fact_check must run after title_optimization (initial path)"
        )
        assert ("revision", "fact_check") in self.edges, (
            "fact_check must re-run after every revision"
        )
        assert ("fact_check", "quality_analysis") in self.edges, (
            "fact_check must always feed into quality_analysis"
        )

    def test_revision_loop_does_not_bypass_fact_check(self):
        assert ("revision", "quality_analysis") not in self.edges, (
            "Revision must pass through fact_check to prevent "
            "unverified claims in revised content"
        )


class TestFactCheckGraphConnectivity:
    def setup_method(self):
        self.compiled = build_graph()
        self.edges = _edge_pairs(self.compiled)

    def test_all_paths_to_quality_analysis_pass_through_fact_check(self):
        predecessors = {src for src, tgt in self.edges if tgt == "quality_analysis"}
        assert predecessors == {"fact_check"}, (
            f"Only fact_check should feed quality_analysis, got: {predecessors}"
        )
