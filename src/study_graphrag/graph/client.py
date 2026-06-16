"""Neo4j graph client wrapping the Bolt driver."""

import logging
from contextlib import contextmanager
from typing import Any, Dict, Generator, List, Optional

from neo4j import GraphDatabase, Record, Session

from study_graphrag.config import settings
from study_graphrag.graph.models import (
  INIT_QUERIES,
  VECTOR_INDEX_QUERY,
  Entity,
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
    """Create the vector embedding index if it does not exist."""
    logger.info("Creating vector index...")
    self.query(
      VECTOR_INDEX_QUERY,
      {"dimensions": settings.VECTOR_DIMENSIONS},
    )
    logger.info("Vector index created.")

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
    """Insert or update a relationship between two entities.

    The source and target entities must already exist in the graph.
    """
    query = (
      f"MATCH (s:{relation.source.label} {{name: $source_name}}) "
      f"MATCH (t:{relation.target.label} {{name: $target_name}}) "
      f"MERGE (s)-[r:{relation.type}]->(t) "
      f"SET r.metadata = $metadata "
    )
    self.query(
      query,
      {
        "source_name": relation.source.name,
        "target_name": relation.target.name,
        "metadata": relation.metadata or "",
      },
    )

  def search_vector(
    self, embedding: List[float], top_k: int = 10
  ) -> List[Dict[str, Any]]:
    """Find top-k entities by cosine similarity using the vector index."""
    query = (
      "CALL db.index.vector.queryNodes('entity_embedding', $top_k, $embedding) "
      "YIELD node, score "
      "RETURN labels(node)[0] AS label, node.name AS name, "
      "       node.description AS description, score "
      "ORDER BY score DESC"
    )
    results = self.query(query, {"top_k": top_k, "embedding": embedding})
    return [
      {
        "label": r["label"],
        "name": r["name"],
        "description": r["description"],
        "score": r["score"],
      }
      for r in results
    ]

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
        segments = path
        for i in range(len(segments) - 1):
          src = segments[i]
          tgt = segments[i + 1]
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
    """Traverse the graph and return triples with actual relationship types."""
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
        for i in range(0, len(path) - 2, 2):
          src_node = path[i]
          rel = path[i + 1]
          tgt_node = path[i + 2]
          src_labels = ":".join(src_node.labels)
          tgt_labels = ":".join(tgt_node.labels)
          rel_type = rel.type
          triple = (
            f"[{src_labels}] {src_node.get('name', '?')} "
            f"-[:{rel_type}]-> "
            f"[{tgt_labels}] {tgt_node.get('name', '?')}"
          )
          if triple not in seen:
            seen.add(triple)
            triples.append(triple)
    return triples
