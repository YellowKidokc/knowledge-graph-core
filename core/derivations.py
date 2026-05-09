"""
derivations.py — Engine for deriving graph edges from observations

This is the soul of the system: deterministic, auditable rules that
explain WHY each edge exists. No mystical vector fog.
Answers question 3: "What graph relationships did we derive?"
And question 4: "Why does this edge exist?"
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from .canonical_model import (
    CanonicalEdge, CanonicalNode, DerivationChain,
    DerivationStrategy, EdgeType,
)
from .observations import Observation, ObservationType


# ---------------------------------------------------------------------------
# Base class
# ---------------------------------------------------------------------------

class BaseDerivationRule(ABC):
    """
    A derivation rule takes a set of observations and produces edges.

    Each rule is a named, versioned, auditable unit.  When an edge is
    created by a rule, it records the rule name and the matched evidence
    so the system can always answer "why does this edge exist?"
    """

    name: str = "base"
    version: str = "1.0.0"
    produces: EdgeType = EdgeType.MENTIONS

    @abstractmethod
    def apply(
        self,
        source_node: CanonicalNode,
        nodes_by_label: Dict[str, CanonicalNode],
        observations: List[Observation],
    ) -> List[CanonicalEdge]:
        ...

    def _make_edge(
        self,
        source: CanonicalNode,
        target: CanonicalNode,
        evidence: Dict[str, Any],
        confidence: float = 1.0,
        strategy: DerivationStrategy = DerivationStrategy.RULE_BASED,
    ) -> CanonicalEdge:
        chain = DerivationChain(
            strategy=strategy,
            confidence=confidence,
            evidence=evidence,
            derived_by=f"{self.name}@{self.version}",
        )
        return CanonicalEdge(
            source_id=source.id,
            target_id=target.id,
            edge_type=self.produces,
            derivation_chain=[chain],
        )


# ---------------------------------------------------------------------------
# Concrete rules
# ---------------------------------------------------------------------------

class WikilinkDerivationRule(BaseDerivationRule):
    """
    Derives CITES edges from [[wikilink]] observations.
    If note A contains [[B]], emit A -> CITES -> B.
    """
    name = "wikilink_rule"
    produces = EdgeType.CITES

    def apply(self, source_node, nodes_by_label, observations):
        edges = []
        for obs in observations:
            if obs.observation_type != ObservationType.WIKILINK:
                continue
            target = nodes_by_label.get(obs.normalized_value)
            if target is None:
                continue
            edges.append(self._make_edge(
                source=source_node,
                target=target,
                evidence={"link_text": obs.value, "position": obs.position},
                confidence=1.0,
                strategy=DerivationStrategy.EXPLICIT_LINK,
            ))
        return edges


class TagCoMembershipRule(BaseDerivationRule):
    """
    Derives CO_OCCURS edges between nodes that share a tag.
    If A has #tag and B has #tag, emit A <-> CO_OCCURS <-> B.
    """
    name = "tag_co_membership_rule"
    produces = EdgeType.CO_OCCURS

    def apply(self, source_node, nodes_by_label, observations):
        # This rule is typically run across ALL nodes, not per-node.
        # The graph_builders.py coordinates multi-node rules.
        return []

    def apply_global(
        self,
        nodes: List[CanonicalNode],
        obs_by_node: Dict[UUID, List[Observation]],
    ) -> List[CanonicalEdge]:
        from collections import defaultdict
        tag_to_nodes: Dict[str, List[CanonicalNode]] = defaultdict(list)
        for node in nodes:
            for obs in obs_by_node.get(node.id, []):
                if obs.observation_type == ObservationType.TAG:
                    tag_to_nodes[obs.normalized_value].append(node)

        edges = []
        for tag, tagged_nodes in tag_to_nodes.items():
            for i, a in enumerate(tagged_nodes):
                for b in tagged_nodes[i + 1:]:
                    chain = DerivationChain(
                        strategy=DerivationStrategy.RULE_BASED,
                        confidence=0.8,
                        evidence={"shared_tag": tag},
                        derived_by=f"{self.name}@{self.version}",
                    )
                    edges.append(CanonicalEdge(
                        source_id=a.id,
                        target_id=b.id,
                        edge_type=EdgeType.CO_OCCURS,
                        derivation_chain=[chain],
                    ))
        return edges


class VectorSimilarityRule(BaseDerivationRule):
    """
    Derives SIMILAR_TO edges from cosine similarity above a threshold.
    Records the similarity score and model name in the derivation chain.
    """
    name = "vector_similarity_rule"
    produces = EdgeType.SIMILAR_TO

    def __init__(self, threshold: float = 0.82, model: str = "text-embedding-3-small"):
        self.threshold = threshold
        self.model = model

    def apply(self, source_node, nodes_by_label, observations):
        return []

    def apply_with_scores(
        self,
        source: CanonicalNode,
        candidates: List[Tuple[CanonicalNode, float]],
    ) -> List[CanonicalEdge]:
        edges = []
        for target, score in candidates:
            if score < self.threshold:
                continue
            chain = DerivationChain(
                strategy=DerivationStrategy.VECTOR_SIMILARITY,
                confidence=round(score, 4),
                evidence={"similarity_score": score, "model": self.model, "threshold": self.threshold},
                derived_by=f"{self.name}@{self.version}",
            )
            edges.append(CanonicalEdge(
                source_id=source.id,
                target_id=target.id,
                edge_type=EdgeType.SIMILAR_TO,
                derivation_chain=[chain],
            ))
        return edges


# ---------------------------------------------------------------------------
# Rule registry
# ---------------------------------------------------------------------------

BUILTIN_RULES: List[BaseDerivationRule] = [
    WikilinkDerivationRule(),
    TagCoMembershipRule(),
    VectorSimilarityRule(),
]
