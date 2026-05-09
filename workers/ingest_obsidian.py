"""
workers/ingest_obsidian.py — Obsidian vault ingestion worker

Walks an Obsidian vault directory, parses frontmatter and wikilinks,
creates CanonicalNodes, and emits ObservationBatches for the graph builder.

Usage:
    python -m workers.ingest_obsidian --vault /path/to/vault
"""

from __future__ import annotations
import argparse
import hashlib
import re
import sys
from pathlib import Path
from typing import List, Optional, Tuple
from uuid import uuid4

try:
    import yaml  # PyYAML
except ImportError:
    yaml = None  # frontmatter parsing is optional


# Relative imports work when run as a module
from core.canonical_model import CanonicalNode, IngestRecord, NodeType
from core.observations import Observation, ObservationBatch, ObservationType


# ---- Regex patterns -------------------------------------------------------

WIKILINK_RE = re.compile(r'\[\[([^\]|]+)(?:\|[^\]]+)?\]\]')
TAG_RE = re.compile(r'(?:^|\s)#([A-Za-z0-9_/-]+)')
FRONTMATTER_RE = re.compile(r'^---\s*\n(.*?)\n---\s*\n', re.DOTALL)


# ---- Helpers ---------------------------------------------------------------

def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _parse_frontmatter(raw: str) -> Tuple[dict, str]:
    """Return (frontmatter_dict, body_without_frontmatter)."""
    match = FRONTMATTER_RE.match(raw)
    if match and yaml:
        try:
            fm = yaml.safe_load(match.group(1)) or {}
            body = raw[match.end():]
            return fm, body
        except Exception:
            pass
    return {}, raw


# ---- Core ingest logic -----------------------------------------------------

def ingest_vault(vault_path: str) -> Tuple[List[CanonicalNode], List[ObservationBatch], IngestRecord]:
    """
    Ingest all .md files in an Obsidian vault.

    Returns:
        nodes          — one CanonicalNode per .md file
        obs_batches    — one ObservationBatch per file
        ingest_record  — summary of what was ingested
    """
    vault = Path(vault_path).expanduser().resolve()
    if not vault.is_dir():
        raise FileNotFoundError(f"Vault directory not found: {vault}")

    record = IngestRecord(
        adapter="obsidian",
        source_path=str(vault),
        status="pending",
    )

    nodes: List[CanonicalNode] = []
    obs_batches: List[ObservationBatch] = []

    for md_file in sorted(vault.rglob("*.md")):
        try:
            raw = md_file.read_text(encoding="utf-8")
        except Exception as e:
            print(f"[WARN] Could not read {md_file}: {e}", file=sys.stderr)
            continue

        frontmatter, body = _parse_frontmatter(raw)

        # Derive label from filename (without extension)
        label = md_file.stem

        node = CanonicalNode(
            node_type=NodeType.DOCUMENT,
            label=label,
            adapter="obsidian",
            source_id=str(md_file.relative_to(vault)),
            content_hash=_sha256(raw),
            metadata={
                "frontmatter": frontmatter,
                "file_size": len(raw),
                "vault": str(vault),
            },
        )
        nodes.append(node)

        # --- Extract observations ---
        obs: List[Observation] = []

        # Wikilinks
        for match in WIKILINK_RE.finditer(body):
            link_target = match.group(1).strip()
            obs.append(Observation(
                source_node_id=node.id,
                observation_type=ObservationType.WIKILINK,
                value=match.group(0),
                normalized_value=link_target.lower(),
                position=match.start(),
                extractor="regex_wikilink",
                confidence=1.0,
            ))

        # Inline tags
        for match in TAG_RE.finditer(body):
            tag = match.group(1)
            obs.append(Observation(
                source_node_id=node.id,
                observation_type=ObservationType.TAG,
                value=f"#{tag}",
                normalized_value=tag.lower(),
                position=match.start(),
                extractor="regex_tag",
                confidence=1.0,
            ))

        # Frontmatter tags
        fm_tags = frontmatter.get("tags", [])
        if isinstance(fm_tags, str):
            fm_tags = [fm_tags]
        for tag in fm_tags:
            obs.append(Observation(
                source_node_id=node.id,
                observation_type=ObservationType.FRONTMATTER_FIELD,
                value=str(tag),
                normalized_value=str(tag).lower(),
                extractor="frontmatter_tags",
                confidence=1.0,
            ))

        obs_batches.append(ObservationBatch(
            source_node_id=node.id,
            adapter="obsidian",
            observations=obs,
        ))

    record.node_count = len(nodes)
    record.edge_count = 0  # edges are derived later by build_edges.py
    record.status = "complete"
    return nodes, obs_batches, record


# ---- CLI -------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest an Obsidian vault")
    parser.add_argument("--vault", required=True, help="Path to Obsidian vault")
    parser.add_argument("--dry-run", action="store_true", help="Print summary without writing")
    args = parser.parse_args()

    nodes, batches, record = ingest_vault(args.vault)
    total_obs = sum(len(b.observations) for b in batches)
    print(f"Ingested {record.node_count} notes, {total_obs} observations")

    if args.dry_run:
        for node in nodes[:5]:
            print(f"  {node.label} ({node.source_id})")
        if len(nodes) > 5:
            print(f"  ... and {len(nodes) - 5} more")


if __name__ == "__main__":
    main()
