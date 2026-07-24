"""Integration tests for ChromaDB vector store operations.

Uses temporary directories — no persistent data is modified.
"""

import pytest

from tui_agents.storage.vector_store import VectorStore
from tui_agents.utils.config import Config


@pytest.mark.integration
class TestVectorStore:
    @pytest.mark.asyncio
    async def test_add_and_query(self, test_vector_store: VectorStore):
        doc_id = test_vector_store.add(
            text="Diffusion models and optimal transport theory are fundamental tools.",
            metadata={"paper_id": "paper-1", "section": "abstract"},
        )
        assert doc_id
        assert test_vector_store.count == 1

        docs, metas, dists = test_vector_store.query("diffusion optimal transport")
        assert len(docs) == 1
        assert docs[0] is not None
        assert metas[0]["paper_id"] == "paper-1"

    @pytest.mark.asyncio
    async def test_add_batch(self, test_vector_store: VectorStore):
        texts = [
            "Score-based generative models use stochastic differential equations.",
            "Flow matching provides a simulation-free training objective.",
            "Optimal transport distances measure geometric differences between distributions.",
        ]
        metadatas = [
            {"paper_id": "a"},
            {"paper_id": "b"},
            {"paper_id": "c"},
        ]
        ids = test_vector_store.add_batch(texts, metadatas)
        assert len(ids) == 3
        assert test_vector_store.count == 3

    @pytest.mark.asyncio
    async def test_query_by_ids(self, test_vector_store: VectorStore):
        doc_id = test_vector_store.add(
            text="Test document for retrieval.",
            metadata={"paper_id": "retrieval-test"},
        )
        docs, metas = test_vector_store.query_by_ids([doc_id])
        assert len(docs) == 1
        assert "Test document" in docs[0]

    @pytest.mark.asyncio
    async def test_delete_single(self, test_vector_store: VectorStore):
        doc_id = test_vector_store.add(
            text="Document to be deleted.",
            metadata={"paper_id": "delete-test"},
        )
        assert test_vector_store.count == 1

        test_vector_store.delete(doc_id)
        assert test_vector_store.count == 0

    @pytest.mark.asyncio
    async def test_delete_by_paper(self, test_vector_store: VectorStore):
        test_vector_store.add(
            text="Chunk 1 of paper X.",
            metadata={"paper_id": "paper-x"},
        )
        test_vector_store.add(
            text="Chunk 2 of paper X.",
            metadata={"paper_id": "paper-x"},
        )
        test_vector_store.add(
            text="Chunk 1 of paper Y.",
            metadata={"paper_id": "paper-y"},
        )
        assert test_vector_store.count == 3

        test_vector_store.delete_by_paper("paper-x")
        assert test_vector_store.count == 1

        docs, metas, _ = test_vector_store.query("paper Y")
        assert any("paper-y" in str(m) for m in metas)

    @pytest.mark.asyncio
    async def test_update_metadata(self, test_vector_store: VectorStore):
        doc_id = test_vector_store.add(
            text="Doc with metadata to update.",
            metadata={"paper_id": "update-test", "status": "old"},
        )

        test_vector_store.update_metadata(doc_id, {"paper_id": "update-test", "status": "new"})

        docs, metas = test_vector_store.query_by_ids([doc_id])
        assert metas[0]["status"] == "new"

    @pytest.mark.asyncio
    async def test_query_relevance_order(self, test_vector_store: VectorStore):
        test_vector_store.add(
            text="Bananas and apples are popular fruits for healthy eating.",
            metadata={"topic": "food"},
        )
        test_vector_store.add(
            text="Diffusion models are state-of-the-art for image generation.",
            metadata={"topic": "ml"},
        )
        test_vector_store.add(
            text="Score matching and optimal transport have deep connections in diffusion processes.",
            metadata={"topic": "ml"},
        )

        docs, metas, dists = test_vector_store.query(
            "diffusion models optimal transport score matching", n_results=3
        )

        assert len(docs) >= 2
        # ML-related docs should appear first
        ml_docs_first = any(
            m.get("topic") == "ml" for m in metas[:2]
        )
        assert ml_docs_first, f"Expected ML docs first, got topics: {[m.get('topic') for m in metas]}"

    @pytest.mark.asyncio
    async def test_empty_collection_query(self, test_vector_store: VectorStore):
        docs, metas, dists = test_vector_store.query("anything")
        assert docs == []
