#!/usr/bin/env python3
"""CLI script to query the knowledge graph and generate answers."""

import argparse
import logging

from study_graphrag.generation.answer_generator import AnswerGenerator
from study_graphrag.retrieval.graph_searcher import GraphSearcher

logging.basicConfig(
  level=logging.INFO,
  format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
  datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def main() -> None:
  parser = argparse.ArgumentParser(
    description="Query the biomedical knowledge graph with natural language."
  )
  parser.add_argument(
    "--question",
    "-q",
    type=str,
    default=None,
    help="Question to ask (if omitted, interactive mode)",
  )
  parser.add_argument(
    "--top-k",
    type=int,
    default=None,
    help="Number of vector search results",
  )
  parser.add_argument(
    "--hops",
    type=int,
    default=None,
    help="Graph traversal depth",
  )
  parser.add_argument(
    "--show-context",
    action="store_true",
    help="Print the retrieved graph context",
  )
  parser.add_argument(
    "--structured",
    action="store_true",
    help="Return structured JSON output",
  )
  args = parser.parse_args()

  searcher = GraphSearcher(
    top_k=args.top_k,
    max_hops=args.hops,
  )
  generator = AnswerGenerator()

  if args.question:
    _handle_question(args.question, searcher, generator, args)
  else:
    print("Study GraphRAG -- Interactive Query Mode")
    print("Type ':quit' to exit.\n")
    while True:
      try:
        question = input("> ").strip()
      except (EOFError, KeyboardInterrupt):
        print()
        break
      if not question or question.lower() in (":quit", ":q"):
        break
      print()
      _handle_question(question, searcher, generator, args)
      print()


def _handle_question(
  question: str,
  searcher: GraphSearcher,
  generator: AnswerGenerator,
  args: argparse.Namespace,
) -> None:
  """Retrieve context and generate an answer for a single question."""
  logger.info("Processing question: %s", question)

  if args.structured:
    result = searcher.retrieve_structured(question)
    import json

    print(json.dumps(result, indent=2, ensure_ascii=False))
    return

  context = searcher.retrieve(question)

  if args.show_context:
    print("--- Context ---")
    print(context)
    print("---------------\n")

  answer = generator.generate(question, context)
  print(f"Answer: {answer.answer}")


if __name__ == "__main__":
  main()
