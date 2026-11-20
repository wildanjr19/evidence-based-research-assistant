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
    parser = argparse.ArgumentParser(description="Import references and fetch licensed papers")
    parser.add_argument(
        "stage",
        choices=["discover", "fetch", "import-bib", "download-bib", "prepare-bib", "prepare-local"],
    )
    parser.add_argument("--config")
    parser.add_argument("--download-report", type=Path)
    parser.add_argument("--manifest", type=Path, help="Reviewed local PDF pilot manifest")
    parser.add_argument("--max-documents", type=int, help="Local admission limit; default up to 3")
    parser.add_argument(
        "--local-collection",
        action="store_true",
        help="Admit user PDFs with unverified-source labels",
    )
    parser.add_argument("--bib", type=Path, help="BibTeX input for import-bib")
    parser.add_argument("--output-dir", type=Path, default=Path("data/skripsi/references"))
    parser.add_argument(
        "--download-config", type=Path, default=Path("configs/skripsi-download.yaml")
    )
    parser.add_argument(
        "--allow-network", action="store_true", help="Spend authorized PDF pilot budget"
    )
    args = parser.parse_args()
    if args.stage == "import-bib" and args.bib is None:
        parser.error("import-bib requires --bib")
    if args.stage == "prepare-bib" and (args.config is None or args.download_report is None):
        parser.error("prepare-bib requires --config for a separate corpus and --download-report")
    if args.stage == "prepare-local" and (args.config is None or args.manifest is None):
        parser.error("prepare-local requires --config for a new corpus and --manifest")
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        if args.stage == "prepare-local":
            from rag.ingestion.local import prepare_local

            prepare_local(
                load_config(args.config),
                args.manifest,
                max_documents=args.max_documents,
                local_collection=args.local_collection,
            )
            return 0
        if args.stage == "prepare-bib":
            from rag.ingestion.prepare import prepare_downloads

            prepare_downloads(load_config(args.config), args.download_report)
            return 0
        if args.stage == "download-bib":
            from rag.ingestion.download_http import load_download_settings
            from rag.ingestion.downloads import download_bibliography

            _, report = download_bibliography(
                load_download_settings(args.download_config), allow_network=args.allow_network
            )
            return 0 if report["counts"].get("pdf_ready") else 1
        if args.stage == "import-bib":
            from rag.ingestion.bibliography import import_bibliography

            _, report = import_bibliography(args.bib, args.output_dir)
            return 1 if report["parse_failures"] else 0
        config = load_config(args.config or "configs/config.yaml")
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
    except (
        ValueError,
        OSError,
        KeyError,
        TypeError,
        sqlite3.Error,
        httpx.HTTPError,
        ET.ParseError,
    ) as exc:
        logging.getLogger(__name__).error("Ingestion failed: %s", exc)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
