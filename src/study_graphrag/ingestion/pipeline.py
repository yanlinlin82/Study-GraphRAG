"""Orchestration pipeline for knowledge graph ingestion."""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional

from tqdm import tqdm

from study_graphrag.config import settings
from study_graphrag.graph.client import GraphClient
from study_graphrag.graph.models import Entity
from study_graphrag.ingestion.entity_extractor import EntityExtractor
from study_graphrag.ingestion.relation_extractor import RelationExtractor
from study_graphrag.retrieval.embedder import Embedder

logger = logging.getLogger(__name__)


class IngestionPipeline:
  """End-to-end ingestion pipeline: text in, knowledge graph out."""

  def __init__(
    self,
    graph_client: Optional[GraphClient] = None,
    entity_extractor: Optional[EntityExtractor] = None,
    relation_extractor: Optional[RelationExtractor] = None,
    embedder: Optional[Embedder] = None,
  ) -> None:
    self.graph = graph_client or GraphClient()
    self.entity_extractor = entity_extractor or EntityExtractor()
    self.relation_extractor = relation_extractor or RelationExtractor()
    self.embedder = embedder or Embedder()

  # ------------------------------------------------------------------
  # Public API
  # ------------------------------------------------------------------

  def run_file(self, path: str, dry_run: bool = False) -> Dict:
    """Ingest a JSONL or TXT file into the knowledge graph.

    Args:
        path: Path to the input file.
        dry_run: If True, print extractions without writing to Neo4j.

    Returns:
        Summary statistics.
    """
    path_obj = Path(path)
    if path_obj.suffix == ".jsonl":
      return self._ingest_jsonl(path_obj, dry_run)
    return self._ingest_text(path_obj, dry_run)

  def run_text(
    self,
    doc_id: str,
    title: str,
    text: str,
    dry_run: bool = False,
  ) -> Dict:
    """Ingest a single document into the knowledge graph."""
    return self._process_document(
      {"id": doc_id, "title": title, "abstract": text}, dry_run
    )

  # ------------------------------------------------------------------
  # Internal
  # ------------------------------------------------------------------

  def _ingest_jsonl(self, path: Path, dry_run: bool) -> Dict:
    """Ingest a JSONL file (one JSON doc per line)."""
    docs = []
    with open(path, "r", encoding="utf-8") as fh:
      for line in fh:
        line = line.strip()
        if line:
          docs.append(json.loads(line))
    return self._ingest_docs(docs, dry_run)

  def _ingest_text(self, path: Path, dry_run: bool) -> Dict:
    """Ingest a plain text file as a single document."""
    text = path.read_text(encoding="utf-8")
    doc = {
      "id": path.stem,
      "title": path.stem.replace("_", " ").replace("-", " "),
      "abstract": text,
    }
    return self._process_document(doc, dry_run)

  def _ingest_docs(self, docs: List[Dict], dry_run: bool) -> Dict:
    """Ingest a list of document dicts."""
    stats = {
      "documents": 0,
      "entities_added": 0,
      "relations_added": 0,
    }
    for doc in tqdm(docs, desc="Ingesting"):
      result = self._process_document(doc, dry_run)
      for key in stats:
        stats[key] += result.get(key, 0)
    return stats

  def _process_document(self, doc: Dict, dry_run: bool) -> Dict:
    """Process a single document through the full pipeline."""
    doc_id = doc.get("id", "unknown")
    title = doc.get("title", "")
    abstract = doc.get("abstract", doc.get("text", ""))
    full_text = f"{title}\n\n{abstract}"

    # 1. Chunk if needed
    chunks = self._chunk_text(full_text)

    all_entities: Dict[tuple, Entity] = {}
    all_relations = []

    for chunk in chunks:
      # 2. Extract entities
      entities = self.entity_extractor.extract(chunk)
      for e in entities:
        all_entities[e.unique_key] = e

      # 3. Extract relations
      relations = self.relation_extractor.extract(chunk, entities)
      all_relations.extend(relations)

    # 4. Wrap in Article entity
    article_entity = Entity(
      name=doc_id,
      label="Article",
      description=title or doc_id,
      pmid=doc_id,
    )
    all_entities[article_entity.unique_key] = article_entity

    # 5. Link entities to article
    for entity in list(all_entities.values()):
      if entity.label != "Article":
        all_relations.append(
          type(
            "Relation",
            (),
            {
              "source": entity,
              "target": article_entity,
              "type": "MENTIONED_IN",
              "metadata": "",
              "to_triple": lambda self: (
                f"[{self.source.label}] {self.source.name} "
                f"-[:MENTIONED_IN]-> "
                f"[{self.target.label}] {self.target.name}"
              ),
            },
          )()
        )

    # 6. Generate embeddings
    logger.info(
      "Generating embeddings for %d entities...",
      len(all_entities),
    )
    for entity in all_entities.values():
      entity.embedding = self.embedder.embed(entity.embedding_text)

    # 7. Write to Neo4j (unless dry-run)
    if not dry_run:
      self.graph.initialize()
      self.graph.create_vector_index()

      for entity in all_entities.values():
        self.graph.merge_entity(entity)

      for relation in all_relations:
        self.graph.merge_relation(relation)

    logger.info(
      "Document %s: %d entities, %d relations",
      doc_id,
      len(all_entities),
      len(all_relations),
    )

    return {
      "documents": 1,
      "entities_added": len(all_entities),
      "relations_added": len(all_relations),
    }

  def _chunk_text(self, text: str) -> List[str]:
    """Split text into overlapping chunks."""
    if len(text) <= settings.CHUNK_SIZE:
      return [text]

    chunks = []
    start = 0
    while start < len(text):
      end = start + settings.CHUNK_SIZE
      chunk = text[start:end]
      chunks.append(chunk)
      start += settings.CHUNK_SIZE - settings.CHUNK_OVERLAP
    return chunks
