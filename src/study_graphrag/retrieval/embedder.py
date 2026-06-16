"""Embedding service using Sentence-Transformers."""

import logging
from typing import List

from sentence_transformers import SentenceTransformer

from study_graphrag.config import settings

logger = logging.getLogger(__name__)


class Embedder:
  """Generate embeddings for text using Sentence-Transformers."""

  def __init__(self, model_name: str | None = None) -> None:
    self._model_name = model_name or settings.EMBEDDING_MODEL
    logger.info("Loading embedding model: %s", self._model_name)
    self._model = SentenceTransformer(self._model_name)

  def embed(self, text: str) -> List[float]:
    """Embed a single text string.

    Returns:
        A list of floats representing the embedding vector.
    """
    vector = self._model.encode(text, normalize_embeddings=True)
    return vector.tolist()

  def embed_batch(self, texts: List[str]) -> List[List[float]]:
    """Embed a batch of text strings."""
    vectors = self._model.encode(
      texts, normalize_embeddings=True, show_progress_bar=False
    )
    return [v.tolist() for v in vectors]
