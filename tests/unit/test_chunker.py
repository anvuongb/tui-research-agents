"""Tests for the PDF text chunker."""

import pytest

from tui_agents.sources.pdf import (
    DocumentChunk,
    chunk_text,
    estimate_token_count,
    _clean_text,
    _split_sentences,
)


class TestCleanText:
    def test_whitespace_collapsed(self):
        assert _clean_text("hello    world") == "hello world"

    def test_leading_trailing_whitespace_stripped(self):
        assert _clean_text("  hello world  ") == "hello world"

    def test_newlines_replaced_with_space(self):
        assert _clean_text("line one\nline two") == "line one line two"


class TestSplitSentences:
    def test_simple_sentences(self):
        result = _split_sentences("Hello world. This is a test. Another sentence!")
        assert len(result) == 3

    def test_paragraph_split(self):
        text = "First paragraph.\n\nSecond paragraph."
        result = _split_sentences(text)
        assert len(result) >= 2

    def test_empty_string(self):
        assert _split_sentences("") == []

    def test_no_periods(self):
        result = _split_sentences("hello world")
        assert len(result) == 1
        assert result[0] == "hello world"


class TestEstimateTokenCount:
    def test_rough_estimate(self):
        # ~4 chars per token
        assert estimate_token_count("abcdefgh") == 2
        assert estimate_token_count("a" * 100) == 25


class TestChunkText:
    def test_chunk_below_size_returns_single_chunk(self):
        text = "Short text. " * 5
        chunks = chunk_text(text, chunk_size=10000, chunk_overlap=500)
        assert len(chunks) == 1
        assert chunks[0].text == text.strip()

    def test_chunk_above_size_returns_multiple(self):
        text = "Hello world. This is a test. " * 500
        chunks = chunk_text(text, chunk_size=2000, chunk_overlap=200)
        assert len(chunks) > 1

    def test_chunks_have_correct_indexes(self):
        text = "Hello world. This is a test. " * 500
        chunks = chunk_text(text, chunk_size=2000, chunk_overlap=200)
        total = chunks[0].total_chunks
        for i, c in enumerate(chunks):
            assert c.chunk_index == i
            assert c.total_chunks == total

    def test_chunks_dont_exceed_size_plus_overlap_tolerance(self):
        text = "Hello world. This is a test sentence. " * 500
        chunks = chunk_text(text, chunk_size=2000, chunk_overlap=200)
        for c in chunks:
            assert len(c.text) <= 2500, f"Chunk too large: {len(c.text)} chars"

    def test_chunks_are_valid(self):
        text = "Hello world. This is a test. " * 500
        chunks = chunk_text(text, chunk_size=2000, chunk_overlap=200)
        for c in chunks:
            assert isinstance(c, DocumentChunk)
            assert c.id
            assert len(c.text) > 0
            assert isinstance(c.metadata, dict)

    def test_empty_input(self):
        chunks = chunk_text("")
        assert chunks == []

    def test_chunks_contain_original_content(self):
        text = "Unique phrase XYZ123. Another unique phrase ABC456."
        chunks = chunk_text(text, chunk_size=500, chunk_overlap=50)
        combined = " ".join(c.text for c in chunks)
        assert "Unique phrase XYZ123" in combined
        assert "ABC456" in combined
