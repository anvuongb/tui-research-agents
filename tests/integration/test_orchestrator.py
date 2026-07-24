"""Integration tests for Orchestrator.delete_paper() — verifies cascade cleanup
across SQLite, ChromaDB, and filesystem."""

from pathlib import Path

import pytest

from tui_agents.storage.models import Paper, PaperSource


@pytest.mark.integration
class TestDeletePaperFullCleanup:
    @pytest.mark.asyncio
    async def test_delete_removes_from_db_chroma_and_disk(
        self, test_orchestrator, tmp_config
    ):
        orch = test_orchestrator
        paper_id = "e2e-delete-test"

        paper = Paper(
            id=paper_id,
            source=PaperSource.ARXIV,
            source_id="arxiv:delete.1",
            title="Paper To Delete",
            authors=["Author"],
            abstract="Will be deleted.",
        )
        await orch.db.upsert_paper(paper)

        # Create ChromaDB embeddings for the paper
        orch.vector_store.add(
            text="Chunk one of paper to delete.",
            metadata={"paper_id": paper_id, "chunk_index": "0"},
        )
        orch.vector_store.add(
            text="Chunk two of paper to delete.",
            metadata={"paper_id": paper_id, "chunk_index": "1"},
        )

        # Create a dummy PDF file on disk
        papers_dir = Path(tmp_config.papers_dir) / paper_id
        papers_dir.mkdir(parents=True, exist_ok=True)
        pdf_path = papers_dir / "test.pdf"
        pdf_path.write_text("fake pdf content")
        paper.pdf_path = str(pdf_path)
        await orch.db.upsert_paper(paper)

        # Create a dummy code directory
        code_dir = Path(tmp_config.code_dir) / paper_id
        code_dir.mkdir(parents=True, exist_ok=True)
        (code_dir / "implementation.py").write_text("print('hello')")

        # Verify everything exists before delete
        assert await orch.db.get_paper(paper_id) is not None
        assert pdf_path.exists()
        assert code_dir.exists()
        chroma_docs, _, _ = orch.vector_store.query("chunk to delete")
        assert len(chroma_docs) >= 2

        # Delete
        await orch.delete_paper(paper_id)

        # Verify SQLite — paper gone
        assert await orch.db.get_paper(paper_id) is None

        # Verify PDF file gone
        assert not pdf_path.exists()
        assert not papers_dir.exists()

        # Verify code directory gone
        assert not code_dir.exists()

        # Verify ChromaDB embeddings gone
        chroma_docs, _, _ = orch.vector_store.query("chunk to delete")
        assert len(chroma_docs) == 0

    @pytest.mark.asyncio
    async def test_delete_nonexistent_paper_no_error(self, test_orchestrator):
        await test_orchestrator.delete_paper("does-not-exist")

    @pytest.mark.asyncio
    async def test_delete_preserves_unrelated_papers(
        self, test_orchestrator, tmp_config
    ):
        orch = test_orchestrator

        await orch.db.upsert_paper(Paper(
            id="keeper-delete", source=PaperSource.ARXIV, source_id="k.1",
            title="Keeper", authors=["A"],
        ))
        orch.vector_store.add(
            text="Keeper chunk one.", metadata={"paper_id": "keeper-delete"},
        )

        keep_code = Path(tmp_config.code_dir) / "keeper-delete"
        keep_code.mkdir(parents=True, exist_ok=True)
        (keep_code / "keep.py").write_text("keep me")

        # Create and delete a different paper
        await orch.db.upsert_paper(Paper(
            id="to-remove", source=PaperSource.ARXIV, source_id="r.1",
            title="Remove Me", authors=["B"],
        ))
        orch.vector_store.add(
            text="Remove me chunk.", metadata={"paper_id": "to-remove"},
        )

        await orch.delete_paper("to-remove")

        # Keeper should still exist in all stores
        assert await orch.db.get_paper("keeper-delete") is not None

        chroma_docs, _, _ = orch.vector_store.query("Keeper chunk")
        assert len(chroma_docs) >= 1

        assert keep_code.exists()
        assert (keep_code / "keep.py").exists()
