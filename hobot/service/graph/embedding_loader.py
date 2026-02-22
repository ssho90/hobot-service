"""
Neo4j Document 임베딩 적재 로더.

동작:
1) 임베딩 대상 Document 증분 조회
2) Gemini embedding 모델로 벡터 생성
3) Neo4j Document.text_embedding 업데이트
4) Vector Index(document_text_embedding_idx) 보장
"""

from __future__ import annotations

import hashlib
import logging
import os
from typing import Any, Dict, List, Optional, Sequence

from google import genai
from google.genai import types

from .neo4j_client import get_neo4j_client

logger = logging.getLogger(__name__)

DEFAULT_EMBEDDING_MODEL = "gemini-embedding-001"
DEFAULT_EMBEDDING_DIMENSION = 768
DEFAULT_EMBEDDING_BATCH_SIZE = 16
DEFAULT_EMBEDDING_MAX_TEXT_CHARS = 6000
DEFAULT_EMBEDDING_INDEX_NAME = "document_text_embedding_idx"
DEFAULT_RETRY_FAILED_AFTER_MINUTES = 180


def _chunked(values: Sequence[Dict[str, Any]], size: int) -> List[List[Dict[str, Any]]]:
    chunk_size = max(int(size), 1)
    return [list(values[idx : idx + chunk_size]) for idx in range(0, len(values), chunk_size)]


def _sanitize_index_name(index_name: str) -> str:
    text = "".join(ch for ch in str(index_name or "").strip() if ch.isalnum() or ch == "_")
    return text or DEFAULT_EMBEDDING_INDEX_NAME


def _normalize_text(value: Any) -> str:
    return str(value or "").strip()


