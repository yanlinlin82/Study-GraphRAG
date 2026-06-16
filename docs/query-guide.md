# Query Guide

## Overview

The query pipeline takes a natural language biomedical question, retrieves relevant graph context from Neo4j, and generates a grounded answer using an LLM.

---

## Query Flow

```
 User Question ──► Entity Linking ──► Vector Search ──► Graph Expansion ──► Context Assembly
                                                                                │
                                                                                ▼
                                                                         LLM Generation
                                                                                │
                                                                                ▼
                                                                          Answer + Evidence
```

### 1. Entity Linking

The user's question is sent to the LLM to extract entity mentions. For example:

```
Question: "What drugs target BRCA1?"
Entities: [{"name": "BRCA1", "type": "Gene"}]
```

### 2. Vector Search

The full question is embedded using Sentence-Transformers and a vector similarity search is performed against all entity nodes in Neo4j. This retrieves the top-k most semantically similar entities (default: 10).

This step captures entities that may have been missed by strict entity linking.

### 3. Graph Expansion

For each matched entity (from both linking and vector search), the system traverses the graph 1-2 hops along defined relationships.

Example Cypher queries:

```cypher
// 1-hop from entity
MATCH (e {name: $name})-[r]->(n)
RETURN e, r, n

// 2-hop expansion
MATCH (e {name: $name})-[r1]->()-[r2]->(n)
RETURN e, r1, r2, n
```

### 4. Context Assembly

Graph paths are serialized into text:

```
[Gene] BRCA1 -[:ENCODES]-> [Protein] BRCA1 protein
[Drug] Olaparib -[:TARGETS]-> [Gene] BRCA1
[Disease] Breast Cancer <-[:ASSOCIATED_WITH]- [Gene] BRCA1
```

These triples are combined with vector search results to form the final context.

### 5. LLM Generation

A prompt is constructed:

```
You are a biomedical knowledge assistant. Use the following graph context to answer the question.

Context:
{context_triples}

Question: {question}

Answer with citations to the supporting triples.
```

---

## Running a Query

```bash
# Interactive query
python scripts/query.py

# Single query
python scripts/query.py --question "What proteins interact with TP53?"

# With custom parameters
python scripts/query.py \
  --question "What pathways is EGFR involved in?" \
  --top-k 15 \
  --hops 2
```

---

## Example Output

```
Question: What drugs target BRCA1?

Answer: Several drugs target BRCA1, primarily through the mechanism of
PARP inhibition. The key drug is Olaparib (Lynparza), which is approved
for BRCA1-mutated ovarian and breast cancers. Other PARP inhibitors
include Niraparib and Rucaparib, which also exploit BRCA1 deficiency
through synthetic lethality.

Evidence:
- [Drug] Olaparib -[:TARGETS]-> [Gene] BRCA1
- [Drug] Niraparib -[:TARGETS]-> [Gene] BRCA1
- [Gene] BRCA1 -[:ASSOCIATED_WITH]-> [Disease] Ovarian Cancer
```

---

## Advanced Usage

### Direct Cypher Queries

For power users, the `GraphClient` supports direct Cypher execution:

```python
from study_graphrag.graph.client import GraphClient

client = GraphClient()
results = client.query(
    "MATCH (d:Drug)-[:TARGETS]->(g:Gene {name: $name}) RETURN d.name",
    {"name": "BRCA1"}
)
```

### Retrieval Customization

```python
from study_graphrag.retrieval.graph_searcher import GraphSearcher

searcher = GraphSearcher(
    top_k=15,       # vector search results
    max_hops=2,     # graph traversal depth
    min_score=0.5   # minimum vector similarity threshold
)

context = searcher.retrieve("What drugs target BRCA1?")
```
