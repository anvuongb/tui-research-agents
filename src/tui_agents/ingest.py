"""
Local PDF ingestion script.

Usage:
    python -m tui_agents.ingest /path/to/pdf/folder [--dry-run] [--distill]

Walks a directory tree, finds all .pdf files, extracts text, chunks,
embeds in ChromaDB, and stores metadata in SQLite.
With --distill, also runs the LLM distillation step on each paper.
"""

import argparse
import asyncio
import shutil
import sys
import uuid
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tui_agents.sources.pdf import chunk_text, estimate_token_count, extract_text_from_pdf
from tui_agents.storage.database import Database
from tui_agents.storage.models import Paper, PaperSource
from tui_agents.storage.vector_store import VectorStore
from tui_agents.utils.config import load_config


def find_pdfs(root: Path, recursive: bool = True) -> list[Path]:
    if recursive:
        return sorted(root.rglob("*.pdf"))
    return sorted(root.glob("*.pdf"))


def make_paper_id(filepath: Path, root: Path) -> str:
    rel = filepath.relative_to(root)
    return str(uuid.uuid5(uuid.NAMESPACE_URL, str(rel)))


def make_title(filepath: Path) -> str:
    return filepath.stem.replace("_", " ").replace("-", " ")


async def ingest_pdfs(
    folder: str,
    recursive: bool = True,
    dry_run: bool = False,
    distill: bool = False,
) -> None:
    config = load_config()
    root = Path(folder).resolve()

    if not root.exists() or not root.is_dir():
        print(f"Error: {folder} is not a directory")
        sys.exit(1)

    pdfs = find_pdfs(root, recursive=recursive)
    print(f"Found {len(pdfs)} PDF(s) in {root}")

    if dry_run:
        for p in pdfs:
            print(f"  {p.relative_to(root)}")
        print(f"\nDry run — {len(pdfs)} file(s) would be ingested.")
        return

    db = Database(config.database_path)
    vs = VectorStore(
        persist_directory=config.chroma_persist_dir,
        collection_name=config.chroma_collection_name,
    )

    distiller = None
    if distill:
        from tui_agents.agents.distiller import DistillerAgent
        from tui_agents.llm.client import LLMClient

        llm = LLMClient(config)
        distiller = DistillerAgent(llm, db, vs)

    ingested = 0
    skipped = 0
    failed = 0
    distilled = 0

    for i, pdf_path in enumerate(pdfs):
        paper_id = make_paper_id(pdf_path, root)
        title = make_title(pdf_path)
        rel_path = str(pdf_path.relative_to(root)) if recursive else pdf_path.name

        existing = await db.get_paper(paper_id)
        if existing:
            if distill and distiller and existing.status != "distilled":
                print(f"[{i+1}/{len(pdfs)}] DISTILL: {rel_path}", end=" ", flush=True)
                try:
                    distillation = await distiller.distill(paper_id)
                    if distillation:
                        print(f"— {len(distillation.summary)} chars summary ✓")
                        distilled += 1
                    else:
                        print("✗ (no result)")
                except Exception as e:
                    print(f"✗ ({e})")
            else:
                print(f"[{i+1}/{len(pdfs)}] SKIP (already ingested): {rel_path}")
                skipped += 1
            continue

        try:
            print(f"[{i+1}/{len(pdfs)}] INGEST: {rel_path}", end=" ", flush=True)

            text = await asyncio.to_thread(extract_text_from_pdf, str(pdf_path))
            if not text.strip():
                print("— empty PDF, skipping")
                skipped += 1
                continue

            token_est = estimate_token_count(text)
            print(f"({len(text)} chars, ~{token_est} tokens)", end=" ", flush=True)

            chunks = chunk_text(text, chunk_size=4000, chunk_overlap=500)
            print(f"— {len(chunks)} chunks", end=" ", flush=True)

            abstract = text[:500] if text else ""

            papers_dir = Path(config.papers_dir) / paper_id
            papers_dir.mkdir(parents=True, exist_ok=True)
            dest_pdf = papers_dir / pdf_path.name
            shutil.copy2(str(pdf_path), str(dest_pdf))

            paper = Paper(
                id=paper_id,
                source=PaperSource.LOCAL,
                source_id=str(rel_path),
                title=title,
                authors=[],
                abstract=abstract,
                url=None,
                pdf_path=str(dest_pdf),
                published_date=None,
                tags=[],
                status="collected",
                created_at=datetime.now().isoformat(),
                updated_at=datetime.now().isoformat(),
            )

            embedding_ids = []
            for chunk in chunks:
                doc_id = await asyncio.to_thread(
                    vs.add,
                    text=chunk.text,
                    metadata={
                        "paper_id": paper_id,
                        "chunk_index": str(chunk.chunk_index),
                        "total_chunks": str(chunk.total_chunks),
                        "source": "local",
                    },
                )
                embedding_ids.append(doc_id)
            paper.embedding_id = embedding_ids[0] if embedding_ids else None

            await db.upsert_paper(paper)
            print("✓")
            ingested += 1

            if distiller:
                print(f"         DISTILL:", end=" ", flush=True)
                try:
                    async def dist_progress(stage: str, msg: str, pct: float) -> None:
                        pass

                    distillation = await distiller.distill(paper_id, progress=dist_progress)
                    if distillation and distillation.summary:
                        print(f"{len(distillation.summary)} chars summary ✓")
                        distilled += 1
                    elif distillation:
                        print("✗ (empty summary)")
                    else:
                        print("✗ (no result — may be API error, rate limit, or context overflow)")
                except Exception as e:
                    print(f"✗ ({e})")

        except Exception as e:
            print(f"✗ ({e})")
            failed += 1

    await db.close()

    summary_parts = [f"{ingested} ingested"]
    if skipped:
        summary_parts.append(f"{skipped} skipped")
    if failed:
        summary_parts.append(f"{failed} failed")
    if distill:
        summary_parts.append(f"{distilled} distilled")
    print(f"\nDone. {', '.join(summary_parts)}.")


def main():
    parser = argparse.ArgumentParser(description="Ingest local PDF files into TUI Research Agents")
    parser.add_argument("folder", help="Path to folder containing PDF files")
    parser.add_argument("--recursive", "-r", action="store_true", default=True,
                        help="Recursively search subfolders (default: True)")
    parser.add_argument("--no-recursive", action="store_true",
                        help="Only process PDFs in the top-level folder")
    parser.add_argument("--dry-run", action="store_true",
                        help="List files without ingesting")
    parser.add_argument("--distill", action="store_true",
                        help="Run LLM distillation after ingesting each paper (requires API key)")

    args = parser.parse_args()

    recursive = not args.no_recursive
    asyncio.run(ingest_pdfs(
        args.folder, recursive=recursive, dry_run=args.dry_run, distill=args.distill,
    ))


if __name__ == "__main__":
    main()
