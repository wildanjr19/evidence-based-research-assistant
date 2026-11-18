import argparse
import json
import logging
import sqlite3

from rag.config import load_config
from rag.retrieval.pipeline import MODES, retrieve


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Retrieve evidence chunks from existing M3 indexes"
    )
    parser.add_argument("--config", default="configs/config.yaml")
    parser.add_argument("--question", required=True)
    parser.add_argument("--mode", choices=MODES)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        chunks = retrieve(args.question, load_config(args.config), args.mode)
        logging.getLogger(__name__).info(
            "Retrieved chunks: %s", json.dumps(chunks, ensure_ascii=True)
        )
    except (OSError, ValueError, RuntimeError, sqlite3.Error, ImportError) as exc:
        logging.getLogger(__name__).error("Retrieval failed: %s", exc)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
