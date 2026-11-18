import argparse
import logging
import sqlite3

from rag.config import load_config
from rag.evaluation.retrieval import evaluate_retrieval
from rag.retrieval.pipeline import MODES


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate retrieval or grounded claim citations")
    parser.add_argument("--config", default="configs/config.yaml")
    parser.add_argument("--dataset", help="Override evaluation.dataset_path for a validation set")
    parser.add_argument("--mode", choices=(*MODES, "all"), default="all")
    parser.add_argument(
        "--stage", choices=("retrieval", "citations", "agreement"), default="retrieval"
    )
    parser.add_argument("--annotations", help="Human-labeled JSONL for --stage agreement")
    parser.add_argument("--allow-api", action="store_true", help="Allow bounded paid cache misses")
    parser.add_argument(
        "--with-judge", action="store_true", help="Evaluate an independent judge sample"
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        if args.annotations and args.stage != "agreement":
            raise ValueError("--annotations requires --stage agreement")
        modes = MODES if args.mode == "all" else (args.mode,)
        if args.stage == "retrieval":
            if args.allow_api or args.with_judge:
                raise ValueError("API and judge flags require --stage citations")
            evaluate_retrieval(load_config(args.config), args.dataset, modes)
        elif args.stage == "citations":
            from rag.evaluation.citations import evaluate_citations

            reports = evaluate_citations(
                load_config(args.config),
                args.dataset,
                modes,
                allow_api=args.allow_api,
                with_judge=args.with_judge,
            )
            if any(report["status"] != "ok" for report in reports):
                return 1
        else:
            from rag.evaluation.agreement import evaluate_agreement

            if args.allow_api or args.with_judge:
                raise ValueError("Agreement evaluation runs locally without API flags")
            evaluate_agreement(load_config(args.config), args.annotations)
    except (OSError, ValueError, RuntimeError, sqlite3.Error, ImportError) as exc:
        logging.getLogger(__name__).error("Retrieval evaluation failed: %s", exc)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
