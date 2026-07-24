from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pypdf


@dataclass
class DocumentChunk:
    id: str
    text: str
    metadata: dict[str, Any]
    chunk_index: int
    total_chunks: int


def _clean_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text)
    text = text.strip()
    return text


def _split_sentences(text: str) -> list[str]:
    text = re.sub(r"\n\s*\n", "\n\n", text)
    paragraphs = text.split("\n\n")
    sentences: list[str] = []
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        sents = re.split(r"(?<=[.!?])\s+", para)
        sentences.extend(s for s in sents if s.strip())
    return sentences


def extract_text_from_pdf(pdf_path: str | Path) -> str:
    path = Path(pdf_path)
    if not path.exists():
        raise FileNotFoundError(f"PDF not found: {path}")

    reader = pypdf.PdfReader(str(path))
    pages: list[str] = []

    for page in reader.pages:
        text = page.extract_text()
        if text:
            pages.append(_clean_text(text))

    return "\n\n".join(pages)


def chunk_text(
    text: str,
    chunk_size: int = 4000,
    chunk_overlap: int = 500,
    metadata: dict[str, Any] | None = None,
) -> list[DocumentChunk]:
    if not text.strip():
        return []

    sentences = _split_sentences(text)
    if not sentences:
        return []

    chunks: list[DocumentChunk] = []
    current_chunk: list[str] = []
    current_length = 0
    pending_sentences: list[str] = []

    for sentence in sentences:
        sentence_len = len(sentence)

        if current_length + sentence_len > chunk_size and current_chunk:
            chunk_text_content = " ".join(current_chunk).strip()
            if chunk_text_content:
                chunks.append(DocumentChunk(
                    id=str(uuid.uuid4()),
                    text=chunk_text_content,
                    metadata={**(metadata or {}), "chunk_index": len(chunks)},
                    chunk_index=len(chunks),
                    total_chunks=0,
                ))

            if chunk_overlap > 0:
                overlap_text = ""
                pending_sentences = []
                for s in reversed(current_chunk):
                    candidate = s + " " + overlap_text
                    if len(candidate) <= chunk_overlap:
                        pending_sentences.insert(0, s)
                        overlap_text = candidate
                    else:
                        break
            else:
                pending_sentences = []

            current_chunk = list(pending_sentences)
            current_length = sum(len(s) + 1 for s in current_chunk)

        current_chunk.append(sentence)
        current_length += sentence_len + 1

    if current_chunk:
        chunk_text_content = " ".join(current_chunk).strip()
        if chunk_text_content:
            chunks.append(DocumentChunk(
                id=str(uuid.uuid4()),
                text=chunk_text_content,
                metadata={**(metadata or {}), "chunk_index": len(chunks)},
                chunk_index=len(chunks),
                total_chunks=0,
            ))

    total = len(chunks)
    for c in chunks:
        c.total_chunks = total

    return chunks


def estimate_token_count(text: str) -> int:
    return len(text) // 4
