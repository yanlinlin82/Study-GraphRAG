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
  Relation,
)

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a biomedical relationship extraction assistant.

Given a text and a list of entities, extract all pairwise relationships \
between those entities.

For each relationship, return a JSON object with:
- "source_name": name of the source entity (exactly as listed)
- "source_type": type of the source entity
- "relation": the relationship type, one of {relation_types}
- "target_name": name of the target entity
- "target_type": type of the target entity
- "evidence": short phrase from the text supporting this relation

Return a JSON array: [{{"source_name": ..., "source_type": ..., "relation": ..., \
"target_name": ..., "target_type": ..., "evidence": ...}}, ...]

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

  def extract(self, text: str, entities: List[Entity]) -> List[Relation]:
    """Extract relationships between the given entities.

    Args:
        text: Original biomedical text.
        entities: Previously extracted entities.

    Returns:
        A list of Relation objects.
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

    raw = completion.choices[0].message.content or "[]"
    return self._parse(raw, entities)

  def _parse(self, raw: str, entities: List[Entity]) -> List[Relation]:
    """Parse the LLM JSON response into Relation objects."""
    relations: List[Relation] = []
    entity_map = {e.name: e for e in entities}

    try:
      data = json.loads(raw)
      if isinstance(data, dict):
        data = data.get("relations", data.get("relationships", []))
      for item in data:
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
    return relations
