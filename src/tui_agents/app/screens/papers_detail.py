"""Detail-panel rendering and implementation version navigation for
PapersScreen. Extracted from papers.py.

Mixed into PapersScreen.
"""

from __future__ import annotations

from textual.widgets import Button, DataTable, Label, Static


class PapersDetail:
    """Detail panel rendering, impl versioning, and code viewing."""

    _DETAIL_STATIC_IDS = (
        "detail-authors",
        "detail-year",
        "detail-source",
        "detail-abstract",
        "detail-distill-summary",
        "detail-distill-methodology",
        "detail-distill-contributions",
        "detail-distill-limitations",
        "detail-impl-summary",
    )

    def _selected_paper_id(self) -> str | None:
        table = self.query_one("#papers-table", DataTable)
        if table.cursor_row is None:
            return None
        row_key = table.coordinate_to_cell_key((table.cursor_row, 0))
        if row_key and row_key.row_key.value:
            return str(row_key.row_key.value)
        return None

    def _clear_detail_panel(self) -> None:
        self.query_one("#detail-title", Label).update("")
        for wid in self._DETAIL_STATIC_IDS:
            try:
                self.query_one(f"#{wid}", Static).update("")
            except Exception:
                pass
        self.query_one("#impl-controls").styles.display = "none"

    async def on_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        row_key = event.row_key
        if not (row_key and row_key.value):
            return
        row_id = str(row_key.value)
        paper = await self.app.orchestrator.db.get_paper(row_id)
        if not paper:
            self._clear_detail_panel()
            return

        self.query_one("#detail-title", Label).update(paper.title)
        self.query_one("#detail-authors", Static).update(
            f"Authors: {', '.join(paper.authors[:5])}"
        )
        self.query_one("#detail-year", Static).update(
            f"Published: {paper.published_date or 'N/A'}"
        )
        self.query_one("#detail-source", Static).update(
            f"Source: {paper.source.value} | Status: {paper.status}"
        )
        abstract = paper.abstract[:800] + ("..." if len(paper.abstract) > 800 else "")
        self.query_one("#detail-abstract", Static).update(abstract)

        distillation = await self.app.orchestrator.db.get_distillation(row_id)
        if distillation:
            summary = distillation.summary[:400] + ("..." if len(distillation.summary) > 400 else "")
            self.query_one("#detail-distill-summary", Static).update(
                f"\n[bold]Summary:[/] {summary}"
            )
            method = distillation.methodology[:300] + ("..." if len(distillation.methodology) > 300 else "")
            self.query_one("#detail-distill-methodology", Static).update(
                f"\n[bold]Methodology:[/] {method}"
            )
            contribs = "\n  - " + "\n  - ".join(distillation.contributions[:5])
            self.query_one("#detail-distill-contributions", Static).update(
                f"\n[bold]Contributions:[/]{contribs}"
            )
            lims = "\n  - " + "\n  - ".join(distillation.limitations[:3]) if distillation.limitations else " None noted"
            self.query_one("#detail-distill-limitations", Static).update(
                f"\n[bold]Limitations:[/]{lims}"
            )
        else:
            for wid in ("detail-distill-summary", "detail-distill-methodology",
                        "detail-distill-contributions", "detail-distill-limitations"):
                self.query_one(f"#{wid}", Static).update("")

        impls = await self.app.orchestrator.db.list_implementations(row_id)
        self._render_impl_controls(row_id, impls)

    def _render_impl_controls(self, row_id: str, impls: list) -> None:
        if impls:
            version_idx = self._impl_versions.get(row_id, 0)
            if version_idx >= len(impls):
                version_idx = len(impls) - 1
            self._impl_versions[row_id] = version_idx

            impl = impls[version_idx]
            deps = ", ".join(impl.dependencies[:5])
            self.query_one("#detail-impl-summary", Static).update(
                f"\n[bold]Implementation v{version_idx+1}/{len(impls)}:[/] "
                f"{len(impl.code)} chars, {len(impl.dependencies)} deps ({deps})"
            )
            self.query_one("#impl-version-label", Static).update(
                f"v{version_idx+1}/{len(impls)}"
            )
            self.query_one("#impl-controls").styles.display = "block"

            self.query_one("#impl-prev-btn", Button).disabled = (version_idx == 0)
            self.query_one("#impl-next-btn", Button).disabled = (version_idx >= len(impls) - 1)
            self.query_one("#view-code-btn", Button).disabled = False
            self.query_one("#delete-impl-btn", Button).disabled = False
            run_btn = self.query_one("#run-proto-btn", Button)
            run_btn.disabled = False
            run_btn.styles.display = "block"
        else:
            self.query_one("#detail-impl-summary", Static).update(
                "\n[bold]Implementation:[/] none yet — click Implement Selected"
            )
            self.query_one("#impl-version-label", Static).update("")
            self.query_one("#impl-controls").styles.display = "block"
            for bid in ("#impl-prev-btn", "#impl-next-btn", "#view-code-btn", "#delete-impl-btn"):
                self.query_one(bid, Button).disabled = True
            self.query_one("#run-proto-btn", Button).styles.display = "none"

    async def _view_selected_code(self) -> None:
        paper_id = self._selected_paper_id()
        if not paper_id:
            return
        impls = await self.app.orchestrator.db.list_implementations(paper_id)
        version_idx = self._impl_versions.get(paper_id, 0)
        if 0 <= version_idx < len(impls):
            impl = impls[version_idx]
            paper = await self.app.orchestrator.db.get_paper(paper_id)
            if paper:
                from tui_agents.app.screens.code_viewer import CodeViewer
                await self.app.push_screen(CodeViewer(
                    title=paper.title,
                    code=impl.code,
                    dependencies=impl.dependencies,
                ))

    async def _step_impl_version(self, delta: int) -> None:
        paper_id = self._selected_paper_id()
        if not paper_id:
            return
        impls = await self.app.orchestrator.db.list_implementations(paper_id)
        idx = self._impl_versions.get(paper_id, 0)
        new_idx = idx + delta
        if 0 <= new_idx < len(impls):
            self._impl_versions[paper_id] = new_idx
            await self._refresh_detail_panel(paper_id)

    async def _delete_selected_impl(self) -> None:
        paper_id = self._selected_paper_id()
        if not paper_id:
            return
        impls = await self.app.orchestrator.db.list_implementations(paper_id)
        idx = self._impl_versions.get(paper_id, 0)
        if 0 <= idx < len(impls):
            impl = impls[idx]
            await self.app.orchestrator.db.delete_implementation(impl.id)
            if paper_id in self._impl_versions:
                del self._impl_versions[paper_id]
            await self._refresh_detail_panel(paper_id)

    async def _refresh_detail_panel(self, paper_id: str) -> None:
        table = self.query_one("#papers-table", DataTable)
        for row_idx in range(table.row_count):
            key = table.coordinate_to_cell_key((row_idx, 0))
            if key and key.row_key.value == paper_id:
                event = type("FakeEvent", (), {"row_key": key.row_key})()
                await self.on_row_highlighted(event)
                break

    async def _move_cursor_to_paper(self, paper_id: str) -> None:
        try:
            table = self.query_one("#papers-table", DataTable)
            for row_idx in range(table.row_count):
                key = table.coordinate_to_cell_key((row_idx, 0))
                if key and key.row_key.value == paper_id:
                    table.move_cursor(row=row_idx)
                    break
        except Exception:
            pass
