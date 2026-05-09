"""
graph_builders.py — Orchestrates observation extraction and edge derivation

Coordinates all adapters, rules, and observations to build the full
knowledge graph. This is the "assembly line" that turns raw content
into a navigable, explainable graph.
"""

from __future__ import annotations
from typing import Dict, List, Optional
from uuid import UUID

from .canonical_model import CanonicalEdge, CanonicalNode, IngestRecord
from .derivations import BUILTIN_RULES, BaseDerivationRule, VectorSimilarityRule
from .observations import Observation, ObservationBatch, ObservationStore


class GraphBuilder:
    """
    Orchestrates the full pipeline:
      1. Accept ingested nodes + observation batches
      2. Index nodes by label for fast lookup
      3. Run all derivation rules
      4. Return a list of edges with full derivation chains

    This answers all four core questions:
      Q1: "What did we ingest?"      -> ingest_records
      Q2: "What did we observe?"     -> observation_store
      Q3: "What edges were derived?" -> derived_edges
      Q4: "Why does this edge exist?" -> edge.explain()
    """

    def __init__(
        self,
        rules: Optional[List[BaseDerivationRule]] = None,
        vector_threshold: float = 0.82,
    ):
        self.rules = rules if rules is not None else BUILTIN_RULES
        self.vector_threshold = vector_threshold

        self._nodes: List[CanonicalNode] = []
        self._nodes_by_id: Dict[UUID, CanonicalNode] = {}
        self._nodes_by_label: Dict[str, CanonicalNode] = {}
        self._obs_store = ObservationStore()
        self._ingest_records: List[IngestRecord] = []
        self._edges: List[CanonicalEdge] = []

    # ------------------------------------------------------------------
    # Ingestion
    # ------------------------------------------------------------------

    def add_node(self, node: CanonicalNode) -> None:
        self._nodes.append(node)
        self._nodes_by_id[node.id] = node
        self._nodes_by_label[node.label.lower()] = node

    def add_nodes(self, nodes: List[CanonicalNode]) -> None:
        for node in nodes:
            self.add_node(node)

    def add_observation_batch(self, batch: ObservationBatch) -> None:
        self._obs_store.add_batch(batch)

    def add_ingest_record(self, record: IngestRecord) -> None:
        self._ingest_records.append(record)

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def build(self) -> List[CanonicalEdge]:
        """
        Run all derivation rules and return the full edge list.
        Each edge carries a DerivationChain that explains its existence.
        """
        self._edges = []

        obs_by_node: Dict[UUID, List[Observation]] = {}
        for obs in self._obs_store.all_observations():
            obs_by_node.setdefault(obs.source_node_id, []).append(obs)

        for node in self._nodes:
            node_obs = obs_by_node.get(node.id, [])
            for rule in self.rules:
                # Skip global-only rules
                if hasattr(rule, 'apply_global'):
                    continue
                new_edges = rule.apply(
                    source_node=node,
                    nodes_by_label=self._nodes_by_label,
                    observations=node_obs,
                )
                self._edges.extend(new_edges)

        # Run global rules (e.g. tag co-membership)
        for rule in self.rules:
            if hasattr(rule, 'apply_global'):
                global_edges = rule.apply_global(
                    nodes=self._nodes,
                    obs_by_node=obs_by_node,
                )
                self._edges.extend(global_edges)

        return self._edges

    def build_vector_edges(
        self,
        similarity_matrix: Dict[UUID, List[tuple]],
    ) -> List[CanonicalEdge]:
        """
        Build SIMILAR_TO edges from a pre-computed similarity matrix.
        Expects: { node_id: [(candidate_node, score), ...] }
        """
        vec_rule = next(
            (r for r in self.rules if isinstance(r, VectorSimilarityRule)),
            VectorSimilarityRule(threshold=self.vector_threshold),
        )
        new_edges = []
        for node_id, candidates in similarity_matrix.items():
            source = self._nodes_by_id.get(node_id)
            if source is None:
                continue
            candidate_nodes = [
                (self._nodes_by_id[cid], score)
                for cid, score in candidates
                if cid in self._nodes_by_id
            ]
            new_edges.extend(vec_rule.apply_with_scores(source, candidate_nodes))
        self._edges.extend(new_edges)
        return new_edges

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def summary(self) -> dict:
        """Return a summary suitable for logging or the /graph endpoint."""
        return {
            "nodes": len(self._nodes),
            "observations": self._obs_store.total_count(),
            "edges": len(self._edges),
            "ingest_records": len(self._ingest_records),
            "edges_by_type": self._count_edges_by_type(),
        }

    def _count_edges_by_type(self) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for edge in self._edges:
            k = edge.edge_type.value
            counts[k] = counts.get(k, 0) + 1
        return counts

    def explain_edge(self, edge_id: UUID) -> Optional[str]:
        """Return the derivation explanation for a specific edge."""
        for edge in self._edges:
            if edge.id == edge_id:
                return edge.explain()
        return None
