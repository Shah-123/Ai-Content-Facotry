"""
Tests for vector_store.py (ChromaDB Vector Store Manager)
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from vector_store import ChromaVectorStore, get_vector_store


@dataclass
class DummyChunk:
    text: str
    page_start: int = 1
    page_end: int = 1


def test_chroma_vector_store_init(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("CHROMA_PERSIST_DIR", str(tmp_path / "chroma_db"))
    vstore = ChromaVectorStore(collection_name="test_collection")
    assert vstore.collection_name == "test_collection"
    # persist_dir is a Path, not a str: comparing Paths avoids the separator
    # mismatch that a string comparison hits on Windows (C:/x vs C:\x).
    assert vstore.persist_dir == tmp_path / "chroma_db"


def test_upsert_and_query_chunks(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("CHROMA_PERSIST_DIR", str(tmp_path / "chroma_db"))
    monkeypatch.delenv("CHROMA_API_KEY", raising=False)

    vstore = ChromaVectorStore(collection_name="test_rag_docs")
    
    chunks = [
        DummyChunk(text="Artificial Intelligence and Large Language Models accelerate software engineering.", page_start=1, page_end=1),
        DummyChunk(text="Vector databases store dense embeddings for semantic RAG retrieval.", page_start=2, page_end=2),
        DummyChunk(text="Pexels and DALL-E generate high quality media assets.", page_start=3, page_end=3),
    ]
    
    dummy_embeddings = [
        [0.1] * 1536,
        [0.8] * 1536,
        [0.05] * 1536,
    ]

    upload_id = "test_upload_123"
    filename = "tech_overview.pdf"

    # Upsert
    success = vstore.upsert_chunks(
        upload_id=upload_id,
        filename=filename,
        chunks=chunks,
        embeddings=dummy_embeddings,
    )
    assert success is True

    # Query with upload_id filter
    results = vstore.query_similar_chunks(
        query_embedding=[0.8] * 1536,
        upload_id=upload_id,
        top_k=2,
    )

    assert len(results) > 0
    assert "text" in results[0]
    assert results[0]["metadata"]["upload_id"] == upload_id
    assert results[0]["metadata"]["filename"] == filename


def test_missing_embeddings_are_dropped_not_zero_filled(tmp_path: Path, monkeypatch):
    """A chunk whose embedding failed must NOT be indexed as a zero vector."""
    monkeypatch.setenv("CHROMA_PERSIST_DIR", str(tmp_path / "chroma_db"))
    monkeypatch.delenv("CHROMA_API_KEY", raising=False)

    vstore = ChromaVectorStore(collection_name="test_partial_emb")
    chunks = [
        DummyChunk(text="Chunk with a real embedding."),
        DummyChunk(text="Chunk whose embedding failed."),
    ]
    # Second embedding is empty (embedding generation failed for that chunk).
    embeddings = [[0.3] * 1536, []]

    assert vstore.upsert_chunks("u1", "doc.pdf", chunks, embeddings) is True

    # Only the one validly-embedded chunk should be stored.
    col = vstore.get_collection()
    assert col.count() == 1


def test_delete_upload_chunks(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("CHROMA_PERSIST_DIR", str(tmp_path / "chroma_db"))
    monkeypatch.delenv("CHROMA_API_KEY", raising=False)

    vstore = ChromaVectorStore(collection_name="test_delete_collection")

    chunks = [DummyChunk(text="Sample text content for deletion test.")]
    upload_id = "to_be_deleted_456"

    vstore.upsert_chunks(
        upload_id=upload_id,
        filename="delete_me.txt",
        chunks=chunks,
        embeddings=[[0.5] * 1536],
    )

    deleted = vstore.delete_upload_chunks(upload_id)
    assert deleted is True

    # Query should now return empty
    results = vstore.query_similar_chunks(
        query_text="Sample text",
        upload_id=upload_id,
        top_k=5,
    )
    assert len(results) == 0


def test_singleton_instance():
    v1 = get_vector_store()
    v2 = get_vector_store()
    assert v1 is v2


# ---------------------------------------------------------------------------
# Persist directory must not depend on the working directory
# ---------------------------------------------------------------------------


class TestPersistDirIsAnchoredToTheProject:
    """`CHROMA_PERSIST_DIR` used to default to a CWD-relative "./data/chroma_db".

    That meant uvicorn started from the repo root and pytest run from
    Agents_backend/ addressed two different databases. A document indexed by one
    was invisible to the other, so retrieval silently fell through to the
    local-embeddings fallback. This repository still contains both directories,
    each holding an initialised but empty collection — the fingerprint of the
    split. These tests pin the resolution rules so it cannot recur.
    """

    def test_default_is_independent_of_the_working_directory(self, tmp_path, monkeypatch):
        import os
        from vector_store import ChromaVectorStore, _BACKEND_DIR

        monkeypatch.delenv("CHROMA_PERSIST_DIR", raising=False)
        seen = set()
        for cwd in (tmp_path, _BACKEND_DIR, _BACKEND_DIR.parent):
            monkeypatch.chdir(cwd)
            seen.add(str(ChromaVectorStore().persist_dir))

        assert len(seen) == 1, f"index location varies with cwd: {seen}"
        assert str(_BACKEND_DIR) in seen.pop()

    def test_relative_env_value_anchors_to_the_backend_not_the_cwd(
        self, tmp_path, monkeypatch
    ):
        from vector_store import ChromaVectorStore, _BACKEND_DIR

        monkeypatch.setenv("CHROMA_PERSIST_DIR", "data/custom_index")
        monkeypatch.chdir(tmp_path)
        resolved = ChromaVectorStore().persist_dir

        assert resolved == (_BACKEND_DIR / "data" / "custom_index").resolve()
        assert str(tmp_path) not in str(resolved)

    def test_absolute_env_value_is_honoured_verbatim(self, tmp_path, monkeypatch):
        from vector_store import ChromaVectorStore

        target = tmp_path / "explicit_index"
        monkeypatch.setenv("CHROMA_PERSIST_DIR", str(target))
        assert ChromaVectorStore().persist_dir == target

    def test_empty_env_value_falls_back_to_the_default(self, monkeypatch):
        from vector_store import ChromaVectorStore, _DEFAULT_PERSIST_DIR

        monkeypatch.setenv("CHROMA_PERSIST_DIR", "   ")
        assert ChromaVectorStore().persist_dir == _DEFAULT_PERSIST_DIR
