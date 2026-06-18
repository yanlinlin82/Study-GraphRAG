"""Graph-aware retriever combining vector search and graph traversal."""

import json
import logging
import re
from typing import Any, Dict, List, Optional

from openai import OpenAI

from study_graphrag.config import settings
from study_graphrag.graph.client import GraphClient
from study_graphrag.graph.models import ENTITY_LABELS
from study_graphrag.retrieval.embedder import Embedder

logger = logging.getLogger(__name__)

LINKING_SYSTEM_PROMPT = """You are a biomedical entity linker. Given a question, \
identify the biomedical entities mentioned. Return a JSON object:
{{"entities": [{{"name": "...", "type": "..."}}]}}

Entity types: {labels}. Only include entities clearly present in the question."""

LINKING_USER_TEMPLATE = "Question: {question}"


class GraphSearcher:
  """Hybrid retriever: entity linking + vector search + graph expansion.

  Supports provenance-aware queries: if the question references a PMID,
  a dedicated source-document lookup is performed.
  """

  _PMID_PATTERN = re.compile(r"(?:PMID[:\s]*|pmid[:\s]*|^)(\d{8,})")

  def __init__(
    self,
    graph_client: Optional[GraphClient] = None,
    embedder: Optional[Embedder] = None,
    top_k: Optional[int] = None,
    max_hops: Optional[int] = None,
    min_score: Optional[float] = None,
  ) -> None:
    self.graph = graph_client or GraphClient()
    self.embedder = embedder or Embedder()
    self.top_k = top_k or settings.RETRIEVAL_TOP_K
    self.max_hops = max_hops or settings.RETRIEVAL_MAX_HOPS
    self.min_score = min_score or settings.RETRIEVAL_MIN_SCORE

    self._llm_client = OpenAI(
      api_key=settings.LLM_API_KEY,
      base_url=settings.LLM_BASE_URL,
    )

  def retrieve(self, question: str) -> str:
    """Retrieve graph context for a question.

    Returns a string of formatted triples for the generation layer.
    The context includes provenance information (pmid) when available,
    and Event-node blocks for n-ary relationships.
    """
    context_parts: List[str] = []

    # 0. Check if question targets a specific source document
    target_pmid = self._extract_pmid(question)

    # 1. Entity linking
    linked = self._link_entities(question)
    logger.info("Linked entities: %s", linked)

    # 2. Vector search
    query_embedding = self.embedder.embed(question)
    vector_results = self.graph.search_vector(query_embedding, self.top_k)
    vector_results = [
      r for r in vector_results if r["score"] >= self.min_score
    ]
    logger.info("Vector search returned %d results", len(vector_results))

    # 3. Combine entity names to expand
    names_to_expand = set()
    for e in linked:
      names_to_expand.add(e["name"])
    for r in vector_results:
      names_to_expand.add(r["name"])

    # 4a. Source-specific lookup (if a PMID was detected)
    if target_pmid:
      logger.info("Performing source lookup for %s", target_pmid)
      source_triples = self.graph.get_relations_by_source(target_pmid)
      if source_triples:
        context_parts.append("# Relations from " + target_pmid)
        context_parts.extend(source_triples)
        # If a specific source is requested, still add entity expansions
        # so the LLM has full context, but flag the focus.

    # 4b. Graph expansion with provenance
    triples: List[str] = []
    for name in names_to_expand:
      expanded = self.graph.expand_with_relations(name, self.max_hops)
      triples.extend(expanded)

    # Deduplicate
    triples = list(dict.fromkeys(triples))
    if triples:
      context_parts.append("# Graph neighborhood")
      context_parts.extend(triples)

    # 4c. Event expansion (n-ary relationships)
    event_blocks: List[str] = []
    for name in names_to_expand:
      blocks = self.graph.expand_entity_events(name)
      event_blocks.extend(blocks)

    if event_blocks:
      context_parts.append("# Events (n-ary relationships)")
      context_parts.extend(event_blocks)

    context = (
      "\n".join(context_parts)
      if context_parts
      else "No relevant graph context found."
    )
    return context

  def _extract_pmid(self, question: str) -> Optional[str]:
    """Extract a PMID-like identifier from the question, if present."""
    # Look for explicit "pmid-XXXXX" or "PMID: XXXXX" patterns
    match = self._PMID_PATTERN.search(question)
    if match:
      return f"pmid-{match.group(1)}"

    # Also check for "pmid-..." style
    alt = re.search(r"(?:pmid-|PMID-)(\d+)", question)
    if alt:
      return f"pmid-{alt.group(1)}"

    return None

  def _link_entities(self, question: str) -> List[Dict[str, str]]:
    """Extract entity mentions from the question using the LLM."""
    labels_str = ", ".join(sorted(ENTITY_LABELS))

    completion = self._llm_client.chat.completions.create(
      model=settings.LLM_MODEL,
      messages=[
        {
          "role": "system",
          "content": LINKING_SYSTEM_PROMPT.format(labels=labels_str),
        },
        {
          "role": "user",
          "content": LINKING_USER_TEMPLATE.format(question=question),
        },
      ],
      temperature=0.0,
      max_tokens=500,
      response_format={"type": "json_object"},
    )

    raw = completion.choices[0].message.content or '{"entities": []}'
    try:
      data = json.loads(raw)
      entities = data.get("entities", [])
      return [
        {
          "name": e["name"],
          "type": e["type"],
        }
        for e in entities
        if e.get("name") and e.get("type") in ENTITY_LABELS
      ]
    except (json.JSONDecodeError, KeyError) as exc:
      logger.warning("Failed to parse entity linking output: %s", exc)
      return []

  def retrieve_structured(self, question: str) -> Dict[str, Any]:
    """Retrieve graph context and return structured data.

    Useful for programmatic access.
    """
    context_str = self.retrieve(question)

    # Also return the raw pieces for inspection
    linked = self._link_entities(question)
    query_embedding = self.embedder.embed(question)
    vector_results = self.graph.search_vector(query_embedding, self.top_k)
    vector_results = [
      r for r in vector_results if r["score"] >= self.min_score
    ]

    names_to_expand = set()
    for e in linked:
      names_to_expand.add(e["name"])
    for r in vector_results:
      names_to_expand.add(r["name"])

    triples: List[str] = []
    for name in names_to_expand:
      expanded = self.graph.expand_with_relations(name, self.max_hops)
      triples.extend(expanded)

    return {
      "question": question,
      "linked_entities": linked,
      "vector_results": vector_results,
      "triples": list(dict.fromkeys(triples)),
      "context": context_str,
    }
