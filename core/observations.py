"""
observations.py — Recording what we observed during ingestion

Observations are the raw, extracted facts from documents.
They sit between raw content and derived graph edges.
Answers question 2: "What did we observe?"
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4


class ObservationType(str, Enum):
    """Types of observations extracted from source content."""
    ENTITY_MENTION = "entity_mention"
    WIKILINK = "wikilink"
    HYPERLINK = "hyperlink"
    TAG = "tag"
    HEADING = "heading"
    CODE_BLOCK = "code_block"
    FRONTMATTER_FIELD = "frontmatter_field"
    CO_OCCURRENCE = "co_occurrence"
    SEMANTIC_CLUSTER = "semantic_cluster"
    CITATION = "citation"


@dataclass
class Observation:
    """
    A single observed fact extracted from a source node.

    Every observation records WHERE it was found (source_node_id, position)
    and HOW it was extracted (extractor). This gives the derivation
    system the raw material to build justified edges.
    """
    id: UUID = field(default_factory=uuid4)
    source_node_id: UUID = field(default_factory=uuid4)
    observation_type: ObservationType = ObservationType.ENTITY_MENTION
    value: str = ""
    normalized_value: str = ""
    position: Optional[int] = None
    extractor: str = ""
    confidence: float = 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    observed_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class ObservationBatch:
    """
    A collection of observations produced in a single extraction pass.
    Useful for bulk-inserting into Postgres and for audit logging.
    """
    id: UUID = field(default_factory=uuid4)
    source_node_id: UUID = field(default_factory=uuid4)
    adapter: str = ""
    extractor_version: str = "1.0.0"
    observations: List[Observation] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)

    def summary(self) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for obs in self.observations:
            counts[obs.observation_type.value] = (
                counts.get(obs.observation_type.value, 0) + 1
            )
        return counts


@dataclass
class ObservationStore:
    """In-memory store for observations during a single ingest run."""
    _batches: List[ObservationBatch] = field(default_factory=list)

    def add_batch(self, batch: ObservationBatch) -> None:
        self._batches.append(batch)

    def all_observations(self) -> List[Observation]:
        obs: List[Observation] = []
        for batch in self._batches:
            obs.extend(batch.observations)
        return obs

    def for_node(self, node_id: UUID) -> List[Observation]:
        return [o for o in self.all_observations() if o.source_node_id == node_id]

    def total_count(self) -> int:
        return sum(len(b.observations) for b in self._batches)
