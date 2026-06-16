"""Data models for biomedical entities and relationships."""

from dataclasses import dataclass
from typing import List, Optional

# Allowed node labels
ENTITY_LABELS = {"Gene", "Protein", "Drug", "Disease", "Pathway", "Article"}

# Allowed relationship types
RELATION_TYPES = {
  "ENCODES",
  "TARGETS",
  "ASSOCIATED_WITH",
  "INDICATED_FOR",
  "PARTICIPATES_IN",
  "REGULATES",
  "INTERACTS_WITH",
  "MENTIONED_IN",
}


@dataclass
class Entity:
  """A biomedical entity node in the knowledge graph."""

  name: str
  label: str  # one of ENTITY_LABELS
  description: str = ""
  embedding: Optional[List[float]] = None

  # Optional identifiers
  uniprot_id: Optional[str] = None
  drugbank_id: Optional[str] = None
  mondo_id: Optional[str] = None
  kegg_id: Optional[str] = None
  pmid: Optional[str] = None
  chromosome: Optional[str] = None
  function: Optional[str] = None
  mechanism: Optional[str] = None

  def __post_init__(self) -> None:
    if self.label not in ENTITY_LABELS:
      raise ValueError(
        f"Invalid entity label '{self.label}'. Must be one of {ENTITY_LABELS}"
      )

  @property
  def unique_key(self) -> tuple:
    """Return a (label, name) tuple used for deduplication."""
    return (self.label, self.name)

  @property
  def embedding_text(self) -> str:
    """Text used to generate the embedding vector."""
    parts = [f"{self.label}: {self.name}"]
    if self.description:
      parts.append(f" - {self.description}")
    return "".join(parts)


@dataclass
class Relation:
  """A relationship (edge) connecting two entities."""

  source: Entity
  target: Entity
  type: str  # one of RELATION_TYPES
  metadata: str = ""  # optional evidence text

  def __post_init__(self) -> None:
    if self.type not in RELATION_TYPES:
      raise ValueError(
        f"Invalid relation type '{self.type}'. Must be one of {RELATION_TYPES}"
      )

  def to_triple(self) -> str:
    """Serialize to a human-readable triple string."""
    return (
      f"[{self.source.label}] {self.source.name} "
      f"-[:{self.type}]-> "
      f"[{self.target.label}] {self.target.name}"
    )


# Cypher queries for index and constraint initialization
INIT_QUERIES = [
  "CREATE CONSTRAINT gene_name IF NOT EXISTS "
  "FOR (g:Gene) REQUIRE g.name IS UNIQUE",
  "CREATE CONSTRAINT drug_name IF NOT EXISTS "
  "FOR (d:Drug) REQUIRE d.name IS UNIQUE",
  "CREATE CONSTRAINT disease_name IF NOT EXISTS "
  "FOR (d:Disease) REQUIRE d.name IS UNIQUE",
  "CREATE CONSTRAINT protein_name IF NOT EXISTS "
  "FOR (p:Protein) REQUIRE p.name IS UNIQUE",
  "CREATE CONSTRAINT pathway_name IF NOT EXISTS "
  "FOR (p:Pathway) REQUIRE p.name IS UNIQUE",
  "CREATE CONSTRAINT article_pmid IF NOT EXISTS "
  "FOR (a:Article) REQUIRE a.pmid IS UNIQUE",
]

# Vector index creation (must be run separately after data is present)
VECTOR_INDEX_QUERY = """
CREATE VECTOR INDEX entity_embedding IF NOT EXISTS
  FOR (n:Gene|Drug|Disease|Protein|Pathway|Article)
  ON (n.embedding)
  OPTIONS {indexConfig: {
    `vector.dimensions`: $dimensions,
    `vector.similarity_function`: 'cosine'
  }}
"""
