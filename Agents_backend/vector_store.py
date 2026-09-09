"""
vector_store.py — ChromaDB Vector Database Manager for RAG.

Provides a robust interface to Chroma Cloud and local persistent ChromaDB collections,
enabling semantic vector indexing and similarity retrieval over document chunks.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("Agents_backend.vector_store")

try:
    import chromadb
    CHROMA_AVAILABLE = True
except ImportError:
    chromadb = None
    CHROMA_AVAILABLE = False
    logger.warning("chromadb package is not installed. VectorStore will operate in fallback mode.")


COLLECTION_NAME = "ai_content_factory_documents"

# The backend package root — the same anchor db.py and event_bus.py use for
# their data directories.
_BACKEND_DIR = Path(__file__).resolve().parent
_DEFAULT_PERSIST_DIR = _BACKEND_DIR / "data" / "chroma_db"


def _resolve_persist_dir(raw: str) -> Path:
    """Anchor the on-disk index to the project, never to the launch directory.

    `CHROMA_PERSIST_DIR` used to default to the literal "./data/chroma_db",
    which Path.resolve() interprets against the CURRENT WORKING DIRECTORY. So
    `uvicorn` started from the repo root and `pytest` run from Agents_backend/
    addressed two different databases, and a document indexed by one was
    invisible to the other — the retrieval layer silently fell through to its
    local-embeddings fallback and, before the grounding gate existed, on to an
    ungrounded post. (This repository contains both directories, each holding
    an initialised but empty collection: the fingerprint of exactly that split.)

    An absolute value is honoured as given. A relative one is resolved against
    the backend directory, so it means the same place regardless of where the
    process was started.
    """
    if not raw:
        return _DEFAULT_PERSIST_DIR
    candidate = Path(raw).expanduser()
    return candidate if candidate.is_absolute() else (_BACKEND_DIR / candidate).resolve()


class ChromaVectorStore:
    """Manages document chunk embeddings and vector search via ChromaDB Cloud or Local storage."""

    def __init__(self, collection_name: str = COLLECTION_NAME):
        self.collection_name = collection_name
        self.api_key = os.getenv("CHROMA_API_KEY", "").strip()
        self.tenant = os.getenv("CHROMA_TENANT", "default_tenant").strip()
        self.database = os.getenv("CHROMA_DATABASE", "default_database").strip()
        self.persist_dir = _resolve_persist_dir(os.getenv("CHROMA_PERSIST_DIR", "").strip())
        self._client = None
        self._collection = None

    def _get_client(self):
        """Lazy-initialize ChromaDB client with Cloud API support and local persistent fallback."""
        global chromadb, CHROMA_AVAILABLE
        if self._client is not None:
            return self._client

        if not CHROMA_AVAILABLE:
            try:
                import chromadb
                CHROMA_AVAILABLE = True
            except ImportError:
                CHROMA_AVAILABLE = False
                raise RuntimeError("chromadb library is not installed.")

        # Try CloudClient if API key is provided
        if self.api_key:
            try:
                logger.info(f"Connecting to Chroma Cloud (tenant: {self.tenant}, db: {self.database})...")
                if hasattr(chromadb, "CloudClient"):
                    self._client = chromadb.CloudClient(
                        api_key=self.api_key,
                        tenant=self.tenant,
                        database=self.database,
                    )
                elif hasattr(chromadb, "HttpClient"):
                    self._client = chromadb.HttpClient(
                        headers={"x-chroma-token": self.api_key}
                    )
                logger.info("Successfully connected to Chroma Cloud!")
                return self._client
            except Exception as exc:
                logger.warning(
                    f"Chroma Cloud connection failed: {exc}. Falling back to local PersistentClient."
                )

        # Fallback to local PersistentClient
        abs_persist_dir = Path(self.persist_dir).resolve()
        abs_persist_dir.mkdir(parents=True, exist_ok=True)
        # Logged at INFO because "the index looks empty" is almost always "the
        # index is somewhere else" — this line is what tells you where.
        logger.info(f"Initializing local Chroma PersistentClient at {abs_persist_dir}...")
        self._client = chromadb.PersistentClient(path=str(abs_persist_dir))
        return self._client

    def get_collection(self):
        """Obtain or create the target collection."""
        if self._collection is not None:
            return self._collection

        client = self._get_client()
        try:
            self._collection = client.get_or_create_collection(
                name=self.collection_name,
                metadata={"hnsw:space": "cosine"},
            )
            return self._collection
        except Exception as exc:
            logger.error(f"Failed to get/create Chroma collection '{self.collection_name}': {exc}")
            raise

    def upsert_chunks(
        self,
        upload_id: str,
        filename: str,
        chunks: List[Any],
        embeddings: Optional[List[List[float]]] = None,
    ) -> bool:
        """Upsert document chunks into the ChromaDB collection.

        Args:
            upload_id: Unique string ID for the upload batch.
            filename: Original document filename.
            chunks: List of Chunk objects containing text, page_start, page_end.
            embeddings: Optional precomputed list of float embedding vectors.
        """
        if not chunks:
            return False

        try:
            col = self.get_collection()
            ids = [f"{upload_id}_chunk_{i}" for i in range(len(chunks))]
            documents = [c.text for c in chunks]
            metadatas = [
                {
                    "upload_id": upload_id,
                    "filename": filename,
                    "page_start": getattr(c, "page_start", 1),
                    "page_end": getattr(c, "page_end", 1),
                    "chunk_index": i,
                }
                for i, c in enumerate(chunks)
            ]

            # When embeddings are provided, only index chunks that actually have
            # a valid vector. Previously missing embeddings were replaced with a
            # zero vector ([0.0]*1536), which poisons the index with a meaningless
            # point and hardcodes the embedding dimension. If NO embeddings are
            # provided at all, we omit them and let Chroma embed the documents.
            if embeddings and len(embeddings) == len(chunks):
                keep = [i for i, emb in enumerate(embeddings) if emb]
                if not keep:
                    logger.warning(f"No valid embeddings for upload '{upload_id}'; skipping upsert.")
                    return False
                ids = [ids[i] for i in keep]
                documents = [documents[i] for i in keep]
                metadatas = [metadatas[i] for i in keep]
                kwargs: Dict[str, Any] = {
                    "ids": ids,
                    "documents": documents,
                    "metadatas": metadatas,
                    "embeddings": [embeddings[i] for i in keep],
                }
            else:
                kwargs = {"ids": ids, "documents": documents, "metadatas": metadatas}

            col.upsert(**kwargs)
            logger.info(f"Successfully upserted {len(kwargs['ids'])} chunks for upload '{upload_id}' into ChromaDB.")
            return True
        except Exception as exc:
            logger.exception(f"Failed to upsert chunks into ChromaDB for upload '{upload_id}': {exc}")
            return False

    def query_similar_chunks(
        self,
        query_text: str = "",
        query_embedding: Optional[List[float]] = None,
        upload_id: Optional[str] = None,
        top_k: int = 8,
    ) -> List[Dict[str, Any]]:
        """Query ChromaDB for top-k semantically relevant document chunks.

        Args:
            query_text: Optional plain text query.
            query_embedding: Optional dense embedding vector for query.
            upload_id: Optional metadata filter to scope query to a specific upload.
            top_k: Max number of results to return.

        Returns:
            List of result dicts: [{"text", "metadata", "distance", "id"}]
        """
        try:
            col = self.get_collection()

            where_clause = {"upload_id": upload_id} if upload_id else None

            query_kwargs: Dict[str, Any] = {
                "n_results": top_k,
                "where": where_clause,
            }

            if query_embedding and len(query_embedding) > 0:
                query_kwargs["query_embeddings"] = [query_embedding]
            elif query_text:
                query_kwargs["query_texts"] = [query_text]
            else:
                logger.warning("Neither query_text nor query_embedding was provided to query_similar_chunks.")
                return []

            res = col.query(**query_kwargs)

            out = []
            if res and res.get("documents") and len(res["documents"]) > 0:
                docs = res["documents"][0]
                metas = res.get("metadatas", [[]])[0]
                dists = res.get("distances", [[]])[0]
                chunk_ids = res.get("ids", [[]])[0]

                for i in range(len(docs)):
                    out.append({
                        "id": chunk_ids[i] if i < len(chunk_ids) else "",
                        "text": docs[i],
                        "metadata": metas[i] if i < len(metas) else {},
                        "distance": dists[i] if i < len(dists) else 0.0,
                    })

            return out
        except Exception as exc:
            logger.exception(f"ChromaDB similarity query failed: {exc}")
            return []

    def get_upload_chunks(self, upload_id: str, limit: int = 30) -> List[Dict[str, Any]]:
        """Fetch stored chunks for an upload without a similarity query.

        Used as a fallback when a scoped similarity query returns nothing but
        the document is indexed — avoids needing a separate on-disk chunk store.
        """
        try:
            col = self.get_collection()
            res = col.get(where={"upload_id": upload_id}, limit=limit)
            docs = res.get("documents") or []
            metas = res.get("metadatas") or []
            return [
                {"text": docs[i], "metadata": metas[i] if i < len(metas) else {}}
                for i in range(len(docs))
            ]
        except Exception as exc:
            logger.warning(f"ChromaDB get_upload_chunks failed for '{upload_id}': {exc}")
            return []

    def delete_upload_chunks(self, upload_id: str) -> bool:
        """Delete all chunks belonging to a specific upload_id."""
        try:
            col = self.get_collection()
            col.delete(where={"upload_id": upload_id})
            logger.info(f"Deleted ChromaDB chunks for upload_id: {upload_id}")
            return True
        except Exception as exc:
            logger.warning(f"Failed to delete ChromaDB chunks for upload_id '{upload_id}': {exc}")
            return False


# Singleton instance helper
_vector_store_instance: Optional[ChromaVectorStore] = None


def get_vector_store() -> ChromaVectorStore:
    """Return the application-wide ChromaVectorStore instance."""
    global _vector_store_instance
    if _vector_store_instance is None:
        _vector_store_instance = ChromaVectorStore()
    return _vector_store_instance
