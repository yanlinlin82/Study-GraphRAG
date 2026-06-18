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
class HyperRelation:
  """An n-ary relationship modeled as an Event node.

  Unlike binary Relation (an Edge), a HyperRelation is reified into an Event node
  that connects arbitrarily many participants. The Event node itself stores the
  relation type, evidence text, and a link back to the source document.
  """

  relation_type: str  # one of RELATION_TYPES
  participants: List[Entity]  # all entities involved (2 or more)
  metadata: str = ""  # evidence text from source
  pmid: str = ""  # source document identifier

  def __post_init__(self) -> None:
    if self.relation_type not in RELATION_TYPES:
      raise ValueError(
        f"Invalid hyper relation type '{self.relation_type}'. "
        f"Must be one of {RELATION_TYPES}"
      )
    if len(self.participants) < 2:
      raise ValueError(
        f"HyperRelation requires at least 2 participants, got {len(self.participants)}"
      )

  @property
  def event_id(self) -> str:
    """Stable identifier for deduplication."""
    names = sorted(p.name for p in self.participants)
    return f"{self.relation_type}::{'::'.join(names)}"


@dataclass
class Relation:
  """A binary relationship (edge) connecting two entities."""

  source: Entity
  target: Entity
  type: str  # one of RELATION_TYPES
  metadata: str = ""  # evidence text from source
  pmid: str = ""  # source document identifier

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
  "CREATE CONSTRAINT event_id IF NOT EXISTS "
  "FOR (e:Event) REQUIRE e.id IS UNIQUE",
]

# Vector index creation (one per label, for broader Neo4j 5.x compatibility)
VECTOR_INDEX_TEMPLATE = """
CREATE VECTOR INDEX entity_embedding_{label} IF NOT EXISTS
  FOR (n:{label})
  ON (n.embedding)
  OPTIONS {{indexConfig: {{
    `vector.dimensions`: {dimensions},
    `vector.similarity_function`: 'cosine'
  }}}}
"""
