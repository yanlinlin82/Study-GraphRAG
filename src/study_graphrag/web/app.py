"""Web application -- FastAPI server for the Study GraphRAG query interface."""

import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from study_graphrag.config import settings
from study_graphrag.generation.answer_generator import AnswerGenerator
from study_graphrag.retrieval.graph_searcher import GraphSearcher

logger = logging.getLogger(__name__)

app = FastAPI(title="Study GraphRAG", version="0.1.0")

# Mount static files (HTML, CSS, JS)
static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# Lazy-loaded searcher and generator
_searcher: GraphSearcher | None = None
_generator: AnswerGenerator | None = None


def get_searcher() -> GraphSearcher:
  global _searcher
  if _searcher is None:
    logger.info("Initializing GraphSearcher...")
    _searcher = GraphSearcher()
  return _searcher


def get_generator() -> AnswerGenerator:
  global _generator
  if _generator is None:
    logger.info("Initializing AnswerGenerator...")
    _generator = AnswerGenerator()
  return _generator


# ------------------------------------------------------------------
# Request / Response models
# ------------------------------------------------------------------


class QueryRequest(BaseModel):
  question: str


class QueryResponse(BaseModel):
  question: str
  answer: str
  context: str
  linked_entities: list[dict]
  model: str = settings.LLM_MODEL


# ------------------------------------------------------------------
# Routes
# ------------------------------------------------------------------


@app.get("/")
async def index() -> FileResponse:
  """Serve the main chat interface."""
  return FileResponse(str(static_dir / "index.html"))


@app.post("/api/query", response_model=QueryResponse)
async def query(request: QueryRequest) -> QueryResponse:
  """Process a natural language question and return a grounded answer."""
  if not request.question.strip():
    raise HTTPException(status_code=400, detail="Question cannot be empty.")

  logger.info("Processing query: %s", request.question)

  try:
    searcher = get_searcher()
    generator = get_generator()

    result = searcher.retrieve_structured(request.question)
    answer = generator.generate(request.question, result["context"])

    return QueryResponse(
      question=request.question,
      answer=answer.answer,
      context=result["context"],
      linked_entities=result["linked_entities"],
    )
  except Exception as exc:
    logger.exception("Query failed")
    raise HTTPException(
      status_code=500,
      detail=f"Query processing failed: {exc}",
    )


@app.get("/api/health")
async def health() -> dict:
  """Health check endpoint."""
  from study_graphrag.graph.client import GraphClient

  try:
    gc = GraphClient()
    gc.query("RETURN 1 AS n")
    neo4j_ok = True
  except Exception:
    neo4j_ok = False

  return {
    "status": "ok" if neo4j_ok else "degraded",
    "neo4j": neo4j_ok,
    "llm_model": settings.LLM_MODEL,
  }
