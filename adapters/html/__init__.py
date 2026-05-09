"""adapters/html/ — HTML page ingestion adapter."""
import re, hashlib
from pathlib import Path
from core.canonical_model import CanonicalNode, NodeType
from core.observations import Observation, ObservationBatch, ObservationType

HREF_RE = re.compile(r'href=["\']( https?://[^"\' ]+)["\' ]', re.I)
HEADING_RE = re.compile(r'<h[1-6][^>]*>\s*([^<]+)\s*</h[1-6]>', re.I)

def ingest_html_file(file_path, base_url=""):
    """Parse HTML file into a CanonicalNode + ObservationBatch."""
    path = Path(file_path)
    raw = path.read_text(encoding="utf-8", errors="replace")
    node = CanonicalNode(
        node_type=NodeType.DOCUMENT, label=path.stem, adapter="html",
        source_id=str(path), content_hash=hashlib.sha256(raw.encode()).hexdigest(),
        metadata={"base_url": base_url, "file_size": len(raw)})
    obs = (
        [Observation(source_node_id=node.id, observation_type=ObservationType.HYPERLINK,
            value=m.group(1).strip(), normalized_value=m.group(1).strip().lower(),
            position=m.start(), extractor="regex_href") for m in HREF_RE.finditer(raw)]
        + [Observation(source_node_id=node.id, observation_type=ObservationType.HEADING,
            value=m.group(1).strip(), normalized_value=m.group(1).strip().lower(),
            position=m.start(), extractor="regex_heading") for m in HEADING_RE.finditer(raw)])
    return node, ObservationBatch(source_node_id=node.id, adapter="html", observations=obs)

__all__ = ["ingest_html_file"]
