# Usage Examples

## Overview

After ingesting documents, the knowledge graph supports provenance-aware queries for both binary relations and n-ary (hyper) relations. Below are typical examples.

---

## Binary Relation with Source Tracking

### Scenario

A document `pmid-12345678` states: *"Olaparib targets BRCA1 and is indicated for breast cancer."*

After ingestion, the following edges exist in Neo4j:

```cypher
(:Drug {name: "Olaparib"}) -[:TARGETS {pmid: "pmid-12345678", metadata: "targets BRCA1"}]-> (:Gene {name: "BRCA1"})
(:Drug {name: "Olaparib"}) -[:INDICATED_FOR {pmid: "pmid-12345678", metadata: "indicated for breast cancer"}]-> (:Disease {name: "breast cancer"})
```

### Query: Find all relations from a specific document

```cypher
MATCH (s)-[r]->(t)
WHERE r.pmid = "pmid-12345678"
RETURN labels(s) AS source_label, s.name AS source,
       type(r) AS relation, r.metadata AS evidence,
       labels(t) AS target_label, t.name AS target
```

### Query: Verify whether two documents agree on a relation

```cypher
MATCH (s {name: "Olaparib"})-[r:TARGETS]->(t {name: "BRCA1"})
RETURN r.pmid AS source_doc, r.metadata AS evidence
ORDER BY r.pmid
```

### Query: Find the most frequently cited relation across documents

```cypher
MATCH (s)-[r:TARGETS]->(t)
RETURN s.name AS drug, t.name AS target, count(r) AS citation_count,
       collect(r.pmid) AS sources
ORDER BY citation_count DESC
```

---

## N-ary (Hyper) Relation with Source Tracking

### Scenario

A document `pmid-87654321` states: *"Imatinib treats CML by inhibiting the BCR-ABL fusion gene."*

This involves three entities (Drug, Disease, Gene) acting together -- a binary edge cannot capture this directly. Instead, an `:Event` node is created:

```
                     ┌──────────────────────┐
                     │   Event              │
                     │ id: TREATS::BCR-ABL::CML::Imatinib
                     │ type: TREATS         │
                     │ pmid: pmid-87654321  │
                     │ metadata: treats CML │
                     │   by inhibiting      │
                     │   BCR-ABL            │
                     └──────────┬───────────┘
                                │
              ┌─────────────────┼─────────────────┐
              │ PARTICIPATES_IN │                 │
         ┌────┴────┐      ┌────┴────┐      ┌─────┴─────┐
         │ Imatinib│      │   CML   │      │  BCR-ABL  │
         │  Drug   │      │ Disease │      │   Gene    │
         └─────────┘      └─────────┘      └───────────┘
                                │
                           ┌────┴────┐
                           │ Article │
                           │pmid:... │
                           └─────────┘
```

### Query: Find all events from a specific document

```cypher
MATCH (e:Event {pmid: "pmid-87654321"})
MATCH (p)-[:PARTICIPATES_IN]->(e)
RETURN e.type AS relation, e.metadata AS evidence,
       collect(p.name) AS participants
```

### Query: Find all events involving a specific entity

```cypher
MATCH (entity {name: "BCR-ABL"})-[:PARTICIPATES_IN]->(e:Event)
MATCH (p)-[:PARTICIPATES_IN]->(e)
WHERE p <> entity
RETURN e.type AS relation, e.pmid AS source,
       collect(DISTINCT p.name) AS other_participants
```

### Query: Traverse from entity through Event to find multi-step pathways

```cypher
// From Imatinib, find what it targets and what diseases are involved
MATCH (drug:Drug {name: "Imatinib"})-[:PARTICIPATES_IN]->(e:Event)
MATCH (target)-[:PARTICIPATES_IN]->(e)
WHERE target:Gene OR target:Disease
RETURN e.type, collect(target.name) AS related_entities, e.pmid AS source
```

---

## Comparison: Binary vs N-ary Models

| Scenario | Binary Edge | Event Node (n-ary) |
|---|---|---|
| two entities, one relation | `(A)-[r]->(B)` -- direct | possible but overkill |
| "Drug A targets Gene B" | `(Drug)-[:TARGETS]->(Gene)` | -- |
| "Drug A treats Disease B by targeting Gene C" | cannot express all three together | `(A,B,C)-[:PARTICIPATES_IN]->(Event)` |
| "Gene A regulates Gene B in Disease C context" | `(A)-[:REGULATES]->(B)` (loses context) | `(A,B,C)-[:PARTICIPATES_IN]->(Event)` |
| Provenance | `r.pmid` on edge | `e.pmid` on Event node, `(Event)-[:MENTIONED_IN]->(Article)` |

---

## Natural Language Queries (via the query script)

After the retrieval layer upgrade, the following NL questions are supported:

### Queries about a specific source document

```bash
uv run scripts/query.py --question "What relations are found in pmid-45678901?"
```

Context sent to the LLM will include:
```
# Relations from pmid-45678901
[Drug] Imatinib -[:TARGETS {pmid: "pmid-45678901", evidence: "inhibiting the BCR-ABL fusion protein"}]-> [Protein] BCR-ABL
[Gene] BCR-ABL -[:ENCODES {pmid: "pmid-45678901", evidence: "BCR-ABL fusion gene"}]-> [Protein] BCR-ABL
[Event] TREATS {pmid: "pmid-45678901", evidence: "effectively treats chronic myeloid leukemia"}
  participant: [Drug] Imatinib
  participant: [Disease] CML
  participant: [Gene] BCR-ABL
  source: [Article] pmid-45678901 (pmid: pmid-45678901)
```

This allows the LLM to ground its answer in the specific document.

### Queries about n-ary events involving an entity

```bash
uv run scripts/query.py --question "Show me all events involving Imatinib"
```

### Queries comparing evidence across documents

```bash
uv run scripts/query.py --question "Which documents mention the relationship between BRCA1 and Olaparib?"
```

### Queries with explicit document filtering

```bash
uv run scripts/query.py --question "What did pmid-34567890 say about EGFR and Gefitinib?"
```

### Output format (--show-context)

Use `--show-context` to inspect what the LLM receives:

```bash
uv run scripts/query.py \
  --question "What relations are found in pmid-45678901?" \
  --show-context
```

You will see the provenance-annotated triples and Event blocks passed to the AnswerGenerator.