class DocumentEmbeddingLoader:
    def __init__(
        self,
        neo4j_client=None,
        *,
        model_name: str = DEFAULT_EMBEDDING_MODEL,
        output_dimension: int = DEFAULT_EMBEDDING_DIMENSION,
        batch_size: int = DEFAULT_EMBEDDING_BATCH_SIZE,
        max_text_chars: int = DEFAULT_EMBEDDING_MAX_TEXT_CHARS,
        vector_index_name: str = DEFAULT_EMBEDDING_INDEX_NAME,
    ):
        self.neo4j_client = neo4j_client or get_neo4j_client()
        self.model_name = str(model_name or DEFAULT_EMBEDDING_MODEL).strip() or DEFAULT_EMBEDDING_MODEL
        self.output_dimension = max(int(output_dimension), 1)
        self.batch_size = max(int(batch_size), 1)
        self.max_text_chars = max(int(max_text_chars), 200)
        self.vector_index_name = _sanitize_index_name(vector_index_name)

        api_key = (
            os.getenv("GEMINI_EMBEDDING_API_KEY")
            or os.getenv("GEMINI_API_KEY")
            or os.getenv("GOOGLE_API_KEY")
        )
        if api_key:
            self.client = genai.Client(api_key=api_key)
        else:
            self.client = None

    def ensure_vector_index(self) -> None:
        query = f"""
        CREATE VECTOR INDEX {self.vector_index_name} IF NOT EXISTS
        FOR (d:Document)
        ON (d.text_embedding)
        OPTIONS {{
            indexConfig: {{
                `vector.dimensions`: {int(self.output_dimension)},
                `vector.similarity_function`: 'cosine'
            }}
        }}
        """
        self.neo4j_client.run_write(query)

    def fetch_candidates(
        self,
        *,
        limit: int,
        retry_failed_after_minutes: int = DEFAULT_RETRY_FAILED_AFTER_MINUTES,
    ) -> List[Dict[str, Any]]:
        query = """
        MATCH (d:Document)
        WHERE trim(coalesce(d.text, d.description, d.title, "")) <> ""
          AND (
            d.text_embedding IS NULL
            OR coalesce(d.embedding_status, "") <> "ok"
            OR coalesce(d.embedding_model, "") <> $model_name
            OR coalesce(toInteger(d.embedding_dimension), -1) <> $output_dimension
            OR (d.updated_at IS NOT NULL AND d.embedding_updated_at IS NOT NULL AND d.updated_at > d.embedding_updated_at)
          )
          AND (
            d.embedding_status IS NULL
            OR d.embedding_status <> "failed"
            OR d.embedding_updated_at IS NULL
            OR d.embedding_updated_at <= datetime() - duration({minutes: $retry_failed_after_minutes})
          )
        RETURN
            d.doc_id AS doc_id,
            d.title AS title,
            d.title_ko AS title_ko,
            d.description AS description,
            d.description_ko AS description_ko,
            d.text AS text,
            d.embedding_text_hash AS embedding_text_hash
        ORDER BY coalesce(d.updated_at, d.published_at) DESC
        LIMIT $limit
        """
        rows = self.neo4j_client.run_read(
            query,
            {
                "model_name": self.model_name,
                "output_dimension": int(self.output_dimension),
                "retry_failed_after_minutes": max(int(retry_failed_after_minutes), 0),
                "limit": max(int(limit), 1),
            },
        )
        return [dict(row) for row in rows or []]

    def _compose_document_text(self, row: Dict[str, Any]) -> str:
        title = _normalize_text(row.get("title_ko")) or _normalize_text(row.get("title"))
        body = (
            _normalize_text(row.get("description_ko"))
            or _normalize_text(row.get("description"))
            or _normalize_text(row.get("text"))
        )
        if title and body:
            text = f"{title}\n\n{body}"
        else:
            text = title or body
        if len(text) > self.max_text_chars:
            text = text[: self.max_text_chars]
        return text.strip()

    @staticmethod
    def _text_hash(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def _embed_texts(self, texts: List[str]) -> List[List[float]]:
        if not self.client:
            raise RuntimeError("missing_gemini_embedding_api_key")
        response = self.client.models.embed_content(
            model=self.model_name,
            contents=texts,
            config=types.EmbedContentConfig(
                task_type="RETRIEVAL_DOCUMENT",
                output_dimensionality=self.output_dimension,
            ),
        )
        embeddings = list(response.embeddings or [])
        vectors: List[List[float]] = [list(item.values or []) for item in embeddings]
        if len(vectors) != len(texts):
            raise RuntimeError(
                f"embedding_count_mismatch expected={len(texts)} actual={len(vectors)}"
            )
        for idx, vector in enumerate(vectors):
            if len(vector) != self.output_dimension:
                raise RuntimeError(
                    f"embedding_dimension_mismatch index={idx} expected={self.output_dimension} actual={len(vector)}"
                )
        return vectors

    def _upsert_embeddings(self, rows: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not rows:
            return {"properties_set": 0}
        query = """
        UNWIND $rows AS row
        MATCH (d:Document {doc_id: row.doc_id})
        SET d.text_embedding = row.embedding,
            d.embedding_model = $model_name,
            d.embedding_dimension = $output_dimension,
            d.embedding_status = "ok",
            d.embedding_error = NULL,
            d.embedding_text_hash = row.embedding_text_hash,
            d.embedding_updated_at = datetime()
        """
        return self.neo4j_client.run_write(
            query,
            {
                "rows": rows,
                "model_name": self.model_name,
                "output_dimension": int(self.output_dimension),
            },
        )

    def _mark_failed_docs(self, doc_ids: List[str], error_message: str):
        if not doc_ids:
            return
        query = """
        UNWIND $doc_ids AS doc_id
        MATCH (d:Document {doc_id: doc_id})
        SET d.embedding_status = "failed",
            d.embedding_error = $error_message,
            d.embedding_updated_at = datetime()
        """
        self.neo4j_client.run_write(
            query,
            {
                "doc_ids": doc_ids,
                "error_message": str(error_message or "")[:500],
            },
        )

    def sync_incremental(
        self,
        *,
        limit: int = 800,
        retry_failed_after_minutes: int = DEFAULT_RETRY_FAILED_AFTER_MINUTES,
    ) -> Dict[str, Any]:
        if not self.client:
            return {
                "status": "skipped",
                "reason": "missing_gemini_embedding_api_key",
                "model_name": self.model_name,
                "output_dimension": int(self.output_dimension),
            }

        self.ensure_vector_index()
        candidates = self.fetch_candidates(
            limit=limit,
            retry_failed_after_minutes=retry_failed_after_minutes,
        )
        if not candidates:
            return {
                "status": "no_data",
                "model_name": self.model_name,
                "output_dimension": int(self.output_dimension),
                "candidate_docs": 0,
                "embedded_docs": 0,
                "failed_docs": 0,
                "skipped_docs": 0,
            }

        prepared: List[Dict[str, Any]] = []
        skipped_docs = 0
        for row in candidates:
            doc_id = _normalize_text(row.get("doc_id"))
            if not doc_id:
                skipped_docs += 1
                continue
            text = self._compose_document_text(row)
            if not text:
                skipped_docs += 1
                continue
            text_hash = self._text_hash(text)
            if text_hash == _normalize_text(row.get("embedding_text_hash")):
                skipped_docs += 1
                continue
            prepared.append(
                {
                    "doc_id": doc_id,
                    "text": text,
                    "embedding_text_hash": text_hash,
                }
            )

        if not prepared:
            return {
                "status": "no_data",
                "model_name": self.model_name,
                "output_dimension": int(self.output_dimension),
                "candidate_docs": len(candidates),
                "embedded_docs": 0,
                "failed_docs": 0,
                "skipped_docs": skipped_docs,
            }

        embedded_docs = 0
        failed_docs = 0
        failed_doc_ids: List[str] = []
        for batch in _chunked(prepared, self.batch_size):
            texts = [item["text"] for item in batch]
            try:
                vectors = self._embed_texts(texts)
                rows = [
                    {
                        "doc_id": item["doc_id"],
                        "embedding_text_hash": item["embedding_text_hash"],
                        "embedding": vectors[idx],
                    }
                    for idx, item in enumerate(batch)
                ]
                self._upsert_embeddings(rows)
                embedded_docs += len(rows)
            except Exception as batch_exc:
                logger.warning(
                    "[DocumentEmbeddingLoader] batch embedding failed(size=%s): %s",
                    len(batch),
                    batch_exc,
                )
                for item in batch:
                    try:
                        vector = self._embed_texts([item["text"]])[0]
                        self._upsert_embeddings(
                            [
                                {
                                    "doc_id": item["doc_id"],
                                    "embedding_text_hash": item["embedding_text_hash"],
                                    "embedding": vector,
                                }
                            ]
                        )
                        embedded_docs += 1
                    except Exception as doc_exc:
                        failed_docs += 1
                        failed_doc_ids.append(item["doc_id"])
                        self._mark_failed_docs([item["doc_id"]], str(doc_exc))

        status = "success" if failed_docs == 0 else ("partial_success" if embedded_docs > 0 else "failed")
        return {
            "status": status,
            "model_name": self.model_name,
            "output_dimension": int(self.output_dimension),
            "vector_index_name": self.vector_index_name,
            "candidate_docs": len(candidates),
            "prepared_docs": len(prepared),
            "embedded_docs": embedded_docs,
            "failed_docs": failed_docs,
            "failed_doc_ids": failed_doc_ids[:200],
            "skipped_docs": skipped_docs,
        }


_embedding_loader_singleton: Optional[DocumentEmbeddingLoader] = None


def get_document_embedding_loader() -> DocumentEmbeddingLoader:
    global _embedding_loader_singleton
    if _embedding_loader_singleton is None:
        model_name = os.getenv("GRAPH_NEWS_EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL)
        output_dimension = int(
            os.getenv("GRAPH_NEWS_EMBEDDING_DIMENSION", str(DEFAULT_EMBEDDING_DIMENSION))
        )
        batch_size = int(
            os.getenv("GRAPH_NEWS_EMBEDDING_BATCH_SIZE", str(DEFAULT_EMBEDDING_BATCH_SIZE))
        )
        max_text_chars = int(
            os.getenv("GRAPH_NEWS_EMBEDDING_MAX_TEXT_CHARS", str(DEFAULT_EMBEDDING_MAX_TEXT_CHARS))
        )
        vector_index_name = os.getenv(
            "GRAPH_NEWS_EMBEDDING_INDEX_NAME",
            DEFAULT_EMBEDDING_INDEX_NAME,
        )
        _embedding_loader_singleton = DocumentEmbeddingLoader(
            model_name=model_name,
            output_dimension=output_dimension,
            batch_size=batch_size,
            max_text_chars=max_text_chars,
            vector_index_name=vector_index_name,
        )
    return _embedding_loader_singleton


def sync_document_embeddings(
    *,
    limit: int = 800,
    retry_failed_after_minutes: int = DEFAULT_RETRY_FAILED_AFTER_MINUTES,
) -> Dict[str, Any]:
    loader = get_document_embedding_loader()
    return loader.sync_incremental(
        limit=limit,
        retry_failed_after_minutes=retry_failed_after_minutes,
    )
