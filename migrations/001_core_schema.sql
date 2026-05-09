-- migrations/001_core_schema.sql
-- Postgres spine for knowledge-graph-core
-- Run with: psql $DATABASE_URL -f migrations/001_core_schema.sql

-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================================
-- ENUMS
-- ============================================================

CREATE TYPE node_type AS ENUM (
    'document', 'concept', 'entity', 'observation', 'claim', 'question'
);

CREATE TYPE edge_type AS ENUM (
    'mentions', 'similar_to', 'cites', 'derived_from',
    'contradicts', 'supports', 'co_occurs', 'parent_of', 'tagged_with'
);

CREATE TYPE derivation_strategy AS ENUM (
    'explicit_link', 'vector_similarity', 'co_occurrence',
    'nlp_extraction', 'rule_based', 'human_asserted', 'imported'
);

CREATE TYPE ingest_status AS ENUM ('pending', 'complete', 'failed');

-- ============================================================
-- NODES
-- ============================================================

CREATE TABLE nodes (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    node_type       node_type NOT NULL DEFAULT 'document',
    label           TEXT NOT NULL,
    adapter         TEXT NOT NULL,           -- 'obsidian', 'html', 'postgres', etc.
    source_id       TEXT NOT NULL,           -- original path, URL, or row PK
    content_hash    TEXT,                    -- SHA-256 for deduplication
    metadata        JSONB NOT NULL DEFAULT '{}',
    embedding       vector(1536),            -- pgvector; NULL until embedded
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (adapter, source_id)              -- no duplicates per adapter
);

-- Fast lookup by label (case-insensitive)
CREATE INDEX idx_nodes_label ON nodes USING gin(to_tsvector('english', label));
CREATE INDEX idx_nodes_adapter ON nodes(adapter);
CREATE INDEX idx_nodes_type ON nodes(node_type);

-- pgvector IVFFlat index for approximate nearest-neighbor search
CREATE INDEX idx_nodes_embedding ON nodes
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- ============================================================
-- OBSERVATIONS
-- Answers question 2: "What did we observe?"
-- ============================================================

CREATE TABLE observations (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    source_node_id  UUID NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
    obs_type        TEXT NOT NULL,
    value           TEXT NOT NULL,
    normalized_value TEXT NOT NULL,
    position        INTEGER,
    extractor       TEXT NOT NULL,
    confidence      FLOAT NOT NULL DEFAULT 1.0,
    metadata        JSONB NOT NULL DEFAULT '{}',
    observed_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_obs_node ON observations(source_node_id);
CREATE INDEX idx_obs_type ON observations(obs_type);
CREATE INDEX idx_obs_value ON observations(normalized_value);

-- ============================================================
-- EDGES + DERIVATION CHAINS
-- Answers question 3: "What relationships were derived?"
-- Answers question 4: "Why does this edge exist?"
-- ============================================================

CREATE TABLE edges (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    source_id       UUID NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
    target_id       UUID NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
    edge_type       edge_type NOT NULL,
    weight          FLOAT NOT NULL DEFAULT 1.0,
    metadata        JSONB NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_edges_source ON edges(source_id);
CREATE INDEX idx_edges_target ON edges(target_id);
CREATE INDEX idx_edges_type ON edges(edge_type);

-- Derivation chain: one row per step per edge
CREATE TABLE derivation_steps (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    edge_id         UUID NOT NULL REFERENCES edges(id) ON DELETE CASCADE,
    step_order      INTEGER NOT NULL DEFAULT 0,
    strategy        derivation_strategy NOT NULL,
    confidence      FLOAT NOT NULL,
    evidence        JSONB NOT NULL DEFAULT '{}',
    derived_by      TEXT NOT NULL,       -- rule name + version
    derived_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_deriv_edge ON derivation_steps(edge_id);
CREATE INDEX idx_deriv_strategy ON derivation_steps(strategy);

-- ============================================================
-- INGEST RECORDS
-- Answers question 1: "What did we ingest?"
-- ============================================================

CREATE TABLE ingest_records (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    adapter         TEXT NOT NULL,
    source_path     TEXT NOT NULL,
    node_count      INTEGER NOT NULL DEFAULT 0,
    edge_count      INTEGER NOT NULL DEFAULT 0,
    status          ingest_status NOT NULL DEFAULT 'pending',
    error           TEXT,
    ingested_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_ingest_adapter ON ingest_records(adapter);
CREATE INDEX idx_ingest_status ON ingest_records(status);

-- ============================================================
-- HELPER VIEW: explain_edge
-- Returns a human-readable derivation trail for any edge
-- ============================================================

CREATE VIEW edge_explanations AS
SELECT
    e.id AS edge_id,
    n_src.label AS source_label,
    n_src.adapter AS source_adapter,
    e.edge_type,
    n_tgt.label AS target_label,
    n_tgt.adapter AS target_adapter,
    json_agg(
        json_build_object(
            'step', ds.step_order,
            'strategy', ds.strategy,
            'confidence', ds.confidence,
            'evidence', ds.evidence,
            'derived_by', ds.derived_by,
            'derived_at', ds.derived_at
        ) ORDER BY ds.step_order
    ) AS derivation_chain
FROM edges e
JOIN nodes n_src ON n_src.id = e.source_id
JOIN nodes n_tgt ON n_tgt.id = e.target_id
LEFT JOIN derivation_steps ds ON ds.edge_id = e.id
GROUP BY e.id, n_src.label, n_src.adapter, e.edge_type, n_tgt.label, n_tgt.adapter;

COMMENT ON VIEW edge_explanations IS
    'Answers the fourth core question: Why does this edge exist?';
