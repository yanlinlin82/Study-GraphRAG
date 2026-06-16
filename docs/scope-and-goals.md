# Project Scope and Goals

## Overview

**Study GraphRAG** is a learning-oriented project aimed at building a Graph-based Retrieval-Augmented Generation (GraphRAG) system for the **biomedical domain**. It uses **Neo4j** as the underlying graph database and an LLM for both entity/relation extraction and answer generation.

This project is designed as a **study vehicle** -- the goal is to understand the principles, trade-offs, and implementation details of GraphRAG by building a concrete, end-to-end system.

---

## Goals

### Primary

1. **Learn GraphRAG fundamentals** -- Understand how graph structures improve over naive vector-only RAG by capturing entity relationships and enabling multi-hop reasoning.

2. **Build a complete ingestion pipeline** -- Extract biomedical entities (genes, proteins, drugs, diseases, pathways) and their relationships from unstructured text, and store them in Neo4j.

3. **Build a multi-stage retrieval system** -- Combine dense vector search (embeddings) with graph traversal (Cypher queries) to retrieve relevant context.

4. **Build a generation layer** -- Feed retrieved graph context to an LLM to produce grounded, traceable answers.

5. **Create a reusable biomedical data model** -- Define a consistent ontology for common biomedical entities and relationships.

### Non-Goals (Out of Scope)

- Production-grade scalability or deployment.
- Full-text indexing of millions of documents.
- Multi-modal retrieval (images, tables).
- Real-time streaming ingestion.
- Biomedical named-entity recognition (NER) model training -- we use LLM-based extraction.
- Integration with external biomedical APIs (e.g., PubMed, UniProt) -- sample data is provided.

---

## Target Audience

- Developers and data scientists interested in GraphRAG.
- Students or researchers exploring knowledge graph powered LLM applications.
- Anyone wanting a hands-on biomedical knowledge graph project.

---

## Deliverables

| Deliverable | Description |
|---|---|
| `docs/` | Design documentation, data model, architecture, usage guides |
| `src/study_graphrag/` | Modular Python package with graph, ingestion, retrieval, generation layers |
| `scripts/` | Runnable scripts for ingestion and query |
| Sample data | A small set of biomedical abstracts for testing |

---

## Technology Stack

| Component | Technology |
|---|---|
| Graph Database | **Neo4j** (community edition, local Docker) |
| LLM | OpenAI / OpenAI-compatible (configurable via `model`) |
| Embeddings | Sentence-Transformers (`all-MiniLM-L6-v2`) |
| Programming Language | **Python 3.11+** |
| Package Management | **uv** (or `pip`) |
| Containerization | Docker Compose (Neo4j only) |
