# Data Model

## Node Types (Entities)

| Label | Description | Key Properties |
|---|---|---|
| `Gene` | Human gene (e.g., BRCA1, TP53) | `name`, `description`, `chromosome`, `embedding` |
| `Protein` | Gene product | `name`, `uniprot_id`, `function`, `embedding` |
| `Drug` | Pharmaceutical compound | `name`, `drugbank_id`, `mechanism`, `embedding` |
| `Disease` | Medical condition | `name`, `mondo_id`, `description`, `embedding` |
| `Pathway` | Biological pathway | `name`, `kegg_id`, `description`, `embedding` |
| `Article` | Published biomedical article | `title`, `pmid`, `abstract`, `year`, `embedding` |

## Relationship Types

| Type | Source | Target | Description |
|---|---|---|---|
| `ENCODES` | Gene | Protein | Gene expresses a protein |
| `TARGETS` | Drug | Gene/Protein | Drug acts on gene or protein |
| `ASSOCIATED_WITH` | Gene/Protein | Disease | Genetic association |
| `INDICATED_FOR` | Drug | Disease | Drug is approved for a disease |
| `PARTICIPATES_IN` | Gene/Protein | Pathway | Involved in a pathway |
| `REGULATES` | Gene/Protein | Gene/Protein | Regulatory relationship |
| `INTERACTS_WITH` | Protein | Protein | Protein-protein interaction |
| `MENTIONED_IN` | (any entity) | Article | Entity appears in an article |

## Constraints & Indexes

```cypher
CREATE CONSTRAINT gene_name IF NOT EXISTS FOR (g:Gene) REQUIRE g.name IS UNIQUE;
CREATE CONSTRAINT drug_name IF NOT EXISTS FOR (d:Drug) REQUIRE d.name IS UNIQUE;
CREATE CONSTRAINT disease_name IF NOT EXISTS FOR (d:Disease) REQUIRE d.name IS UNIQUE;
CREATE CONSTRAINT protein_name IF NOT EXISTS FOR (p:Protein) REQUIRE p.name IS UNIQUE;
CREATE CONSTRAINT pathway_name IF NOT EXISTS FOR (p:Pathway) REQUIRE p.name IS UNIQUE;
CREATE CONSTRAINT article_pmid IF NOT EXISTS FOR (a:Article) REQUIRE a.pmid IS UNIQUE;

CREATE VECTOR INDEX entity_embedding IF NOT EXISTS
  FOR (n:Gene|Drug|Disease|Protein|Pathway|Article)
  ON (n.embedding)
  OPTIONS {indexConfig: {
    `vector.dimensions`: 384,
    `vector.similarity_function`: 'cosine'
  }};
```

## Example Subgraph

```
                     ┌─────────┐
                     │ Article │
                     │PMID:... │
                     └────┬────┘
                          │ MENTIONED_IN
          ┌───────────────┼───────────────┐
          ▼               ▼               ▼
      ┌────────┐    ┌─────────┐     ┌──────────┐
      │ BRCA1 │    │  Breast │     │ Olaparib │
      │ Gene  │◄───│ Disease │◄────│  Drug    │
      └───┬────┤    └─────────┘     └──────────┘
          │    │ ASSOCIATED_WITH        │
          │    └────────────────────────┘
          │ ENCODES                     │ TARGETS
          ▼                             │
      ┌────────┐                        │
      │ BRCA1 ├─────────────────────────┘
      │Protein│
      └────────┘
```

## Embedding Strategy

- Each entity is embedded using Sentence-Transformers (`all-MiniLM-L6-v2`, 384 dimensions).
- The embedding text is constructed as: `{label}: {name} - {description}`.
- Articles are embedded on their abstract text.
- Vector index uses **cosine similarity** for retrieval.
