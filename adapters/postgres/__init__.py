"""adapters/postgres/ — Postgres persistence adapter.
Requires: psycopg2-binary, DATABASE_URL env var
"""
import json, os
try:
    import psycopg2, psycopg2.extras
    HAS_PG = True
except ImportError:
    HAS_PG = False

from core.canonical_model import CanonicalNode, IngestRecord
from core.observations import ObservationBatch


def get_connection(dsn=None):
    if not HAS_PG: raise ImportError("pip install psycopg2-binary")
    dsn = dsn or os.environ.get("DATABASE_URL")
    if not dsn: raise RuntimeError("Set DATABASE_URL")
    return psycopg2.connect(dsn)


def upsert_node(conn, node):
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO nodes (id,node_type,label,adapter,source_id,content_hash,metadata)
            VALUES (%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (adapter,source_id) DO UPDATE SET
                label=EXCLUDED.label,content_hash=EXCLUDED.content_hash,
                metadata=EXCLUDED.metadata,updated_at=NOW()
        """, (str(node.id),node.node_type.value,node.label,
              node.adapter,node.source_id,node.content_hash,json.dumps(node.metadata)))


def insert_observations(conn, batch):
    if not batch.observations: return 0
    with conn.cursor() as cur:
        vals = [(str(o.id),str(o.source_node_id),o.observation_type.value,
                 o.value,o.normalized_value,o.position,o.extractor,
                 o.confidence,json.dumps(o.metadata)) for o in batch.observations]
        psycopg2.extras.execute_values(cur, """
            INSERT INTO observations(id,source_node_id,obs_type,value,normalized_value,
                position,extractor,confidence,metadata) VALUES %s ON CONFLICT DO NOTHING
        """, vals)
    return len(batch.observations)


def insert_ingest_record(conn, record):
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO ingest_records(id,adapter,source_path,node_count,edge_count,status,error)
            VALUES (%s,%s,%s,%s,%s,%s,%s)
        """, (str(record.id),record.adapter,record.source_path,
              record.node_count,record.edge_count,record.status,record.error))


__all__ = ["get_connection","upsert_node","insert_observations","insert_ingest_record"]
