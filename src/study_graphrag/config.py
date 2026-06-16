"""Configuration for Study GraphRAG, loaded from environment variables."""

import os

from dotenv import load_dotenv

load_dotenv()


class Settings:
  """Application settings, sourced from environment variables with defaults."""

  # --- Neo4j ---
  NEO4J_URI: str = os.getenv("NEO4J_URI", "bolt://localhost:7687")
  NEO4J_USER: str = os.getenv("NEO4J_USER", "neo4j")
  NEO4J_PASSWORD: str = os.getenv("NEO4J_PASSWORD", "password")

  # --- LLM (defaults to DeepSeek OpenAI-compatible API) ---
  LLM_MODEL: str = os.getenv("LLM_MODEL", "deepseek-chat")
  LLM_API_KEY: str = os.getenv("LLM_API_KEY", "")
  LLM_BASE_URL: str = os.getenv("LLM_BASE_URL", "https://api.deepseek.com")
  LLM_MAX_TOKENS: int = int(os.getenv("LLM_MAX_TOKENS", "4096"))
  LLM_TEMPERATURE: float = float(os.getenv("LLM_TEMPERATURE", "0.1"))

  # --- Embeddings ---
  EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
  VECTOR_DIMENSIONS: int = int(os.getenv("VECTOR_DIMENSIONS", "384"))

  # --- Retrieval ---
  RETRIEVAL_TOP_K: int = int(os.getenv("RETRIEVAL_TOP_K", "10"))
  RETRIEVAL_MAX_HOPS: int = int(os.getenv("RETRIEVAL_MAX_HOPS", "2"))
  RETRIEVAL_MIN_SCORE: float = float(os.getenv("RETRIEVAL_MIN_SCORE", "0.5"))

  # --- Ingestion ---
  CHUNK_SIZE: int = int(os.getenv("CHUNK_SIZE", "1500"))
  CHUNK_OVERLAP: int = int(os.getenv("CHUNK_OVERLAP", "100"))


settings = Settings()
