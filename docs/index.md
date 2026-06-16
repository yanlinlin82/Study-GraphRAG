# Study GraphRAG Documentation

> Graph-based Retrieval-Augmented Generation for the biomedical domain, powered by Neo4j.

## Quick Links

| Document | Description |
|---|---|
| [Scope & Goals](scope-and-goals.md) | Project scope, primary goals, non-goals, and technology stack |
| [Architecture](architecture.md) | Layered system design, data flow, and key design decisions |
| [Data Model](data-model.md) | Node/relation types, constraints, indexes, and embedding strategy |
| [Ingestion Guide](ingestion-guide.md) | How to ingest biomedical text into the knowledge graph |
| [Query Guide](query-guide.md) | How to query the graph and generate answers |

## Project Structure

```
Study-GraphRAG/
├── README.md                      # Quick-start guide (this file)
├── pyproject.toml                 # Python package configuration
├── .env.example                   # Environment variable template
├── docker-compose.yml             # Neo4j container setup
│
├── docs/                          # Design documentation
│   ├── index.md
│   ├── scope-and-goals.md
│   ├── architecture.md
│   ├── data-model.md
│   ├── ingestion-guide.md
│   └── query-guide.md
│
├── src/study_graphrag/            # Core Python package
│   ├── config.py                  # Settings from environment
│   ├── graph/                     # Graph storage layer
│   │   ├── client.py              #   Neo4j client (CRUD, vector search)
│   │   └── models.py              #   Entity & Relation data models
│   ├── ingestion/                 # Ingestion layer
│   │   ├── entity_extractor.py   #   LLM-based entity extraction
│   │   ├── relation_extractor.py #   LLM-based relation extraction
│   │   └── pipeline.py           #   Orchestration pipeline
│   ├── retrieval/                 # Retrieval layer
│   │   ├── embedder.py           #   Sentence-Transformers embedding
│   │   └── graph_searcher.py     #   Hybrid graph + vector search
│   └── generation/                # Generation layer
│       └── answer_generator.py   #   LLM answer assembly
│
├── scripts/                       # Runnable entry points
│   ├── ingest.py                  #   CLI for ingestion
│   └── query.py                   #   CLI for querying
│
├── data/                          # Sample biomedical data
│   └── sample_articles.jsonl
│
└── tests/                         # Unit tests
```

## Quick Start

### Prerequisites

- Python 3.11+
- Docker & Docker Compose (for Neo4j)
- An OpenAI API key (or compatible LLM provider)

### 1. Start Neo4j

```bash
docker compose up -d
# Wait ~10 seconds for Neo4j to initialize
```

Open Neo4j Browser at <http://localhost:7474> (user: `neo4j`, password: `password`).

### 2. Set up Python environment

```bash
# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate

# Install with pip
pip install -e .

# Copy and edit environment variables
cp .env.example .env
# Edit .env: set LLM_API_KEY
```

### 3. Ingest sample data

```bash
python scripts/ingest.py --input data/sample_articles.jsonl
```

### 4. Ask questions

```bash
# Single question
python scripts/query.py --question "What drugs target BRCA1?"

# Interactive mode
python scripts/query.py

# With full context trace
python scripts/query.py --question "How does TP53 relate to cancer?" --show-context
```
