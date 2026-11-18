import argparse
import logging
import sqlite3
import xml.etree.ElementTree as ET
from pathlib import Path

import httpx

from rag.config import load_config
from rag.ingestion.arxiv import ArxivClient
from rag.ingestion.pipeline import discover, fetch


def main() -> int:
    parser = argparse.ArgumentParser(description="Discover and fetch licensed arXiv papers")
    parser.add_argument("stage", choices=["discover", "fetch"])
    parser.add_argument("--config", default="configs/config.yaml")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        config = load_config(args.config)
        with httpx.Client(
            timeout=config.ingestion.timeout_seconds,
            limits=httpx.Limits(max_connections=1, max_keepalive_connections=1),
            headers={"User-Agent": "evidence-based-research-assistant/0.1.0"},
            follow_redirects=True,
        ) as http:
            client = ArxivClient(config.ingestion, Path(config.paths.cache_dir), http)
            if args.stage == "discover":
                discover(config, client)
            else:
                fetch(config, client)
    except (ValueError, OSError, sqlite3.Error, httpx.HTTPError, ET.ParseError) as exc:
        logging.getLogger(__name__).error("Ingestion failed: %s", exc)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
