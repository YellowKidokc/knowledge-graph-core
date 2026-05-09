"""
api/graph.py — Graph traversal and neighborhood endpoints

Provides access to the graph structure: neighbors, paths,
hub detection, and orphan analysis.

FastAPI router: mount with app.include_router(graph.router, prefix="/graph")
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional
from uuid import UUID

try:
    from fastapi import APIRouter, Depends, HTTPException, Path, Query
    from pydantic import BaseModel
    HAS_FASTAPI = True
except ImportError:
    HAS_FASTAPI = False


if HAS_FASTAPI:
    import os
    import psycopg2
    import psycopg2.extras

    class NodeSummary(BaseModel):
        node_id: UUID
        label: str
        adapter: str
        node_type: str

    class EdgeSummary(BaseModel):
        edge_id: UUID
        source_id: UUID
        target_id: UUID
        edge_type: str
        weight: float

    class NeighborhoodResponse(BaseModel):
        center: NodeSummary
        neighbors: List[NodeSummary]
        edges: List[EdgeSummary]
        depth: int

    class GraphStatsResponse(BaseModel):
        total_nodes: int
        total_edges: int
        edges_by_type: Dict[str, int]
        top_hubs: List[Dict[str, Any]]
        orphan_count: int

    router = APIRouter(tags=["graph"])

    def _get_db():
        conn = psycopg2.connect(os.environ["DATABASE_URL"])
        try:
            yield conn
        finally:
            conn.close()

    @router.get("/node/{node_id}/neighbors", response_model=NeighborhoodResponse)
    def get_neighbors(
        node_id: UUID = Path(...),
        depth: int = Query(1, ge=1, le=3),
        edge_type: Optional[str] = Query(None),
        conn=Depends(_get_db),
    ):
        """
        Return the immediate neighborhood of a node up to 'depth' hops.
        """
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            # Fetch center node
            cur.execute("SELECT * FROM nodes WHERE id = %s", (str(node_id),))
            center_row = cur.fetchone()
            if not center_row:
                raise HTTPException(status_code=404, detail=f"Node {node_id} not found")

            # Fetch direct edges (depth=1 for now; recursive CTE for deeper)
            edge_filter = ""
            params: List[Any] = [str(node_id)]
            if edge_type:
                edge_filter = " AND e.edge_type = %s"
                params.append(edge_type)

            cur.execute(f"""
                SELECT e.id, e.source_id, e.target_id, e.edge_type, e.weight,
                       n.id AS n_id, n.label, n.adapter, n.node_type
                FROM edges e
                JOIN nodes n ON n.id = CASE
                    WHEN e.source_id = %s THEN e.target_id
                    ELSE e.source_id
                END
                WHERE (e.source_id = %s OR e.target_id = %s){edge_filter}
                LIMIT 100
            """, [str(node_id), str(node_id), str(node_id)] + params[1:])
            rows = cur.fetchall()

        center = NodeSummary(
            node_id=center_row["id"],
            label=center_row["label"],
            adapter=center_row["adapter"],
            node_type=center_row["node_type"],
        )
        neighbors = []
        edges = []
        for row in rows:
            neighbors.append(NodeSummary(
                node_id=row["n_id"],
                label=row["label"],
                adapter=row["adapter"],
                node_type=row["node_type"],
            ))
            edges.append(EdgeSummary(
                edge_id=row["id"],
                source_id=row["source_id"],
                target_id=row["target_id"],
                edge_type=row["edge_type"],
                weight=float(row["weight"]),
            ))

        return NeighborhoodResponse(
            center=center,
            neighbors=neighbors,
            edges=edges,
            depth=depth,
        )

    @router.get("/stats", response_model=GraphStatsResponse)
    def get_graph_stats(conn=Depends(_get_db)):
        """
        Return global graph statistics: node/edge counts, hubs, orphans.
        """
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute("SELECT COUNT(*) AS n FROM nodes")
            total_nodes = cur.fetchone()["n"]

            cur.execute("SELECT COUNT(*) AS n FROM edges")
            total_edges = cur.fetchone()["n"]

            cur.execute("""
                SELECT edge_type, COUNT(*) AS n
                FROM edges GROUP BY edge_type ORDER BY n DESC
            """)
            edges_by_type = {row["edge_type"]: row["n"] for row in cur.fetchall()}

            # Hubs: nodes with the most edges
            cur.execute("""
                SELECT n.id, n.label, n.adapter, COUNT(e.id) AS degree
                FROM nodes n
                LEFT JOIN edges e ON e.source_id = n.id OR e.target_id = n.id
                GROUP BY n.id, n.label, n.adapter
                ORDER BY degree DESC
                LIMIT 10
            """)
            top_hubs = [dict(row) for row in cur.fetchall()]

            # Orphans: nodes with no edges
            cur.execute("""
                SELECT COUNT(*) AS n FROM nodes
                WHERE id NOT IN (
                    SELECT DISTINCT source_id FROM edges
                    UNION
                    SELECT DISTINCT target_id FROM edges
                )
            """)
            orphan_count = cur.fetchone()["n"]

        return GraphStatsResponse(
            total_nodes=total_nodes,
            total_edges=total_edges,
            edges_by_type=edges_by_type,
            top_hubs=top_hubs,
            orphan_count=orphan_count,
        )

    @router.get("/ingest", summary="What did we ingest?")
    def get_ingest_records(
        limit: int = Query(50, le=200),
        adapter: Optional[str] = Query(None),
        conn=Depends(_get_db),
    ):
        """
        Answers Q1: "What did we ingest?"
        Returns the history of ingest runs.
        """
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            sql = "SELECT * FROM ingest_records"
            params = []
            if adapter:
                sql += " WHERE adapter = %s"
                params.append(adapter)
            sql += " ORDER BY ingested_at DESC LIMIT %s"
            params.append(limit)
            cur.execute(sql, params)
            return [dict(row) for row in cur.fetchall()]

else:
    router = None
