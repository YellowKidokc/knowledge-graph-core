"""
canonical_model.py — Core data structures for knowledge-graph-core

Every node and edge in this system is typed, timestamped, and traceable.
No mystical vector fog: every relationship carries a derivation chain
that answers the question "why does this edge exist?"
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4


class NodeType(str, Enum):
      """Canonical node types across all adapters."""
      DOCUMENT = "document"
      CONCEPT = "concept"
      ENTITY = "entity"
      OBSERVATION = "observation"
      CLAIM = "claim"
      QUESTION = "question"


class EdgeType(str, Enum):
      """Canonical edge types — each maps to a derivation strategy."""
      MENTIONS = "mentions"           # document mentions entity/concept
    SIMILAR_TO = "similar_to"       # vector similarity above threshold
    CITES = "cites"                 # explicit citation/wikilink
    DERIVED_FROM = "derived_from"   # observation derived from source
    CONTRADICTS = "contradicts"     # claim opposes another claim
    SUPPORTS = "supports"           # claim supports another claim
    CO_OCCURS = "co_occurs"         # appear together in a sliding window
    PARENT_OF = "parent_of"         # hierarchical / folder structure
    TAGGED_WITH = "tagged_with"     # tag or category membership


class DerivationStrategy(str, Enum):
      """How an edge was computed — the soul of the system."""
      EXPLICIT_LINK = "explicit_link"         # [[wikilink]] or href
    VECTOR_SIMILARITY = "vector_similarity" # cosine sim > threshold
    CO_OCCURRENCE = "co_occurrence"         # shared window in text
    NLP_EXTRACTION = "nlp_extraction"       # NER / relation extraction
    RULE_BASED = "rule_based"               # deterministic rule fired
    HUMAN_ASSERTED = "human_asserted"       # user manually created
    IMPORTED = "imported"                   # brought in from external source


@dataclass
class CanonicalNode:
      """
          A node in the knowledge graph.

              source_id: the original identifier in the adapter (e.g. Obsidian note path,
                             HTML URL, Postgres row PK).
                                 adapter:   which adapter ingested this node (obsidian, html, postgres, etc.)
                                     """
      id: UUID = field(default_factory=uuid4)
      node_type: NodeType = NodeType.DOCUMENT
      label: str = ""
      adapter: str = ""
      source_id: str = ""
      content_hash: Optional[str] = None
      metadata: Dict[str, Any] = field(default_factory=dict)
      embedding: Optional[List[float]] = None
      created_at: datetime = field(default_factory=datetime.utcnow)
      updated_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class DerivationChain:
      """
          The breadcrumb trail that explains WHY an edge exists.

              This is the secret weapon: instead of "these two nodes are
                  close in vector space" you get a full audit trail.
                      """
      strategy: DerivationStrategy
      confidence: float                        # 0.0 – 1.0
    evidence: Dict[str, Any] = field(default_factory=dict)
    # e.g. {"similarity_score": 0.87, "model": "text-embedding-3-small"}
    # e.g. {"rule": "shared_tag", "tag": "epistemology"}
    # e.g. {"link_text": "[[Kant]]", "position": 142}
    derived_by: str = "system"               # "system" or a worker name
    derived_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class CanonicalEdge:
      """
          A directed edge between two nodes with a full derivation chain.

              Ask "why does this edge exist?" → inspect derivation_chain.
                  """
      id: UUID = field(default_factory=uuid4)
      source_id: UUID = field(default_factory=uuid4)
      target_id: UUID = field(default_factory=uuid4)
      edge_type: EdgeType = EdgeType.MENTIONS
      derivation_chain: List[DerivationChain] = field(default_factory=list)
      weight: float = 1.0
      metadata: Dict[str, Any] = field(default_factory=dict)
      created_at: datetime = field(default_factory=datetime.utcnow)

    def explain(self) -> str:
              """Return a human-readable explanation of why this edge exists."""
              if not self.derivation_chain:
                            return "No derivation recorded."
                        lines = []
        for i, step in enumerate(self.derivation_chain, 1):
                      lines.append(
                                        f"Step {i}: [{step.strategy.value}] "
                                        f"confidence={step.confidence:.2f} "
                                        f"evidence={step.evidence}"
                      )
                  return "\n".join(lines)


@dataclass
class IngestRecord:
      """
          Tracks what was ingested, when, and from where.
              Answers question 1: "What did we ingest?"
    """
    id: UUID = field(default_factory=uuid4)
    adapter: str = ""
    source_path: str = ""
    node_count: int = 0
    edge_count: int = 0
    status: str = "pending"   # pending | complete | failed
    error: Optional[str] = None
    ingested_at: datetime = field(default_factory=datetime.utcnow)
