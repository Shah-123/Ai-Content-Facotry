"""
Tests for Graph.agents.document_ingest

These cover the pure pipeline pieces (parsing, chunking, evidence wiring).
LLM calls are mocked so the suite runs offline.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from Graph.agents import document_ingest as di
from Graph.state import EvidencePack, EvidenceItem


# ---------------------------------------------------------------------------
# parse_document
# ---------------------------------------------------------------------------

def test_parse_txt(tmp_path: Path):
    p = tmp_path / "sample.txt"
    p.write_text("hello world\nthis is a test", encoding="utf-8")

    out = di.parse_document(p)
    assert "hello world" in out["text"]
    assert out["metadata"]["format"] == "txt"
    assert out["metadata"]["page_count"] >= 1


def test_parse_md(tmp_path: Path):
    p = tmp_path / "notes.md"
    p.write_text("# Heading\n\nSome paragraph.", encoding="utf-8")

    out = di.parse_document(p)
    assert "Heading" in out["text"]
    assert out["metadata"]["format"] == "md"


def test_parse_unsupported_extension(tmp_path: Path):
    p = tmp_path / "weird.xyz"
    p.write_text("data", encoding="utf-8")

    with pytest.raises(ValueError):
        di.parse_document(p)


def test_parse_missing_file(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        di.parse_document(tmp_path / "ghost.txt")


# ---------------------------------------------------------------------------
# chunk_text
# ---------------------------------------------------------------------------

def test_chunk_respects_max_chars():
    pages = ["alpha " * 100, "beta " * 100, "gamma " * 100]  # ~600 chars each
    chunks = di.chunk_text(pages, max_chars=800, overlap=50)

    assert len(chunks) >= 2
    for c in chunks:
        assert len(c.text) <= 800
        assert c.page_start >= 1
        assert c.page_end >= c.page_start


def test_chunk_splits_oversized_page():
    # Single page that is larger than max_chars must be hard-split.
    big = "x" * 5000
    chunks = di.chunk_text([big], max_chars=1000, overlap=100)

    assert len(chunks) > 1
    assert all(c.page_start == 1 and c.page_end == 1 for c in chunks)
    # Step is max_chars - overlap = 900, so we expect ~ceil(5000/900) chunks.
    assert len(chunks) >= 5


def test_chunk_empty_input_returns_empty():
    assert di.chunk_text([]) == []
    assert di.chunk_text([""]) == []


# ---------------------------------------------------------------------------
# extract_evidence_from_chunks
# ---------------------------------------------------------------------------

def _fake_pack(snippets: list[str]) -> EvidencePack:
    return EvidencePack(
        evidence=[
            EvidenceItem(
                title=f"Fact {i}",
                url="",
                snippet=s,
                published_at=None,
                source="ignored",
                authors=None,
            )
            for i, s in enumerate(snippets)
        ]
    )


def test_extract_evidence_uses_filename_as_source(monkeypatch):
    chunks = [
        di.Chunk("page-one body", page_start=1, page_end=1),
        di.Chunk("page-two body", page_start=2, page_end=2),
    ]

    # Mock the LLM extractor: each chunk yields exactly one EvidenceItem.
    class _FakeExtractor:
        def invoke(self, _messages):
            return _fake_pack(["fact about the topic"])

    class _FakeLLM:
        def with_structured_output(self, _schema):
            return _FakeExtractor()

    monkeypatch.setattr(di, "llm", _FakeLLM())

    items, truncated = di.extract_evidence_from_chunks(
        chunks, filename="my_paper.pdf", topic_hint="quantum"
    )

    assert truncated is False
    # De-dup logic collapses identical snippets across chunks.
    assert len(items) == 1
    item = items[0]
    assert item.source == "my_paper.pdf"
    assert item.url.startswith("file://my_paper.pdf#p")
    assert item.snippet == "fact about the topic"


def test_extract_evidence_truncates_long_documents(monkeypatch):
    many = [
        di.Chunk(f"chunk {i}", page_start=i + 1, page_end=i + 1)
        for i in range(di._MAX_CHUNKS + 5)
    ]

    class _Extractor:
        calls = 0

        def invoke(self, _msgs):
            _Extractor.calls += 1
            return _fake_pack([f"unique fact {_Extractor.calls}"])

    class _LLM:
        def with_structured_output(self, _schema):
            return _Extractor()

    monkeypatch.setattr(di, "llm", _LLM())

    items, truncated = di.extract_evidence_from_chunks(many, filename="big.pdf")

    assert truncated is True
    assert _Extractor.calls == di._MAX_CHUNKS
    # All produced facts are unique → none deduped.
    assert len(items) == di._MAX_CHUNKS


# ---------------------------------------------------------------------------
# sentence splitting and semantic chunking tests
# ---------------------------------------------------------------------------

def test_split_into_sentences():
    text = "Hello world. This is sentence two! And sentence three? Yes."
    sentences = di.split_into_sentences(text)
    assert sentences == [
        "Hello world.",
        "This is sentence two!",
        "And sentence three?",
        "Yes."
    ]


def test_semantic_chunking_basic():
    class FakeEmbeddings:
        def embed_documents(self, texts):
            # Return same dummy embedding vectors for all sentences
            return [[0.1, 0.2]] * len(texts)

    pages = ["Sentence one. Sentence two.", "Sentence three."]
    chunks = di.semantic_chunking(pages, FakeEmbeddings(), target_chunk_size=10, min_chunk_size=1)
    
    assert len(chunks) > 0
    assert chunks[0].text == "Sentence one."


# ---------------------------------------------------------------------------
# document_ingest_node
# ---------------------------------------------------------------------------

def test_document_ingest_node_loads_persisted_evidence(tmp_path: Path, monkeypatch):
    upload_id = "abc123"
    upload_dir = tmp_path / "uploads" / upload_id
    upload_dir.mkdir(parents=True)

    # Persist a fake evidence.json + meta.json
    (upload_dir / "evidence.json").write_text(
        '[{"title":"T","url":"file://doc.pdf#p1","snippet":"s","published_at":null,'
        '"source":"doc.pdf","authors":null}]',
        encoding="utf-8",
    )
    (upload_dir / "meta.json").write_text(
        '{"filename":"doc.pdf","pages":3,"chunks":1,"derived_topic":"My Topic"}',
        encoding="utf-8",
    )

    monkeypatch.setattr(di, "_resolve_uploads_root", lambda: tmp_path / "uploads")

    state = {
        "_job_id": "",
        "upload_id": upload_id,
        "source_mode": "auto_topic",
        "topic": "",
    }

    out = di.document_ingest_node(state)

    assert out["document_filename"] == "doc.pdf"
    assert len(out["evidence"]) == 1
    assert out["evidence"][0].source == "doc.pdf"
    # auto_topic + empty topic → derived topic promoted into state
    assert out.get("topic") == "My Topic"


def test_document_ingest_node_rag_retrieval(tmp_path: Path, monkeypatch):
    upload_id = "rag_test"
    upload_dir = tmp_path / "uploads" / upload_id
    upload_dir.mkdir(parents=True)

    # Persist fake embeddings.json + meta.json + evidence.json fallback
    # Embeddings: chunk 0 is "AI safety policy", chunk 1 is "baking cookies"
    (upload_dir / "embeddings.json").write_text(
        '['
        '  {"text": "AI safety policy details", "page_start": 1, "page_end": 1, "embedding": [1.0, 0.0]},'
        '  {"text": "baking cookies recipe and details", "page_start": 2, "page_end": 2, "embedding": [0.0, 1.0]}'
        ']',
        encoding="utf-8",
    )
    (upload_dir / "meta.json").write_text(
        '{"filename":"doc.pdf","pages":2,"chunks":2,"derived_topic":"My Topic"}',
        encoding="utf-8",
    )

    monkeypatch.setattr(di, "_resolve_uploads_root", lambda: tmp_path / "uploads")

    # Mock embeddings model and LLM evidence extraction
    class FakeEmbeddingsModel:
        def embed_query(self, query):
            # Query is "AI safety" -> returns embedding [1.0, 0.0]
            if "AI" in query:
                return [1.0, 0.0]
            return [0.0, 1.0]

    monkeypatch.setattr(di, "get_embeddings_model", lambda: FakeEmbeddingsModel())

    # Mock extract_evidence_from_chunks
    def mock_extract(chunks, filename, topic_hint, max_chunks):
        # Verify that only the relevant chunk was retrieved
        assert len(chunks) == 1
        assert chunks[0].text == "AI safety policy details"
        return [
            EvidenceItem(
                title="AI Fact",
                url="file://doc.pdf#p1",
                snippet=chunks[0].text,
                published_at=None,
                source=filename,
                authors=None,
            )
        ], False

    monkeypatch.setattr(di, "extract_evidence_from_chunks", mock_extract)

    state = {
        "_job_id": "",
        "upload_id": upload_id,
        "source_mode": "hybrid",
        "topic": "AI safety and risk planning",
        "target_keywords": ["AI"],
    }

    out = di.document_ingest_node(state)

    assert out["document_filename"] == "doc.pdf"
    assert len(out["evidence"]) == 1
    assert out["evidence"][0].snippet == "AI safety policy details"
