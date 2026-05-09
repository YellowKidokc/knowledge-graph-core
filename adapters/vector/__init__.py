"""
adapters/vector/ — Embedding and vector similarity adapter
Generates embeddings (OpenAI or custom) and builds similarity matrices.
"""
from __future__ import annotations
import math, os
from typing import Callable, Dict, List, Optional, Tuple
from uuid import UUID

from core.canonical_model import CanonicalNode

EmbedFn = Callable[[List[str]], List[List[float]]]


def _openai_embed(texts: List[str], model: str = "text-embedding-3-small") -> List[List[float]]:
    try:
        import openai
    except ImportError:
        raise ImportError("Run: pip install openai")
    client = openai.OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    resp = client.embeddings.create(input=texts, model=model)
    return [item.embedding for item in resp.data]


def embed_nodes(nodes: List[CanonicalNode], embed_fn: Optional[EmbedFn] = None,
                batch_size: int = 100) -> List[CanonicalNode]:
    fn = embed_fn or _openai_embed
    for i in range(0, len(nodes), batch_size):
        batch = nodes[i:i + batch_size]
        for node, emb in zip(batch, fn([n.label for n in batch])):
            node.embedding = emb
    return nodes


def build_similarity_matrix(nodes: List[CanonicalNode], top_k: int = 20,
                             threshold: float = 0.75) -> Dict[UUID, List[Tuple[UUID, float]]]:
    def cosine(a, b):
        dot = sum(x*y for x,y in zip(a,b))
        na = math.sqrt(sum(x**2 for x in a))
        nb = math.sqrt(sum(x**2 for x in b))
        return dot/(na*nb) if na and nb else 0.0

    embedded = [n for n in nodes if n.embedding]
    matrix: Dict[UUID, List[Tuple[UUID, float]]] = {}
    for i, node in enumerate(embedded):
        scores = [(other.id, cosine(node.embedding, other.embedding))
                  for j, other in enumerate(embedded) if i != j]
        scores = [(nid, s) for nid, s in scores if s >= threshold]
        scores.sort(key=lambda x: x[1], reverse=True)
        matrix[node.id] = scores[:top_k]
    return matrix


__all__ = ["embed_nodes", "build_similarity_matrix", "EmbedFn"]
