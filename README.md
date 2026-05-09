# knowledge-graph-core

> A Postgres-spined knowledge graph with traceable derivation chains —  
> **every edge knows why it exists.**

When you ask "why are these connected?" the system answers with an actual breadcrumb trail instead of mystical vector fog.

---

## The Four Core Questions

This system is built to answer four questions beautifully:

| # | Question | Answered by |
|---|----------|-------------|
| 1 | **What did we ingest?** | `ingest_records` table, `GET /graph/ingest` |
| 2 | **What did we observe?** | `observations` table, `core/observations.py` |
| 3 | **What graph relationships did we derive?** | `edges` + `derivation_steps` tables |
| 4 | **Why does this edge exist?** | `GET /explain/edge/{id}`, `edge.explain()` |

Question 4 is the soul of the system.

---

## Repository Structure

```
knowledge-graph-core/
├── adapters/
│   ├── obsidian/     # Obsidian vault adapter
│   ├── postgres/     # Postgres read/write adapter
│   ├── html/         # HTML page ingestion adapter
│   └── vector/       # Embedding + similarity adapter
├── core/
│   ├── canonical_model.py    # Node, Edge, DerivationChain data classes
│   ├── observations.py       # Observation types and storage
│   ├── derivations.py        # Derivation rules (the secret weapon)
│   └── graph_builders.py     # Pipeline orchestrator
├── migrations/
│   └── 001_core_schema.sql   # Postgres schema with pgvector
├── workers/
│   ├── ingest_obsidian.py    # Obsidian vault ingestion worker
│   └── build_edges.py        # Edge derivation worker
└── api/
    ├── search.py      # Full-text + semantic search
    ├── graph.py       # Neighborhood + stats endpoints
    └── explain.py     # The "why?" endpoint
```

---

## Technology Stack

| Layer | Tool | Why |
|-------|------|-----|
| Source of truth | **Postgres** | ACID, JSON, full-text search |
| Embeddings | **pgvector** | Lives inside Postgres, no extra service |
| Graph ideas | **LightRAG** | Reference for graph-enhanced RAG patterns |
| Embedded graph | **Kuzu** (optional) | If Postgres graph queries get painful |
| Inspiration | **obsidian-graph-mcp** | Obsidian + Postgres + pgvector + semantic traversal |

---

## Derivation Chain: The Secret Weapon

Every edge in the graph carries a `DerivationChain` — a step-by-step audit trail explaining why it exists:

```python
edge.explain()
# Step 1: [explicit_link] confidence=1.00 evidence={'link_text': '[[Kant]]', 'position': 142}

edge.explain()
# Step 1: [vector_similarity] confidence=0.87 evidence={'similarity_score': 0.87, 'model': 'text-embedding-3-small', 'threshold': 0.82}

edge.explain()
# Step 1: [rule_based] confidence=0.80 evidence={'shared_tag': 'epistemology'}
```

The `/explain/edge/{id}` API endpoint returns this as a human-readable JSON response with a `human_readable` field like:

> *"Kant" explicitly links to "Critique of Pure Reason" via [[Critique of Pure Reason]] (found at position 142).*

---

## Quick Start

### 1. Set up Postgres

```bash
psql $DATABASE_URL -f migrations/001_core_schema.sql
```

### 2. Ingest an Obsidian vault

```bash
python -m workers.ingest_obsidian --vault ~/my-vault --dry-run
python -m workers.ingest_obsidian --vault ~/my-vault
```

### 3. Build the graph edges

```bash
python -m workers.build_edges --adapter obsidian --dry-run
python -m workers.build_edges --all
```

### 4. Run the API

```bash
pip install fastapi uvicorn psycopg2-binary
uvicorn api.main:app --reload
```

Then visit:
- `GET /explain/edge/{edge_id}` — Why does this connection exist?
- `GET /graph/node/{node_id}/neighbors` — What is connected to this?
- `GET /search/fulltext?q=epistemology` — Full-text search
- `GET /graph/stats` — Hubs, orphans, edge type breakdown

---

## Design Principles

1. **Postgres as spine** — one source of truth, no extra graph DB required to start.
2. **Observations before edges** — raw facts are recorded before being interpreted.
3. **Every edge is justified** — no edge exists without a `DerivationChain`.
4. **Adapters are thin** — the core model doesn't care where data came from.
5. **Rules are named and versioned** — `WikilinkDerivationRule@1.0.0` not "the graph did it".

---

## References

- [LightRAG](https://github.com/HKUDS/LightRAG) — graph-enhanced RAG ideas
- [Kuzu](https://kuzudb.com/) — embedded graph DB (optional)
- [obsidian-graph-mcp](https://github.com/obsidian-graph-mcp) — Obsidian + Postgres + pgvector reference
- [pgvector](https://github.com/pgvector/pgvector) — vector similarity in Postgres

---

## License

MIT
