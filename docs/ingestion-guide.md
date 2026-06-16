# Ingestion Guide

## Overview

The ingestion pipeline takes unstructured biomedical text, extracts entities and relationships using an LLM, and stores the resulting knowledge graph in Neo4j.

---

## Pipeline Steps

```
 Raw Text (.txt/.json) ──► Chunking ──► Entity Extraction ──► Relation Extraction
        │                                                           │
        ▼                                                           ▼
  Embedding Generation ◄── Entity Dedup ◄── Graph Writer ◄─────────┘
        │
        ▼
  Neo4j (merge nodes + relationships + vector index)
```

### 1. Input Format

By default, the pipeline accepts:
- **JSONL** files: one document per line with `{"id": ..., "title": ..., "abstract": ...}`
- **Plain text**: one file per article (for simplicity)

Example JSONL line:

```json
{
  "id": "pmid-12345678",
  "title": "BRCA1 in breast cancer",
  "abstract": "BRCA1 is a tumor suppressor gene... Olaparib targets BRCA1-mutated cells..."
}
```

### 2. Entity Extraction

The LLM receives a prompt that asks it to extract biomedical entities from the text. Extracted entities must conform to one of the defined types (Gene, Protein, Drug, Disease, Pathway, Article).

Each extracted entity includes:
- `name` (canonical form)
- `type` (one of the node labels above)
- `description` (short contextual description from the source text)

### 3. Relation Extraction

After entities are extracted, the same text is processed again to extract pairwise relationships. The LLM is asked to produce triples in the form `(source_entity, relationship_type, target_entity)`.

Relationships must use one of the defined types (TARGETS, ENCODES, ASSOCIATED_WITH, etc.) to ensure consistency.

### 4. Embedding Generation

For each entity, a text string is constructed as `{label}: {name} - {description}` and passed through Sentence-Transformers to produce a 384-dimensional embedding vector. This vector is stored as a property on the node for vector similarity search.

### 5. Graph Writing

Entities are written to Neo4j using `MERGE` on `name` + `type` to deduplicate. Relationships use `MERGE` as well to avoid duplicate edges.

---

## Running Ingestion

```bash
# Ingest a single file
python scripts/ingest.py --input data/sample_articles.jsonl

# Ingest with custom chunk size
python scripts/ingest.py --input data/articles.jsonl --chunk-size 2000

# Dry run (show extractions without writing to Neo4j)
python scripts/ingest.py --input data/sample_articles.jsonl --dry-run
```

---

## Configuration

All configuration is in `src/study_graphrag/config.py`, which reads from environment variables (`.env` file):

| Variable | Default | Description |
|---|---|---|
| `NEO4J_URI` | `bolt://localhost:7687` | Neo4j connection URI |
| `NEO4J_USER` | `neo4j` | Neo4j username |
| `NEO4J_PASSWORD` | `password` | Neo4j password |
| `LLM_MODEL` | `gpt-4o-mini` | LLM model identifier |
| `LLM_API_KEY` | (required) | API key for LLM provider |
| `LLM_BASE_URL` | `https://api.openai.com/v1` | LLM API base URL |
| `EMBEDDING_MODEL` | `all-MiniLM-L6-v2` | Sentence-Transformers model |
| `VECTOR_DIMENSIONS` | `384` | Embedding vector dimensions |
