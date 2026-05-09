"""
api/search.py — Semantic + full-text search over the knowledge graph

Supports:
  - Full-text search (Postgres tsvector)
  - Vector/semantic search (pgvector cosine similarity)
  - Combined hybrid search

FastAPI router: mount with app.include_router(search.router, prefix="/search")
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional
from uuid import UUID

try:
    from fastapi import APIRouter, Depends, HTTPException, Query
    from pydantic import BaseModel
    HAS_FASTAPI = True
except ImportError:
    HAS_FASTAPI = False

# ---- Request / Response models ---------------------------------------------

if HAS_FASTAPI:
    class SearchResult(BaseModel):
        node_id: UUID
        label: str
        adapter: str
        score: float
        node_type: str
        metadata: Dict[str, Any] = {}

    class SearchResponse(BaseModel):
        query: str
        mode: str
        results: List[SearchResult]
        total: int

    # ---- Router ----------------------------------------------------------------

    router = APIRouter(tags=["search"])

    def _get_db():
        """Dependency: yield a database connection."""
        # Replace with your actual connection pool
        import os
        import psycopg2
        import psycopg2.extras
        conn = psycopg2.connect(os.environ["DATABASE_URL"])
        try:
            yield conn
        finally:
            conn.close()

    @router.get("/fulltext", response_model=SearchResponse)
    def fulltext_search(
        q: str = Query(..., description="Full-text query string"),
        limit: int = Query(20, le=100),
        adapter: Optional[str] = Query(None),
        conn=Depends(_get_db),
    ):
        """
        Full-text search using Postgres tsvector.
        Fast, no embeddings required.
        """
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            base_sql = """
                SELECT id, label, adapter, node_type, metadata,
                       ts_rank(to_tsvector('english', label), plainto_tsquery(%s)) AS score
                FROM nodes
                WHERE to_tsvector('english', label) @@ plainto_tsquery(%s)
            """
            params = [q, q]
            if adapter:
                base_sql += " AND adapter = %s"
                params.append(adapter)
            base_sql += " ORDER BY score DESC LIMIT %s"
            params.append(limit)
            cur.execute(base_sql, params)
            rows = cur.fetchall()

        results = [
            SearchResult(
                node_id=row["id"],
                label=row["label"],
                adapter=row["adapter"],
                score=float(row["score"]),
                node_type=row["node_type"],
                metadata=row["metadata"] or {},
            )
            for row in rows
        ]
        return SearchResponse(query=q, mode="fulltext", results=results, total=len(results))

    @router.get("/semantic", response_model=SearchResponse)
    def semantic_search(
        q: str = Query(..., description="Natural language query"),
        limit: int = Query(20, le=100),
        threshold: float = Query(0.75, ge=0.0, le=1.0),
        conn=Depends(_get_db),
    ):
        """
        Vector similarity search using pgvector.
        Requires embeddings to be pre-computed (via build_edges.py).

        NOTE: You must embed the query using the same model as the nodes.
        This endpoint expects the query embedding to be passed as a query param
        or computed here if an embedding function is configured.
        """
        # In production: embed q using the same model as nodes
        # For now, return a helpful error if no embedding service is configured
        raise HTTPException(
            status_code=501,
            detail=(
                "Semantic search requires an embedding service. "
                "Configure EMBEDDING_MODEL env var and restart."
            )
        )

    @router.get("/hybrid", response_model=SearchResponse)
    def hybrid_search(
        q: str = Query(..., description="Query string"),
        limit: int = Query(20, le=100),
        conn=Depends(_get_db),
    ):
        """
        Combines full-text and semantic search results (RRF fusion).
        Falls back to full-text only if embeddings are unavailable.
        """
        # Reciprocal Rank Fusion of both result sets
        ft_results = fulltext_search(q=q, limit=limit * 2, conn=conn)
        # TODO: fuse with semantic results when embedding service is available
        return SearchResponse(
            query=q,
            mode="hybrid_ft_only",
            results=ft_results.results[:limit],
            total=min(ft_results.total, limit),
        )

else:
    # Graceful degradation when FastAPI is not installed
    def search_stub(*args, **kwargs):
        raise ImportError("FastAPI not installed. Run: pip install fastapi uvicorn")

    router = None
