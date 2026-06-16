#!/usr/bin/env python3
"""CLI script to ingest biomedical text into the Neo4j knowledge graph."""

import argparse
import logging

from study_graphrag.ingestion.pipeline import IngestionPipeline

logging.basicConfig(
  level=logging.INFO,
  format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
  datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def main() -> None:
  parser = argparse.ArgumentParser(
    description="Ingest biomedical text into the Neo4j knowledge graph."
  )
  parser.add_argument(
    "--input",
    "-i",
    required=True,
    help="Path to input file (.jsonl or .txt)",
  )
  parser.add_argument(
    "--dry-run",
    action="store_true",
    help="Print extractions without writing to Neo4j",
  )
  parser.add_argument(
    "--chunk-size",
    type=int,
    default=None,
    help="Max characters per chunk (overrides config)",
  )
  args = parser.parse_args()

  pipeline = IngestionPipeline()

  if args.chunk_size:
    from study_graphrag.config import settings

    settings.CHUNK_SIZE = args.chunk_size

  logger.info("Starting ingestion: %s (dry_run=%s)", args.input, args.dry_run)
  stats = pipeline.run_file(args.input, dry_run=args.dry_run)

  print("\n--- Ingestion Summary ---")
  for key, value in stats.items():
    print(f"  {key}: {value}")
  print("-------------------------\n")


if __name__ == "__main__":
  main()
