import argparse
import logging
import sqlite3

from rag.chunking.pipeline import chunk_corpus
from rag.config import load_config


def main() -> int:
    parser = argparse.ArgumentParser(description="Chunk parsed papers and store citation units")
    parser.add_argument("--config", default="configs/config.yaml")
    parser.add_argument("--paper-id")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        report = chunk_corpus(load_config(args.config), args.paper_id)
    except (OSError, ValueError, sqlite3.Error) as exc:
        logging.getLogger(__name__).error("Chunking failed: %s", exc)
        return 1
    return int(report["failed"] > 0)


if __name__ == "__main__":
    raise SystemExit(main())
