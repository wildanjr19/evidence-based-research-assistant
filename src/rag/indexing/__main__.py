import argparse
import logging
import sqlite3

from rag.config import load_config
from rag.indexing.pipeline import index_corpus


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Embed stored chunks and build LanceDB + FTS5 indexes"
    )
    parser.add_argument("--config", default="configs/config.yaml")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        index_corpus(load_config(args.config))
    except (OSError, ValueError, RuntimeError, sqlite3.Error, ImportError) as exc:
        logging.getLogger(__name__).error("Indexing failed: %s", exc)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
