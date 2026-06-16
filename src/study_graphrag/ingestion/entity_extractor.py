"""Entity extraction from biomedical text using an LLM."""

import json
import logging
from typing import List

from openai import OpenAI

from study_graphrag.config import settings
from study_graphrag.graph.models import ENTITY_LABELS, Entity

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a biomedical entity extraction assistant. Given a text, extract all biomedical entities.

For each entity, return a JSON object with:
- "name": canonical name of the entity
- "type": one of {labels}
- "description": short contextual description from the text

Return a JSON array: [{{"name": ..., "type": ..., "description": ...}}, ...]

Only include entities that clearly match one of the types above.
Do NOT include generic terms like "patient", "cell", "treatment". \
Focus on specific named entities.
"""  # noqa: E501

USER_PROMPT_TEMPLATE = (
  "Extract biomedical entities from the following text:\n\n{text}"
)


class EntityExtractor:
  """Extract biomedical entities from text using a configured LLM."""

  def __init__(self, model: str | None = None) -> None:
    self._model = model or settings.LLM_MODEL
    self._client = OpenAI(
      api_key=settings.LLM_API_KEY,
      base_url=settings.LLM_BASE_URL,
    )

  def extract(self, text: str) -> List[Entity]:
    """Extract entities from the given text.

    Args:
        text: Biomedical text to analyze.

    Returns:
        A list of extracted Entity objects.
    """
    labels_str = ", ".join(sorted(ENTITY_LABELS))

    completion = self._client.chat.completions.create(
      model=self._model,
      messages=[
        {
          "role": "system",
          "content": SYSTEM_PROMPT.format(labels=labels_str),
        },
        {
          "role": "user",
          "content": USER_PROMPT_TEMPLATE.format(text=text),
        },
      ],
      temperature=settings.LLM_TEMPERATURE,
      max_tokens=settings.LLM_MAX_TOKENS,
      response_format={"type": "json_object"},
    )

    raw = completion.choices[0].message.content or "[]"
    return self._parse(raw)

  def _parse(self, raw: str) -> List[Entity]:
    """Parse the LLM JSON response into Entity objects."""
    entities: List[Entity] = []
    try:
      data = json.loads(raw)
      # Handle both array and {"entities": [...]} formats
      if isinstance(data, dict):
        data = data.get("entities", data.get("entities", []))
      for item in data:
        entity = Entity(
          name=item.get("name", "").strip(),
          label=item.get("type", "").strip(),
          description=item.get("description", "").strip(),
        )
        if entity.name and entity.label in ENTITY_LABELS:
          entities.append(entity)
    except (json.JSONDecodeError, KeyError) as exc:
      logger.warning("Failed to parse LLM entity output: %s", exc)
    return entities
