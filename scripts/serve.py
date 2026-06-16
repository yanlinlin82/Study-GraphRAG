#!/usr/bin/env python3
"""CLI script to start the Study GraphRAG web interface."""

import argparse
import logging
import os
import sys

import uvicorn

logging.basicConfig(
  level=logging.INFO,
  format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
  datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def main() -> None:
  parser = argparse.ArgumentParser(
    description="Start the Study GraphRAG web interface."
  )
  parser.add_argument(
    "--host",
    type=str,
    default=os.getenv("HOST", "0.0.0.0"),
    help="Bind address (default: 0.0.0.0)",
  )
  parser.add_argument(
    "--port",
    type=int,
    default=int(os.getenv("PORT", "8080")),
    help="Bind port (default: 8080)",
  )
  parser.add_argument(
    "--reload",
    action="store_true",
    help="Enable auto-reload for development",
  )
  args = parser.parse_args()

  logger.info(
    "Starting Study GraphRAG web interface at http://%s:%d",
    args.host,
    args.port,
  )
  uvicorn.run(
    "study_graphrag.web.app:app",
    host=args.host,
    port=args.port,
    reload=args.reload,
    log_level="info",
  )


if __name__ == "__main__":
  main()
