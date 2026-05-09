"""
workers/build_edges.py — Derives graph edges from stored observations

Loads nodes and observations from Postgres, runs all derivation rules,
and writes the resulting edges + derivation_steps back to Postgres.

Usage:
    python -m workers.build_edges --adapter obsidian
    python -m workers.build_edges --all
"""

from __future__ import annotations
import argparse
import json
import os
import sys
from typing import Any, Dict, List, Optional
from uuid import UUID

# Optional: use psycopg2 or asyncpg in production
try:
    import psycopg2
    import psycopg2.extras
    HAS_PSYCOPG2 = True
except ImportError:
    HAS_PSYCOPG2 = False

from core.canonical_model import (
    CanonicalEdge, CanonicalNode, DerivationChain, NodeType
)
from core.derivations import BUILTIN_RULES
from core.graph_builders import GraphBuilder
from core.observations import Observation, ObservationBatch, ObservationType


# ---- Database helpers ------------------------------------------------------

def _get_connection(dsn: Optional[str] = None):
    """Return a psycopg2 connection. DSN defaults to DATABASE_URL env var."""
    if not HAS_PSYCOPG2:
        raise RuntimeError(
            "psycopg2 not installed. Run: pip install psycopg2-binary"
        )
    dsn = dsn or os.environ.get("DATABASE_URL")
    if not dsn:
        raise RuntimeError("Set DATABASE_URL or pass --dsn")
    return psycopg2.connect(dsn)


def _load_nodes(conn, adapter: Optional[str] = None) -> List[CanonicalNode]:
    """Load nodes from Postgres, optionally filtered by adapter."""
    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        if adapter:
            cur.execute("SELECT * FROM nodes WHERE adapter = %s", (adapter,))
        else:
            cur.execute("SELECT * FROM nodes")
        rows = cur.fetchall()

    nodes = []
    for row in rows:
        node = CanonicalNode(
            id=UUID(str(row["id"])),
            node_type=NodeType(row["node_type"]),
            label=row["label"],
            adapter=row["adapter"],
            source_id=row["source_id"],
            content_hash=row["content_hash"],
            metadata=row["metadata"] or {},
        )
        nodes.append(node)
    return nodes


def _load_observations(conn, node_ids: List[UUID]) -> Dict[UUID, List[Observation]]:
    """Load observations for a set of nodes."""
    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute(
            "SELECT * FROM observations WHERE source_node_id = ANY(%s)",
            ([str(nid) for nid in node_ids],)
        )
        rows = cur.fetchall()

    obs_by_node: Dict[UUID, List[Observation]] = {}
    for row in rows:
        nid = UUID(str(row["source_node_id"]))
        obs = Observation(
            id=UUID(str(row["id"])),
            source_node_id=nid,
            observation_type=ObservationType(row["obs_type"]),
            value=row["value"],
            normalized_value=row["normalized_value"],
            position=row["position"],
            extractor=row["extractor"],
            confidence=float(row["confidence"]),
            metadata=row["metadata"] or {},
        )
        obs_by_node.setdefault(nid, []).append(obs)
    return obs_by_node


def _write_edges(conn, edges: List[CanonicalEdge]) -> int:
    """Insert edges and their derivation steps into Postgres."""
    written = 0
    with conn.cursor() as cur:
        for edge in edges:
            cur.execute(
                """
                INSERT INTO edges (id, source_id, target_id, edge_type, weight, metadata)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT DO NOTHING
                """,
                (
                    str(edge.id),
                    str(edge.source_id),
                    str(edge.target_id),
                    edge.edge_type.value,
                    edge.weight,
                    json.dumps(edge.metadata),
                )
            )
            for step_order, step in enumerate(edge.derivation_chain):
                cur.execute(
                    """
                    INSERT INTO derivation_steps
                        (edge_id, step_order, strategy, confidence, evidence, derived_by)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (
                        str(edge.id),
                        step_order,
                        step.strategy.value,
                        step.confidence,
                        json.dumps(step.evidence),
                        step.derived_by,
                    )
                )
            written += 1
    conn.commit()
    return written


# ---- Main build pipeline ---------------------------------------------------

def build_edges(
    adapter: Optional[str] = None,
    dsn: Optional[str] = None,
    dry_run: bool = False,
) -> None:
    """
    Full pipeline: load -> observe -> derive -> write.
    This is the worker that populates the graph from raw observations.
    """
    conn = _get_connection(dsn)

    print(f"Loading nodes{'for adapter=' + adapter if adapter else ''}...")
    nodes = _load_nodes(conn, adapter=adapter)
    print(f"  {len(nodes)} nodes loaded")

    node_ids = [n.id for n in nodes]
    obs_by_node = _load_observations(conn, node_ids)
    total_obs = sum(len(v) for v in obs_by_node.values())
    print(f"  {total_obs} observations loaded")

    builder = GraphBuilder(rules=BUILTIN_RULES)
    builder.add_nodes(nodes)
    for node_id, obs_list in obs_by_node.items():
        batch = ObservationBatch(source_node_id=node_id, observations=obs_list)
        builder.add_observation_batch(batch)

    print("Running derivation rules...")
    edges = builder.build()
    print(f"  {len(edges)} edges derived")
    print(f"  {json.dumps(builder._count_edges_by_type(), indent=2)}")

    if dry_run:
        print("[DRY RUN] Not writing to database.")
        for edge in edges[:5]:
            print(f"  {edge.edge_type.value}: {edge.source_id} -> {edge.target_id}")
            print(f"    {edge.explain()}")
        return

    written = _write_edges(conn, edges)
    print(f"Wrote {written} edges to Postgres.")
    conn.close()


# ---- CLI -------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Build graph edges from observations")
    parser.add_argument("--adapter", help="Filter by adapter (e.g. 'obsidian')")
    parser.add_argument("--all", action="store_true", help="Process all adapters")
    parser.add_argument("--dsn", help="Postgres DSN (default: $DATABASE_URL)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not args.adapter and not args.all:
        parser.error("Specify --adapter ADAPTER or --all")

    build_edges(
        adapter=args.adapter if not args.all else None,
        dsn=args.dsn,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
