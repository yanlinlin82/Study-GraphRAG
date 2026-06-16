"""Answer generation from retrieved graph context using an LLM."""

import logging
from dataclasses import dataclass, field

from openai import OpenAI

from study_graphrag.config import settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a biomedical knowledge assistant. \
You answer questions based on the provided graph context.

The context contains triples in the format:
[EntityType] EntityName -[:RELATIONSHIP]-> [EntityType] EntityName

Rules:
1. Base your answer **only** on the provided context.
2. If the context does not contain enough information, say so.
3. Cite supporting triples at the end of your answer.
4. Be concise, precise, and use biomedical terminology appropriately.
"""

USER_PROMPT_TEMPLATE = """Context:
{context}

Question: {question}

Provide a concise answer based on the context above."""


@dataclass
class Answer:
  """The output of the generation layer."""

  question: str
  answer: str
  context: str
  model: str = field(default_factory=lambda: settings.LLM_MODEL)


class AnswerGenerator:
  """Generate grounded answers from graph context and a question."""

  def __init__(self, model: str | None = None) -> None:
    self._model = model or settings.LLM_MODEL
    self._client = OpenAI(
      api_key=settings.LLM_API_KEY,
      base_url=settings.LLM_BASE_URL,
    )

  def generate(self, question: str, context: str) -> Answer:
    """Generate an answer given a question and graph context.

    Args:
        question: Natural language question.
        context: String of graph triples as context.

    Returns:
        An Answer dataclass with the response.
    """
    logger.info(
      "Generating answer for question (context length: %d chars)",
      len(context),
    )

    completion = self._client.chat.completions.create(
      model=self._model,
      messages=[
        {"role": "system", "content": SYSTEM_PROMPT},
        {
          "role": "user",
          "content": USER_PROMPT_TEMPLATE.format(
            context=context,
            question=question,
          ),
        },
      ],
      temperature=settings.LLM_TEMPERATURE,
      max_tokens=settings.LLM_MAX_TOKENS,
    )

    answer_text = completion.choices[0].message.content or ""
    return Answer(
      question=question,
      answer=answer_text.strip(),
      context=context,
    )
