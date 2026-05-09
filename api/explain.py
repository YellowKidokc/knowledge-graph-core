"""
api/explain.py — The soul of the system: "Why does this edge exist?"

This endpoint answers the fourth core question with a full breadcrumb
trail instead of mystical vector fog.

FastAPI router: mount with app.include_router(explain.router, prefix="/explain")
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

    class DerivationStep(BaseModel):
        step: int
        strategy: str
        confidence: float
        evidence: Dict[str, Any]
        derived_by: str
        derived_at: str

    class EdgeExplanation(BaseModel):
        edge_id: UUID
        source_label: str
        source_adapter: str
        edge_type: str
        target_label: str
        target_adapter: str
        derivation_chain: List[DerivationStep]
        human_readable: str  # plain-English summary

    class NodeExplanations(BaseModel):
        node_id: UUID
        label: str
        outgoing_edge_explanations: List[EdgeExplanation]
        incoming_edge_explanations: List[EdgeExplanation]

    router = APIRouter(tags=["explain"])

    def _get_db():
        conn = psycopg2.connect(os.environ["DATABASE_URL"])
        try:
            yield conn
        finally:
            conn.close()

    def _build_human_readable(edge_type: str, source: str, target: str, chain: List[Dict]) -> str:
        """Generate a plain-English explanation of why an edge exists."""
        if not chain:
            return f'"{source}" {edge_type} "{target}" — no derivation recorded.'

        step = chain[0]
        strategy = step.get("strategy", "unknown")
        evidence = step.get("evidence", {})
        confidence = step.get("confidence", 0.0)
        derived_by = step.get("derived_by", "system")

        templates = {
            "explicit_link": (
                f'"{source}" explicitly links to "{target}" '
                f'via {evidence.get("link_text", "a direct link")} '
                f'(found at position {evidence.get("position", "unknown")}).'
            ),
            "vector_similarity": (
                f'"{source}" and "{target}" are semantically similar '
                f'(cosine score={evidence.get("similarity_score", confidence):.3f}, '
                f'model={evidence.get("model", "unknown")}, '
                f'threshold={evidence.get("threshold", "unknown")}). '
                f'Derived by {derived_by}.'
            ),
            "rule_based": (
                f'"{source}" {edge_type} "{target}" because a rule fired: '
                f'{evidence}. Derived by {derived_by}.'
            ),
            "co_occurrence": (
                f'"{source}" and "{target}" co-occur in the same context '
                f'(shared: {evidence}). Confidence: {confidence:.2f}.'
            ),
            "human_asserted": (
                f'A human manually asserted that "{source}" {edge_type} "{target}".'
            ),
        }
        return templates.get(strategy, f'Strategy: {strategy}. Evidence: {evidence}')

    @router.get("/edge/{edge_id}", response_model=EdgeExplanation)
    def explain_edge(
        edge_id: UUID = Path(..., description="Edge UUID"),
        conn=Depends(_get_db),
    ):
        """
        Answers Q4: "Why does this edge exist?"

        Returns a full derivation chain with step-by-step evidence
        and a human-readable summary.  No mystical vector fog.
        """
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute("""
                SELECT * FROM edge_explanations WHERE edge_id = %s
            """, (str(edge_id),))
            row = cur.fetchone()

        if not row:
            raise HTTPException(status_code=404, detail=f"Edge {edge_id} not found")

        chain_raw = row["derivation_chain"] or []
        chain = [
            DerivationStep(
                step=s["step"],
                strategy=s["strategy"],
                confidence=float(s["confidence"]),
                evidence=s["evidence"],
                derived_by=s["derived_by"],
                derived_at=str(s["derived_at"]),
            )
            for s in chain_raw
        ]

        return EdgeExplanation(
            edge_id=row["edge_id"],
            source_label=row["source_label"],
            source_adapter=row["source_adapter"],
            edge_type=row["edge_type"],
            target_label=row["target_label"],
            target_adapter=row["target_adapter"],
            derivation_chain=chain,
            human_readable=_build_human_readable(
                row["edge_type"],
                row["source_label"],
                row["target_label"],
                chain_raw,
            ),
        )

    @router.get("/node/{node_id}", response_model=NodeExplanations)
    def explain_node(
        node_id: UUID = Path(...),
        limit: int = Query(20, le=100),
        conn=Depends(_get_db),
    ):
        """
        Return all edge explanations for a given node (both directions).
        Answers: "Why is this node connected to everything it's connected to?"
        """
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute("SELECT label FROM nodes WHERE id = %s", (str(node_id),))
            node_row = cur.fetchone()
            if not node_row:
                raise HTTPException(status_code=404, detail=f"Node {node_id} not found")

            cur.execute("""
                SELECT * FROM edge_explanations
                WHERE edge_id IN (
                    SELECT id FROM edges WHERE source_id = %s OR target_id = %s
                )
                LIMIT %s
            """, (str(node_id), str(node_id), limit))
            rows = cur.fetchall()

        outgoing = []
        incoming = []
        for row in rows:
            chain_raw = row["derivation_chain"] or []
            chain = [
                DerivationStep(
                    step=s["step"],
                    strategy=s["strategy"],
                    confidence=float(s["confidence"]),
                    evidence=s["evidence"],
                    derived_by=s["derived_by"],
                    derived_at=str(s["derived_at"]),
                )
                for s in chain_raw
            ]
            explanation = EdgeExplanation(
                edge_id=row["edge_id"],
                source_label=row["source_label"],
                source_adapter=row["source_adapter"],
                edge_type=row["edge_type"],
                target_label=row["target_label"],
                target_adapter=row["target_adapter"],
                derivation_chain=chain,
                human_readable=_build_human_readable(
                    row["edge_type"],
                    row["source_label"],
                    row["target_label"],
                    chain_raw,
                ),
            )
            if str(row["edge_id"]) in [str(e.edge_id) for e in outgoing + incoming]:
                continue
            # Determine direction
            if row["source_label"] == node_row["label"]:
                outgoing.append(explanation)
            else:
                incoming.append(explanation)

        return NodeExplanations(
            node_id=node_id,
            label=node_row["label"],
            outgoing_edge_explanations=outgoing,
            incoming_edge_explanations=incoming,
        )

else:
    router = None
