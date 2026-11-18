import argparse
import logging
import sqlite3

from rag.config import load_config
from rag.evaluation.retrieval import evaluate_retrieval
from rag.retrieval.pipeline import MODES


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate retrieval only; no LLM calls")
    parser.add_argument("--config", default="configs/config.yaml")
    parser.add_argument("--dataset", help="Override evaluation.dataset_path for a validation set")
    parser.add_argument("--mode", choices=(*MODES, "all"), default="all")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        modes = MODES if args.mode == "all" else (args.mode,)
        evaluate_retrieval(load_config(args.config), args.dataset, modes)
    except (OSError, ValueError, RuntimeError, sqlite3.Error, ImportError) as exc:
        logging.getLogger(__name__).error("Retrieval evaluation failed: %s", exc)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
