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


class TestProgressAccumulation:
    """Verify multi-stage progress tracking auto-completes earlier stages."""

    STAGE_ORDER = {
        "search": 0, "loading": 1, "paper_text": 2, "github": 3,
        "evaluate": 4, "extract": 5, "generating": 6, "saving": 7,
        "done": 8, "error": 99, "waiting_input": 99,
    }

    def _apply_stage(self, stages, source, stage, pct, msg=""):
        """Simulate the core stage-accumulation logic from update_progress."""
        incoming_order = self.STAGE_ORDER.get(stage, 50)
        for s, info in stages.items():
            existing_order = self.STAGE_ORDER.get(s, 50)
            if existing_order < incoming_order and info["status"] == "⟳":
                info["status"] = "✓"

        status = "✓" if pct >= 1.0 else ("✗" if stage == "error" else "⟳")
        stages[stage] = {
            "msg": msg or stage,
            "pct": f"{int(pct * 100)}%",
            "status": status,
        }
        return stages

    def test_earlier_stages_auto_complete_on_new_stage(self):
        stages = {}
        self._apply_stage(stages, "impl", "loading", 0.05)
        self._apply_stage(stages, "impl", "paper_text", 0.08)
        self._apply_stage(stages, "impl", "github", 0.12)
        self._apply_stage(stages, "impl", "generating", 0.30)

        assert stages["loading"]["status"] == "✓"
        assert stages["paper_text"]["status"] == "✓"
        assert stages["github"]["status"] == "✓"
        assert stages["generating"]["status"] == "⟳"

    def test_done_stage_shows_checkmark(self):
        stages = {}
        self._apply_stage(stages, "impl", "loading", 0.05)
        self._apply_stage(stages, "impl", "generating", 0.30)
        self._apply_stage(stages, "impl", "done", 1.0)

        assert stages["loading"]["status"] == "✓"
        assert stages["generating"]["status"] == "✓"
        assert stages["done"]["status"] == "✓"

    def test_error_stage_shows_cross(self):
        stages = {}
        self._apply_stage(stages, "impl", "loading", 0.05)
        self._apply_stage(stages, "impl", "error", 0.0)

        assert stages["loading"]["status"] == "✓"
        assert stages["error"]["status"] == "✗"

    def test_stage_at_100_percent_shows_done(self):
        stages = {}
        self._apply_stage(stages, "impl", "saving", 1.0)
        assert stages["saving"]["status"] == "✓"

    def test_same_stage_repeated_updates_status(self):
        stages = {}

        self._apply_stage(stages, "impl", "generating", 0.30, msg="Starting...")
        assert stages["generating"]["status"] == "⟳"
        assert "Starting" in stages["generating"]["msg"]

        self._apply_stage(stages, "impl", "generating", 0.60, msg="Still going...")
        assert stages["generating"]["status"] == "⟳"
        assert "Still going" in stages["generating"]["msg"]

        self._apply_stage(stages, "impl", "generating", 1.0, msg="Done!")
        assert stages["generating"]["status"] == "✓"


class TestRunPrototypeButton:
    """Verify the Run Prototype button visibility/invisibility in the detail panel."""

    @pytest.mark.asyncio
    async def test_button_exists_in_compose(self, test_orchestrator):
        """The Run Prototype button is composed in the impl-controls row."""
        app = TuiAgentsApp(test_orchestrator)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            tabs = app.query_one(TabbedContent)
            tabs.active = "papers-tab"
            await pilot.pause(0.1)
            btn = app.query_one("#run-proto-btn", Button)
            assert btn is not None
            assert "Run Prototype" in str(btn.label)

    @pytest.mark.asyncio
    async def test_button_visible_when_implementation_exists(self, test_orchestrator):
        """Button shows and is enabled when the selected paper has implementations."""
        from tui_agents.storage.models import Paper, PaperSource, Implementation

        await test_orchestrator.db.upsert_paper(Paper(
            id="run-btn-test", source=PaperSource.ARXIV, source_id="rbt.1",
            title="Run Button Test", authors=["A"], status="prototyped",
        ))
        await test_orchestrator.db.save_implementation(Implementation(
            id="rbt-impl", paper_id="run-btn-test", run_id="r1", code="x",
        ))

        app = TuiAgentsApp(test_orchestrator)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            tabs = app.query_one(TabbedContent)
            tabs.active = "papers-tab"
            await pilot.pause(0.3)

            papers_screen = app.query_one("#papers-screen")
            await papers_screen._refresh_library()
            await pilot.pause(0.1)

            dt = app.query_one("#papers-table", DataTable)
            if dt.row_count > 0:
                key = dt.coordinate_to_cell_key((0, 0))
                event = type("FakeEvent", (), {"row_key": key.row_key})()
                await papers_screen.on_row_highlighted(event)
                await pilot.pause(0.1)

            btn = app.query_one("#run-proto-btn", Button)
            assert btn.styles.display != "none"
            assert not btn.disabled
