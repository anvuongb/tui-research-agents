import uuid
from pathlib import Path
from typing import Any

import chromadb
from chromadb.config import Settings


class VectorStore:
    def __init__(self, persist_directory: str | Path, collection_name: str = "papers"):
        self._persist_dir = str(persist_directory)
        Path(self._persist_dir).mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(
            path=self._persist_dir,
            settings=Settings(anonymized_telemetry=False),
        )
        self._collection_name = collection_name
        self._collection = self._client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    @property
    def collection(self):
        return self._collection

    @property
    def count(self) -> int:
        return self._collection.count()

    def add(
        self,
        text: str,
        metadata: dict[str, Any] | None = None,
        doc_id: str | None = None,
    ) -> str:
        doc_id = doc_id or str(uuid.uuid4())
        if metadata is None:
            metadata = {}
        self._collection.add(
            documents=[text],
            metadatas=[metadata],
            ids=[doc_id],
        )
        return doc_id

    def add_batch(
        self,
        texts: list[str],
        metadatas: list[dict[str, Any]] | None = None,
        ids: list[str] | None = None,
    ) -> list[str]:
        if ids is None:
            ids = [str(uuid.uuid4()) for _ in texts]
        if metadatas is None:
            metadatas = [{} for _ in texts]
        self._collection.add(
            documents=texts,
            metadatas=metadatas,
            ids=ids,
        )
        return ids

    def query(
        self, query_text: str, n_results: int = 5
    ) -> tuple[list[str], list[dict[str, Any]], list[float]]:
        results = self._collection.query(
            query_texts=[query_text],
            n_results=n_results,
        )
        docs = results.get("documents", [[]])[0]
        metas = results.get("metadatas", [[]])[0]
        dists = results.get("distances", [[]])[0]
        return docs, metas, dists

    def query_by_ids(
        self, ids: list[str]
    ) -> tuple[list[str], list[dict[str, Any]]]:
        results = self._collection.get(ids=ids)
        return results.get("documents", []), results.get("metadatas", [])

    def delete(self, doc_id: str) -> None:
        self._collection.delete(ids=[doc_id])

    def delete_by_paper(self, paper_id: str) -> None:
        existing = self._collection.get(
            where={"paper_id": paper_id}
        )
        if existing and existing.get("ids"):
            self._collection.delete(ids=existing["ids"])

    def update_metadata(self, doc_id: str, metadata: dict[str, Any]) -> None:
        self._collection.update(
            ids=[doc_id],
            metadatas=[metadata],
        )

    def clear(self) -> None:
        self._client.delete_collection(self._collection_name)
        self._collection = self._client.get_or_create_collection(
            name=self._collection_name,
            metadata={"hnsw:space": "cosine"},
        )
