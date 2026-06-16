# Architecture

## High-Level Design

The system follows a layered architecture with four main components:

```
 ┌──────────────────────────────────────────────────────────┐
 │                    User / Client                         │
 └────────────┬─────────────────────────────────┬───────────┘
              │ (1) natural language question   │
              ▼                                 │
 ┌────────────────────────┐                     │
 │     Generation Layer   │ ◄───────────────────┘
 │  (LLM answer assembly) │     (4) answer
 └────────┬───────────────┘
          │ (3) retrieved graph context
          ▼
 ┌────────────────────────┐
 │     Retrieval Layer    │
 │  (vector + graph +     │
 │   hybrid search)       │
 └────────┬───────────────┘
          │ (2) entity-aware query / vector sim
          ▼
 ┌────────────────────────┐     ┌──────────────────┐
 │   Graph Storage Layer  │────►│   Neo4j (AuraDB  │
 │   (Neo4j client)       │◄───│     or local)     │
 └────────┬───────────────┘     └──────────────────┘
          │ (0) extracted triples
          ▼
 ┌────────────────────────┐     ┌──────────────────┐
 │   Ingestion Layer      │────►│  External Text   │
 │   (LLM + Embeddings)   │◄───│  (PubMed, etc.)   │
 └────────────────────────┘     └──────────────────┘
```

## Layer Responsibilities

### 1. Ingestion Layer (`src/study_graphrag/ingestion/`)

- Reads biomedical text (abstracts, articles).
- Uses an LLM to extract entities and relationships.
- Generates embeddings for entity nodes and stores them in Neo4j.
- Deduplicates entities on insertion (merge by name + type).

**Flow:**
```
 Raw Text ──► Entity Extractor ──► Relation Extractor ──► Graph Writer ──► Neo4j
```

### 2. Graph Storage Layer (`src/study_graphrag/graph/`)

- Wraps Neo4j Python driver.
- Provides high-level CRUD methods for entities and relationships.
- Maintains a consistent Cypher query interface.
- Supports both local Neo4j (Docker) and remote (AuraDB / Neo4j Cloud).

### 3. Retrieval Layer (`src/study_graphrag/retrieval/`)

Extracts relevant subgraph from Neo4j given a user question:

1. **Entity Linking** -- Extract entities from the question using the LLM.
2. **Vector Search** -- Embed the question and find top-k similar entities.
3. **Graph Expansion** -- From matched entities, traverse 1-2 hops via relationships.
4. **Context Assembly** -- Combine vector results and graph paths into a structured context.

### 4. Generation Layer (`src/study_graphrag/generation/`)

- Receives the retrieved graph context (nodes + paths).
- Constructs a prompt with the context and the user's question.
- Calls the configured LLM to produce a grounded answer.
- Returns the answer together with supporting evidence (triples/paths).

---

## Data Flow for a Query

```
User: "What drugs target BRCA1?"
  │
  ▼
1. Entity Linking → ["BRCA1"]
2. Vector Search  → Find similar entity nodes
3. Graph Traversal → MATCH (d:Drug)-[:TARGETS]->(g:Gene {name:"BRCA1"})
4. Context        → [d.name, relationship type, g.name]
5. Prompt         → Context + Question → LLM
6. Answer         → "Olaparib, niraparib, ..."
```

---

## Key Design Decisions

| Decision | Rationale |
|---|---|
| LLM-based extraction (not NER model) | Faster to iterate; no training required; flexible schema |
| Sentence-Transformers for embeddings | Lightweight; runs locally; good for entity similarity |
| Hybrid retrieval (vector + graph) | Vector finds similar entities; graph captures multi-hop relationships |
| Neo4j community edition | Free; Dockerized; wide adoption |
| Cypher over GraphQL | Native to Neo4j; powerful path queries |
