# Study GraphRAG

> A learning-oriented implementation of **Graph-based Retrieval-Augmented Generation (GraphRAG)** for the **biomedical domain**, using **Neo4j** as the graph database.

This project is designed as a study vehicle to understand how graph structures improve over naive vector-only RAG by capturing entity relationships and enabling multi-hop reasoning over biomedical knowledge.

## Features

- **Biomedical data model** -- Genes, proteins, drugs, diseases, pathways, and articles with typed relationships
- **LLM-based extraction** -- Extract entities and relationships from unstructured text via LLM prompts
- **Hybrid retrieval** -- Combine dense vector search (Sentence-Transformers) with graph traversal (Cypher)
- **Grounded generation** -- LLM answers are based on retrieved graph triples with evidence
- **Neo4j native** -- Uniqueness constraints, vector index, and Cypher-powered graph traversal

## Quick Start

```bash
# 1. Start Neo4j
docker compose up -d

# 2. Install
python -m venv .venv && source .venv/bin/activate
pip install -e .
cp .env.example .env   # Edit: set LLM_API_KEY

# 3. Ingest sample data
python scripts/ingest.py --input data/sample_articles.jsonl

# 4. Query
python scripts/query.py --question "What drugs target BRCA1?"
```

For detailed documentation, see [docs/index.md](docs/index.md).

## Architecture

```
User Question
    │
    ▼
┌─────────────────┐
│  Entity Linking │── Extract entities from question (LLM)
└────────┬────────┘
         ▼
┌─────────────────┐
│  Vector Search  │── Embed question, find similar entities
└────────┬────────┘
         ▼
┌─────────────────┐
│ Graph Expansion │── Traverse Neo4j 1-2 hops for paths
└────────┬────────┘
         ▼
┌─────────────────┐
│ Context Assembly│── Serialize triples into text
└────────┬────────┘
         ▼
┌─────────────────┐
│ LLM Generation  │── Answer with evidence
└─────────────────┘
```

## Data Model

| Node Label | Examples | Key Relations |
|---|---|---|
| `Gene` | BRCA1, TP53, EGFR | ENCODES, ASSOCIATED_WITH, TARGETS |
| `Protein` | p53, BRCA1 protein | INTERACTS_WITH, REGULATES, TARGETS |
| `Drug` | Olaparib, Gefitinib | TARGETS, INDICATED_FOR |
| `Disease` | Breast Cancer, NSCLC | ASSOCIATED_WITH, INDICATED_FOR |
| `Pathway` | PI3K/AKT, RAS/RAF | PARTICIPATES_IN |
| `Article` | PMIDs | MENTIONED_IN (from entities) |

## Project Structure

```
src/study_graphrag/
├── config.py               # Environment configuration
├── graph/                  # Neo4j client + data models
├── ingestion/              # LLM entity/relation extraction pipeline
├── retrieval/              # Hybrid vector + graph search
└── generation/             # LLM answer generation
scripts/                    # CLI entry points
docs/                       # Full documentation
```

See [docs/index.md](docs/index.md) for the complete project structure.

## Configuration

All settings via environment variables (`.env` file):

| Variable | Default | Description |
|---|---|---|
| `NEO4J_URI` | `bolt://localhost:7687` | Neo4j connection |
| `LLM_MODEL` | `gpt-4o-mini` | LLM for extraction/generation |
| `LLM_API_KEY` | (required) | API key |
| `EMBEDDING_MODEL` | `all-MiniLM-L6-v2` | Sentence-Transformers model |

## Documentation

| Document | Description |
|---|---|
| [Scope & Goals](docs/scope-and-goals.md) | Project scope, goals, non-goals, tech stack |
| [Architecture](docs/architecture.md) | Layer design, data flow, key decisions |
| [Data Model](docs/data-model.md) | Nodes, relations, constraints, indexes |
| [Ingestion Guide](docs/ingestion-guide.md) | How to ingest text into Neo4j |
| [Query Guide](docs/query-guide.md) | How to query and get answers |

## License

MIT
