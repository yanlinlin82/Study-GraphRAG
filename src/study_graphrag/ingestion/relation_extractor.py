"""Relation extraction from biomedical text using an LLM."""

import json
import logging
from typing import List

from openai import OpenAI

from study_graphrag.config import settings
from study_graphrag.graph.models import (
  ENTITY_LABELS,
  RELATION_TYPES,
  Entity,
  HyperRelation,
  Relation,
)

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a biomedical relationship extraction assistant.

Given a text and a list of entities, extract two kinds of relationships:

### 1. Binary (pairwise) relationships
For each ordered pair of entities that have a direct relationship, return:
- "source_name": name of the source entity (exactly as listed)
- "source_type": type of the source entity
- "relation": the relationship type, one of {relation_types}
- "target_name": name of the target entity
- "target_type": type of the target entity
- "evidence": short phrase from the text supporting this relation

### 2. N-ary (multi-participant) relationships
Sometimes a relationship involves MORE THAN TWO entities acting together \
(e.g., "Drug A treats Disease B by targeting Gene C"). For these cases, return:
- "relation_type": the relationship type, one of {relation_types}
- "participants": list of {{"name": ..., "type": ...}} for ALL entities involved
- "evidence": short phrase from the text supporting this relationship

---

Return a JSON object with two keys:
- "binary": [{{binary-relation-objects}}]
- "hyper": [{{n-ary-relation-objects}}]

Only include relationships that are explicitly or clearly implied by the text.
"""  # noqa: E501

USER_PROMPT_TEMPLATE = """Text:
{text}

Entities:
{entities_json}

Extract relationships between these entities."""


class RelationExtractor:
  """Extract relationships between entities from text using an LLM."""

  def __init__(self, model: str | None = None) -> None:
    self._model = model or settings.LLM_MODEL
    self._client = OpenAI(
      api_key=settings.LLM_API_KEY,
      base_url=settings.LLM_BASE_URL,
    )

  def extract(
    self, text: str, entities: List[Entity]
  ) -> tuple[List[Relation], List[HyperRelation]]:
    """Extract relationships between the given entities.

    Args:
        text: Original biomedical text.
        entities: Previously extracted entities.

    Returns:
        A tuple (binary_relations, hyper_relations).
    """
    entities_data = [{"name": e.name, "type": e.label} for e in entities]
    relation_types_str = ", ".join(sorted(RELATION_TYPES))

    completion = self._client.chat.completions.create(
      model=self._model,
      messages=[
        {
          "role": "system",
          "content": SYSTEM_PROMPT.format(relation_types=relation_types_str),
        },
        {
          "role": "user",
          "content": USER_PROMPT_TEMPLATE.format(
            text=text,
            entities_json=json.dumps(entities_data, indent=2),
          ),
        },
      ],
      temperature=settings.LLM_TEMPERATURE,
      max_tokens=settings.LLM_MAX_TOKENS,
      response_format={"type": "json_object"},
    )

    raw = completion.choices[0].message.content or "{}"
    return self._parse(raw, entities)

  def _parse(
    self, raw: str, entities: List[Entity]
  ) -> tuple[List[Relation], List[HyperRelation]]:
    """Parse the LLM JSON response into Relation and HyperRelation objects."""
    relations: List[Relation] = []
    hyper_relations: List[HyperRelation] = []
    entity_map = {e.name: e for e in entities}

    try:
      data = json.loads(raw)
      if isinstance(data, list):
        # Backward compat: old format returns a flat array
        items = data
      else:
        # New format: {"binary": [...], "hyper": [...]}
        items = data.get(
          "binary", data.get("relations", data.get("relationships", []))
        )
        hyper_items = data.get("hyper", data.get("nary", []))

        # Parse hyper relations
        for item in hyper_items:
          rel_type = item.get("relation_type", "").strip().upper()
          participants_raw = item.get("participants", [])
          participants = []
          for p in participants_raw:
            p_name = p.get("name", "").strip()
            ent = entity_map.get(p_name)
            if ent:
              participants.append(ent)
          if rel_type in RELATION_TYPES and len(participants) >= 2:
            hyper_relations.append(
              HyperRelation(
                relation_type=rel_type,
                participants=participants,
                metadata=item.get("evidence", ""),
              )
            )

      # Parse binary relations
      for item in items:
        src_name = item.get("source_name", "").strip()
        tgt_name = item.get("target_name", "").strip()
        rel_type = item.get("relation", "").strip().upper()
        src = entity_map.get(src_name)
        tgt = entity_map.get(tgt_name)

        if src and tgt and rel_type in RELATION_TYPES:
          relations.append(
            Relation(
              source=src,
              target=tgt,
              type=rel_type,
              metadata=item.get("evidence", ""),
            )
          )
    except (json.JSONDecodeError, KeyError) as exc:
      logger.warning("Failed to parse LLM relation output: %s", exc)
    return relations, hyper_relations
