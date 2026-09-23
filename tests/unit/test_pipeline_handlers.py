"""Unit tests for PipelineScreen._update_stage_statuses missing-widget
guard (H6) and the GitHub-link progress stage wiring (H2)."""

from unittest.mock import MagicMock

import pytest

from tui_agents.app.screens.pipeline import PipelineScreen


class TestPipelineWidgetGuard:
    def test_missing_stage_widget_does_not_raise(self):
        """H6 regression: 'orchestrator' (loop/done/error) maps to a stage
        with no composed widgets. The guard must swallow it, not crash."""
        screen = PipelineScreen()
        # Unmounted screen: query() returns empty NodeList for any selector
        screen._update_stage_statuses("orchestrator", "Iteration 1/5")
        screen._update_stage_statuses("nonexistent", "whatever")

    def test_missing_status_widget_alone_does_not_raise(self):
        screen = PipelineScreen()
        screen._update_stage_statuses("collector", "Ready")


class TestGithubLinkStageWiring:
    def test_needs_github_link_stage_in_pipeline_map(self):
        """H2 regression: the implementer emits 'needs_github_link' — the
        pipeline stage_map must know how to route it."""
        import re
        from pathlib import Path

        source = (Path(__file__).resolve().parents[2] / "src/tui_agents/app/screens/pipeline.py").read_text()
        assert '"needs_github_link"' in source

    def test_needs_github_link_stage_in_papers_stage_order(self):
        """The spinner auto-completion map must include the new stage."""
        import ast
        from pathlib import Path

        source = (Path(__file__).resolve().parents[2] / "src/tui_agents/app/screens/papers.py").read_text()
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == "PapersScreen":
                for item in node.body:
                    if isinstance(item, ast.Assign):
                        for target in item.targets:
                            if isinstance(target, ast.Name) and target.id == "STAGE_ORDER":
                                keys = {k.value for k in item.value.keys if isinstance(k, ast.Constant)}
                                assert "needs_github_link" in keys
                                return
        raise AssertionError("STAGE_ORDER not found")

    def test_implementer_emits_needs_github_link(self):
        """H2 regression: implementer.py must emit the stage before
        returning None, otherwise the UI never opens the GitHub modal."""
        from pathlib import Path
        source = (Path(__file__).resolve().parents[2] / "src/tui_agents/agents/implementer.py").read_text()
        assert '"needs_github_link"' in source
        # And it must be emitted before the return-None signal
        emit_pos = source.index('"needs_github_link"')
        return_pos = source.index("return None  # Signal: need user GitHub link")
        assert emit_pos < return_pos
