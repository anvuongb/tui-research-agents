"""TUI tests using Textual's headless test mode (pilot).

These tests verify that the TUI app composes correctly and that
tab navigation, widget presence, and screen layout work as expected.

IMPORTANT: run_test() is expensive (ChromaDB ONNX model loads per test).
Tests using it are consolidated to minimize calls. Do not add standalone
run_test tests without strong justification.
"""

import pytest
from textual.widgets import (
    Button,
    DataTable,
    Input,
    Label,
    Static,
    TabbedContent,
)
from textual.widget import Widget

from tui_agents.app.tui import TuiAgentsApp
from tui_agents.app.screens.dashboard import DashboardScreen
from tui_agents.app.screens.papers import PapersScreen
from tui_agents.app.screens.pipeline import PipelineScreen
from tui_agents.app.screens.benchmarks import BenchmarksScreen
from tui_agents.app.screens.config_screen import ConfigScreen


@pytest.mark.tui
class TestScreenClassHierarchy:
    """Verify all tab content classes are Widget subclasses, not Screen.

    Screen subclasses inside TabPane break tab switching because
    Screen has its own display management that conflicts with TabbedContent.
    This is a regression test for a critical bug.
    """

    def test_dashboard_is_widget(self):
        assert issubclass(DashboardScreen, Widget)

    def test_papers_is_widget(self):
        assert issubclass(PapersScreen, Widget)

    def test_pipeline_is_widget(self):
        assert issubclass(PipelineScreen, Widget)

    def test_benchmarks_is_widget(self):
        assert issubclass(BenchmarksScreen, Widget)

    def test_config_is_widget(self):
        assert issubclass(ConfigScreen, Widget)


@pytest.mark.tui
@pytest.mark.timeout(120)
class TestTUIComposeAndLayout:
    """Verify the TUI app composes correctly with all widgets present.

    Runs a single run_test() session and validates all screens in one go
    to avoid the overhead of multiple Textual app startups.
    """

    @pytest.mark.asyncio
    async def test_all_screens_compose_and_have_required_widgets(self, test_orchestrator):
        app = TuiAgentsApp(test_orchestrator)

        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            tabs = app.query_one(TabbedContent)
            assert tabs is not None
            assert tabs.tab_count == 5

            # --- Papers Screen ---
            tabs.active = "papers-tab"
            await pilot.pause(0.1)
            papers = app.query_one("#papers-screen")
            assert papers is not None
            assert papers.query_one("#search-input", Input) is not None
            assert papers.query_one("#papers-table", DataTable) is not None

            # --- Dashboard Screen ---
            tabs.active = "dashboard-tab"
            await pilot.pause(0.1)
            dashboard = app.query_one("#dashboard-screen")
            assert dashboard is not None
            for stat_id in ["stat-total", "stat-collected", "stat-distilled", "stat-implemented"]:
                assert dashboard.query_one(f"#{stat_id}") is not None

            # --- Pipeline Screen ---
            tabs.active = "pipeline-tab"
            await pilot.pause(0.1)
            pipeline = app.query_one("#pipeline-screen")
            assert pipeline is not None
            for stage in ["collector", "distiller", "implementer", "prototyper", "benchmarker"]:
                assert pipeline.query_one(f"#stage-status-{stage}") is not None

            # --- Benchmarks Screen ---
            tabs.active = "benchmarks-tab"
            await pilot.pause(0.1)
            assert app.query_one("#benchmarks-screen") is not None

            # --- Config Screen ---
            tabs.active = "config-tab"
            await pilot.pause(0.1)
            assert app.query_one("#config-screen") is not None


@pytest.mark.tui
@pytest.mark.timeout(120)
class TestTabNavigation:
    """Verify tab switching works and does not bounce back.

    Tab bounce-back was a critical regression caused by using Screen
    subclasses inside TabPane. These tests ensure it stays fixed.
    """

    @pytest.mark.asyncio
    async def test_all_tabs_switch_and_no_bounce_back(self, test_orchestrator):
        app = TuiAgentsApp(test_orchestrator)

        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            tabs = app.query_one(TabbedContent)

            # Verify all tabs can be switched to via action_switch_tab
            tab_ids = ["dashboard-tab", "papers-tab", "pipeline-tab", "benchmarks-tab", "config-tab"]
            for target in tab_ids:
                app.action_switch_tab(target)
                await pilot.pause(0.1)
                assert tabs.active == target, f"Expected {target}, got {tabs.active}"

            # Bounce-back test: switch away from Papers and verify it stays
            tabs.active = "papers-tab"
            await pilot.pause(0.1)
            assert tabs.active == "papers-tab"

            tabs.active = "dashboard-tab"
            await pilot.pause(0.3)
            assert tabs.active == "dashboard-tab", f"Tab bounced back to {tabs.active}"

            await pilot.pause(0.5)
            assert tabs.active == "dashboard-tab", (
                f"Tab bounced back to {tabs.active} after 0.8s wait"
            )

            # Bounce-back test: Pipeline tab should stay put
            tabs.active = "pipeline-tab"
            await pilot.pause(0.5)
            assert tabs.active == "pipeline-tab", f"Pipeline tab bounced to {tabs.active}"


@pytest.mark.tui
class TestAppBindings:
    """Verify keyboard binding configuration is correct.

    Single-letter keys without modifiers get captured by the Input widget,
    so all tab navigation bindings must use ctrl+ to bypass input capture.
    """

    @pytest.mark.asyncio
    async def test_bindings_use_ctrl_modifier(self, test_orchestrator):
        app = TuiAgentsApp(test_orchestrator)

        nav_bindings = [b for b in app.BINDINGS if "switch_tab" in b.action]
        for b in nav_bindings:
            assert b.key.startswith("ctrl+"), (
                f"Binding '{b.key}' must use ctrl+ modifier to avoid Input capture"
            )

    @pytest.mark.asyncio
    async def test_all_five_tabs_have_bindings(self, test_orchestrator):
        app = TuiAgentsApp(test_orchestrator)

        switch_bindings = [b for b in app.BINDINGS if "switch_tab" in b.action]
        assert len(switch_bindings) == 5, f"Expected 5 tab bindings, got {len(switch_bindings)}"
