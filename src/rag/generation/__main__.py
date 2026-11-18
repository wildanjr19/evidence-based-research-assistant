import argparse
import logging
import sqlite3

from rag.config import load_config
from rag.generation.pipeline import answer_question
from rag.retrieval.pipeline import MODES


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Retrieve chunks and generate validated claims JSON"
    )
    parser.add_argument("--config", default="configs/config.yaml")
    parser.add_argument("--question", required=True)
    parser.add_argument("--mode", choices=MODES)
    parser.add_argument(
        "--allow-api", action="store_true", help="Explicitly enable paid LLM calls on cache misses"
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        result = answer_question(
            args.question, load_config(args.config), args.mode, allow_api=args.allow_api
        )
        logging.getLogger(__name__).info("%s", result["markdown"])
        return 1 if result["status"] == "failed" else 0
    except (OSError, ValueError, RuntimeError, sqlite3.Error, ImportError) as exc:
        logging.getLogger(__name__).error("Generation failed: %s", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
