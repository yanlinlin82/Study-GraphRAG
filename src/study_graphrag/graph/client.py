"""Neo4j graph client wrapping the Bolt driver."""

import logging
from contextlib import contextmanager
from typing import Any, Dict, Generator, List, Optional

from neo4j import GraphDatabase, Record, Session

from study_graphrag.config import settings
from study_graphrag.graph.models import (
  ENTITY_LABELS,
  INIT_QUERIES,
  VECTOR_INDEX_TEMPLATE,
  Entity,
  HyperRelation,
  Relation,
)

logger = logging.getLogger(__name__)


class GraphClient:
  """High-level Neo4j client for biomedical knowledge graph operations."""

  def __init__(
    self,
    uri: Optional[str] = None,
    user: Optional[str] = None,
    password: Optional[str] = None,
  ) -> None:
    self._uri = uri or settings.NEO4J_URI
    self._user = user or settings.NEO4J_USER
    self._password = password or settings.NEO4J_PASSWORD
    self._driver = GraphDatabase.driver(
      self._uri, auth=(self._user, self._password)
    )

  def close(self) -> None:
    """Close the Neo4j driver connection."""
    self._driver.close()

  @contextmanager
  def _session(self) -> Generator[Session, None, None]:
    """Yield a session with automatic cleanup."""
    session = self._driver.session()
    try:
      yield session
    finally:
      session.close()

  def query(
    self, cypher: str, params: Optional[Dict[str, Any]] = None
  ) -> List[Record]:
    """Execute a Cypher query and return results."""
    with self._session() as session:
      results = session.run(cypher, params or {})
      return list(results)

  # ------------------------------------------------------------------
  # Initialization
  # ------------------------------------------------------------------

  def initialize(self) -> None:
    """Create uniqueness constraints and indexes."""
    logger.info("Initializing Neo4j schema...")
    for query in INIT_QUERIES:
      self.query(query)
      logger.debug("Executed: %s", query[:60])
    logger.info("Schema initialized.")

  def create_vector_index(self) -> None:
    """Create vector embedding indexes for each entity label."""
    logger.info("Creating vector indexes...")
    for label in sorted(ENTITY_LABELS):
      query = VECTOR_INDEX_TEMPLATE.format(
        label=label, dimensions=settings.VECTOR_DIMENSIONS
      )
      try:
        self.query(query)
        logger.debug("Vector index created for %s", label)
      except Exception as exc:
        logger.warning("Could not create vector index for %s: %s", label, exc)
    logger.info("Vector indexes created.")

  # ------------------------------------------------------------------
  # Entity CRUD
  # ------------------------------------------------------------------

  def merge_entity(self, entity: Entity) -> None:
    """Insert or update an entity node.

    Merges on label + name to deduplicate.
    """
    props = {
      "name": entity.name,
      "description": entity.description,
    }
    if entity.embedding:
      props["embedding"] = entity.embedding
    # Add optional identifier properties
    for key in (
      "uniprot_id",
      "drugbank_id",
      "mondo_id",
      "kegg_id",
      "pmid",
      "chromosome",
      "function",
      "mechanism",
    ):
      val = getattr(entity, key, None)
      if val is not None:
        props[key] = val

    query = (
      f"MERGE (n:{entity.label} {{name: $name}}) SET n += $props RETURN n.name"
    )
    self.query(query, {"name": entity.name, "props": props})

  def merge_relation(self, relation: Relation) -> None:
    """Insert or update a binary relationship between two entities.

    The source and target entities must already exist in the graph.
    The ``pmid`` property records the source document.
    """
    query = (
      f"MATCH (s:{relation.source.label} {{name: $source_name}}) "
      f"MATCH (t:{relation.target.label} {{name: $target_name}}) "
      f"MERGE (s)-[r:{relation.type}]->(t) "
      f"SET r.metadata = $metadata, r.pmid = $pmid "
    )
    self.query(
      query,
      {
        "source_name": relation.source.name,
        "target_name": relation.target.name,
        "metadata": relation.metadata or "",
        "pmid": relation.pmid or "",
      },
    )

  def search_vector(
    self, embedding: List[float], top_k: int = 10
  ) -> List[Dict[str, Any]]:
    """Find top-k entities by cosine similarity across all label indexes."""
    all_results: List[Dict[str, Any]] = []
    for label in sorted(ENTITY_LABELS):
      index_name = f"entity_embedding_{label}"
      query = (
        f"CALL db.index.vector.queryNodes('{index_name}', $top_k, $embedding) "
        "YIELD node, score "
        f"RETURN '{label}' AS label, node.name AS name, "
        "       node.description AS description, score "
        "ORDER BY score DESC"
      )
      try:
        results = self.query(query, {"top_k": top_k, "embedding": embedding})
        all_results.extend(
          {
            "label": r["label"],
            "name": r["name"],
            "description": r["description"],
            "score": r["score"],
          }
          for r in results
        )
      except Exception as exc:
        logger.debug("Vector search failed for %s: %s", label, exc)

    # Sort by score descending and take top_k
    all_results.sort(key=lambda x: x["score"], reverse=True)
    return all_results[:top_k]

  # ------------------------------------------------------------------
  # HyperRelation (Event node) CRUD
  # ------------------------------------------------------------------

  def merge_hyper_relation(self, hyper: HyperRelation) -> None:
    """Insert or update an n-ary relationship (reified as an Event node).

    Creates or merges an ``Event`` node with properties ``type``,
    ``metadata``, and ``pmid``, then links every participant entity to it
    via ``PARTICIPATES_IN``, and finally links the Event to its source
    Article via ``MENTIONED_IN``.

    All participant entities and the Article node must already exist.
    """
    # 1. Merge the Event node
    create_event = (
      "MERGE (e:Event {id: $event_id}) "
      "SET e.type = $relation_type, "
      "    e.metadata = $metadata, "
      "    e.pmid = $pmid "
    )
    self.query(
      create_event,
      {
        "event_id": hyper.event_id,
        "relation_type": hyper.relation_type,
        "metadata": hyper.metadata or "",
        "pmid": hyper.pmid or "",
      },
    )

    # 2. Link each participant to the Event node
    link_participant = (
      "MATCH (e:Event {id: $event_id}) "
      "MATCH (n {name: $p_name}) "
      "MERGE (n)-[:PARTICIPATES_IN]->(e) "
    )
    for p in hyper.participants:
      self.query(
        link_participant, {"event_id": hyper.event_id, "p_name": p.name}
      )

    # 3. Link the Event to its source Article (if pmid is set)
    if hyper.pmid:
      link_article = (
        "MATCH (e:Event {id: $event_id}) "
        "MATCH (a:Article {pmid: $pmid}) "
        "MERGE (e)-[:MENTIONED_IN]->(a) "
      )
      self.query(
        link_article, {"event_id": hyper.event_id, "pmid": hyper.pmid}
      )

  # ------------------------------------------------------------------
  # Graph traversal for retrieval
  # ------------------------------------------------------------------

  def expand_entity(self, name: str, max_hops: int = 2) -> List[str]:
    """Traverse the graph from an entity and return triple strings."""
    triples: List[str] = []
    seen = set()

    if max_hops < 1:
      return triples

    for hop in range(1, max_hops + 1):
      query = (
        f"MATCH path = (s)-[r*1..{hop}]-(t) WHERE s.name = $name RETURN path"
      )
      results = self.query(query, {"name": name})
      for record in results:
        path = record["path"]
        nodes = path.nodes
        for i in range(len(nodes) - 1):
          src = nodes[i]
          tgt = nodes[i + 1]
          src_labels = ":".join(src.labels)
          tgt_labels = ":".join(tgt.labels)
          triple = (
            f"[{src_labels}] {src.get('name', '?')} "
            f"-[:?]-> "
            f"[{tgt_labels}] {tgt.get('name', '?')}"
          )
          if triple not in seen:
            seen.add(triple)
            triples.append(triple)
    return triples

  def expand_with_relations(self, name: str, max_hops: int = 2) -> List[str]:
    """Traverse the graph and return triples with actual relationship types
    and provenance.

    When an edge carries a ``pmid`` property, it is included in the triple
    string so downstream components can trace the source document.
    """
    triples: List[str] = []
    seen = set()

    if max_hops < 1:
      return triples

    for hop in range(1, max_hops + 1):
      query = (
        f"MATCH path = (s)-[r*1..{hop}]-(t) WHERE s.name = $name RETURN path"
      )
      results = self.query(query, {"name": name})
      for record in results:
        path = record["path"]
        nodes = path.nodes
        rels = path.relationships
        for i in range(len(rels)):
          src_node = nodes[i]
          rel = rels[i]
          tgt_node = nodes[i + 1]
          src_labels = ":".join(src_node.labels)
          tgt_labels = ":".join(tgt_node.labels)
          rel_type = rel.type
          pmid = rel.get("pmid", "")
          if pmid:
            triple = (
              f"[{src_labels}] {src_node.get('name', '?')} "
              f'-[:{rel_type} {{pmid: "{pmid}"}}]-> '
              f"[{tgt_labels}] {tgt_node.get('name', '?')}"
            )
          else:
            triple = (
              f"[{src_labels}] {src_node.get('name', '?')} "
              f"-[:{rel_type}]-> "
              f"[{tgt_labels}] {tgt_node.get('name', '?')}"
            )
          if triple not in seen:
            seen.add(triple)
            triples.append(triple)
    return triples

  def expand_entity_events(self, name: str) -> List[str]:
    """Return context blocks for Event nodes connected to an entity.

    For each Event, the block shows the relationship type, provenance,
    all participant entities, and the source Article.
    """
    blocks: List[str] = []

    events_query = (
      "MATCH (entity {name: $name})-[:PARTICIPATES_IN]->(e:Event) "
      "RETURN e.id AS eid, e.type AS etype, "
      "       e.metadata AS emeta, e.pmid AS epmid"
    )
    events = self.query(events_query, {"name": name})

    for ev in events:
      eid = ev["eid"]
      etype = ev.get("etype", "?")
      emeta = ev.get("emeta", "")
      epmid = ev.get("epmid", "")

      # Participants of this Event
      parts_query = (
        "MATCH (e:Event {id: $eid})<-[:PARTICIPATES_IN]-(p) "
        "RETURN p.name AS pname, head(labels(p)) AS plabel"
      )
      parts = self.query(parts_query, {"eid": eid})
      participant_strs = []
      for p in parts:
        plabel = p.get("plabel", "?")
        pname = p.get("pname", "?")
        participant_strs.append(f"[{plabel}] {pname}")

      # Source Article
      article_str = ""
      if epmid:
        article_query = (
          "MATCH (e:Event {id: $eid})-[:MENTIONED_IN]->(a:Article) "
          "RETURN a.name AS aname, a.pmid AS apmid"
        )
        articles = self.query(article_query, {"eid": eid})
        if articles:
          a = articles[0]
          article_str = (
            f"  source: [Article] {a.get('aname', '?')} "
            f"(pmid: {a.get('apmid', '?')})"
          )

      meta_part = f', evidence: "{emeta}"' if emeta else ""
      lines = [f'[Event] {etype} {{pmid: "{epmid}"{meta_part}}}']
      for ps in participant_strs:
        lines.append(f"  participant: {ps}")
      if article_str:
        lines.append(article_str)

      blocks.append("\n".join(lines))

    return blocks

  def get_relations_by_source(self, pmid: str) -> List[str]:
    """Return all binary and hyper relation triples from a source document.

    Results include ``pmid`` and ``evidence`` in the triple string.
    """
    from collections import OrderedDict

    triples: List[str] = []

    # -- Binary relations from this source --
    query = (
      "MATCH (s)-[r]->(t) "
      "WHERE r.pmid = $pmid "
      "RETURN labels(s) AS src_label, s.name AS src_name, "
      "       type(r) AS rel_type, r.metadata AS metadata, "
      "       labels(t) AS tgt_label, t.name AS tgt_name "
      "LIMIT 200"
    )
    results = self.query(query, {"pmid": pmid})
    for row in results:
      src_lbl = row.get("src_label", ["?"])[0] if row.get("src_label") else "?"
      src_name = row.get("src_name", "?")
      rel_type = row.get("rel_type", "?")
      meta = row.get("metadata", "")
      tgt_lbl = row.get("tgt_label", ["?"])[0] if row.get("tgt_label") else "?"
      tgt_name = row.get("tgt_name", "?")

      if meta:
        triple = (
          f"[{src_lbl}] {src_name} "
          f'-[:{rel_type} {{pmid: "{pmid}", '
          f'evidence: "{meta}"}}]-> '
          f"[{tgt_lbl}] {tgt_name}"
        )
      else:
        triple = (
          f"[{src_lbl}] {src_name} "
          f'-[:{rel_type} {{pmid: "{pmid}"}}]-> '
          f"[{tgt_lbl}] {tgt_name}"
        )
      triples.append(triple)

    # -- HyperRelation events from this source --
    event_query = (
      "MATCH (e:Event {pmid: $pmid}) "
      "MATCH (p)-[:PARTICIPATES_IN]->(e) "
      "RETURN e.id AS eid, e.type AS etype, "
      "       e.metadata AS emeta, "
      "       p.name AS pname, head(labels(p)) AS plabel"
    )
    event_rows = self.query(event_query, {"pmid": pmid})
    if event_rows:
      event_map: Dict[str, Dict] = OrderedDict()
      for row in event_rows:
        eid = row["eid"]
        if eid not in event_map:
          event_map[eid] = {
            "etype": row.get("etype", "?"),
            "emeta": row.get("emeta", ""),
            "participants": [],
          }
        plabel = row.get("plabel", "?")
        pname = row.get("pname", "?")
        event_map[eid]["participants"].append(f"[{plabel}] {pname}")

      for eid, info in event_map.items():
        meta_part = f', evidence: "{info["emeta"]}"' if info["emeta"] else ""
        parts_str = "; ".join(info["participants"])
        triple = (
          f"[Event] {info['etype']} "
          f'{{pmid: "{pmid}"{meta_part}}} '
          f"participants: {parts_str}"
        )
        triples.append(triple)

    return triples
