"""Export the AI-authored pilot draft, bound to canonical chunks; never mark it human gold."""

import argparse
import hashlib
import json
import sqlite3
from contextlib import closing
from pathlib import Path

from rag.config import load_config
from rag.ids import make_chunk_id, make_run_id
from rag.indexing.embedding import text_hash

DOIS = {
    "Y": "10.11591/eei.v13i5.8032",
    "W": "10.18653/v1/2020.aacl-main.85",
    "K": "10.18653/v1/2021.emnlp-main.833",
    "S": "10.18653/v1/2024.naacl-short.63",
    "L": "10.18653/v1/2025.acl-long.243",
}

# These are AI reference drafts, not independent relevance judgments or human labels.
QUESTIONS = [
    (
        "en",
        "lookup",
        "Which three IndoBERT-based ABSA approaches do Yulianti and Nissa investigate?",
        "They compare feature-based single-sentence classification, fine-tuned single-sentence "
        "classification, and fine-tuned sentence-pair classification using auxiliary sentences.",
        [("Y", 1, 2)],
    ),
    (
        "id",
        "lookup",
        "Berapa jumlah tugas dalam IndoNLU dan apa rentang jenis tugasnya?",
        "IndoNLU mencakup dua belas tugas, dari klasifikasi kalimat tunggal hingga pelabelan "
        "sekuens pada pasangan kalimat.",
        [("W", 1, 2)],
    ),
    (
        "en",
        "comparison",
        "How do Yulianti's IndoBERT ABSA approaches and InstructABSA adapt models for ABSA?",
        "Yulianti and Nissa compare feature extraction and fine-tuning of IndoBERT with "
        "single-sentence or sentence-pair inputs. InstructABSA instruction-tunes Tk-Instruct "
        "with positive, negative, and neutral examples.",
        [("Y", 1, 2), ("S", 1, 1)],
    ),
    (
        "id",
        "unanswerable",
        "Berapa akurasi IndoBERTweet pada ulasan pelanggan yang saya kumpulkan pada November 2026?",
        "Tidak ada bukti dalam korpus tentang hasil pada dataset pribadi tersebut.",
        [],
    ),
    (
        "id",
        "lookup",
        "Model mana yang paling efektif dalam studi ABSA Yulianti dan Nissa?",
        "IndoBERT yang di-fine-tune untuk klasifikasi pasangan kalimat "
        "memiliki efektivitas tertinggi.",
        [("Y", 1, 3)],
    ),
    (
        "en",
        "lookup",
        "Which approach offers the best effectiveness-efficiency tradeoff in Yulianti and Nissa?",
        "When effectiveness and efficiency are considered together, the best-performing "
        "approach is fine-tuned IndoBERT for single-sentence classification.",
        [("Y", 1, 3)],
    ),
    (
        "id",
        "lookup",
        "Dari jenis sumber apa data pra-pelatihan Indo4B dikumpulkan?",
        "Indo4B dikumpulkan dari sumber publik seperti teks media sosial, blog, berita, "
        "dan situs web.",
        [("W", 1, 2)],
    ),
    (
        "en",
        "lookup",
        "Why do the IndoNLU authors exclude Twitter data from their public dataset release?",
        "They do not share the Twitter data because of restrictions in the Twitter Developer "
        "Policy and Agreement.",
        [("W", 5, 22)],
    ),
    (
        "en",
        "lookup",
        "How does IndoBERTweet initialize new domain-specific vocabulary embeddings?",
        "It initializes domain-specific vocabulary using average pooling "
        "of BERT subword embeddings.",
        [("K", 1, 4)],
    ),
    (
        "id",
        "lookup",
        "Apa domain sasaran IndoBERTweet dan bagaimana model dasarnya dikembangkan?",
        "IndoBERTweet ditujukan untuk Twitter berbahasa Indonesia dan memperluas model BERT "
        "monolingual Indonesia dengan kosakata khusus domain.",
        [("K", 1, 1)],
    ),
    (
        "en",
        "lookup",
        "What efficiency benefit and evaluation scope are reported in the IndoBERTweet abstract?",
        "Average BERT subword initialization makes pretraining five times faster, with extrinsic "
        "evaluation over seven Twitter-based datasets.",
        [("K", 1, 1)],
    ),
    (
        "id",
        "lookup",
        "Model dasar apa yang digunakan InstructABSA dan contoh sentimen apa yang ditambahkan?",
        "InstructABSA melakukan instruction tuning pada Tk-Instruct dan menambahkan contoh "
        "positif, negatif, serta netral pada sampel pelatihan.",
        [("S", 1, 1)],
    ),
    (
        "en",
        "lookup",
        "Which SemEval editions are used to evaluate InstructABSA in its abstract?",
        "The abstract reports experiments on SemEval 2014, 2015, and 2016 datasets.",
        [("S", 1, 1)],
    ),
    (
        "id",
        "lookup",
        "Apa dampak contoh instruksi menyesatkan pada InstructABSA menurut abstraknya?",
        "Penambahan contoh menyesatkan menurunkan performa InstructABSA sekitar 10 persen.",
        [("S", 1, 2)],
    ),
    (
        "en",
        "lookup",
        "What does SchemaBench measure and approximately how many JSON schemas does it contain?",
        "SchemaBench assesses models' ability to generate valid JSON and contains around "
        "40,000 different JSON schemas.",
        [("L", 1, 1)],
    ),
    (
        "id",
        "lookup",
        "Aspek generasi JSON apa yang diselidiki dalam studi Schema Reinforcement Learning?",
        "Studi menyelidiki pemahaman struktur, escaping, dan deskripsi bahasa alami "
        "untuk menghasilkan JSON yang valid.",
        [("L", 1, 1)],
    ),
    (
        "en",
        "lookup",
        "How does Schema Reinforcement Learning improve JSON schema understanding?",
        "It incorporates reinforcement learning with a Fine-grained Schema Validator "
        "to improve models' understanding of JSON schemas.",
        [("L", 1, 1)],
    ),
    (
        "id",
        "comparison",
        "Bagaimana cakupan sumber IndoNLU berbeda dari domain sasaran IndoBERTweet?",
        "IndoNLU menyediakan tugas dari berbagai domain dan gaya serta pra-pelatihan Indo4B "
        "dari sumber beragam. IndoBERTweet khusus ditujukan untuk Twitter berbahasa Indonesia.",
        [("W", 1, 2), ("K", 1, 1)],
    ),
    (
        "en",
        "unanswerable",
        "What is the exact current API price of GPT-4o-mini in November 2026?",
        "The corpus provides no evidence for the current November 2026 API price.",
        [],
    ),
    (
        "id",
        "unanswerable",
        "Berapa waktu inferensi gabungan IndoBERTweet dan InstructABSA di RTX 3060 Ti milik saya?",
        "Tidak ada pengukuran pada perangkat pribadi tersebut dalam korpus.",
        [],
    ),
]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("data/skripsi/s5-ragas/drafts"))
    args = parser.parse_args()
    config = load_config(args.config)
    directory = args.output_dir / make_run_id().replace(":", "-")
    if not directory.resolve().is_relative_to(Path("data").resolve()):
        raise ValueError("Draft artifacts must remain under data/")
    directory.mkdir(parents=True, exist_ok=False)
    path = Path(config.paths.db_path).resolve()
    with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as connection:
        papers = {}
        for key, doi in DOIS.items():
            rows = connection.execute("SELECT paper_id FROM paper WHERE doi=?", (doi,)).fetchall()
            if len(rows) != 1:
                raise ValueError("Expected exactly one prepared snapshot per pilot DOI")
            papers[key] = rows[0][0]
        records = []
        for index, (language, qtype, question, reference, evidence) in enumerate(QUESTIONS, 1):
            identifiers = [make_chunk_id(papers[key], page, order) for key, page, order in evidence]
            hashes = {}
            for identifier in identifiers:
                row = connection.execute(
                    "SELECT text FROM chunk WHERE chunk_id=?", (identifier,)
                ).fetchone()
                if row is None:
                    raise ValueError("Draft chunk is missing; references require a new review")
                hashes[identifier] = text_hash(row[0])
            records.append(
                dict(
                    qid=f"skripsi-draft-{index:03d}",
                    question=question,
                    qtype=qtype,
                    language=language,
                    gold_chunk_ids=identifiers,
                    gold_paper_ids=list(dict.fromkeys(papers[key] for key, _, _ in evidence)),
                    reference=reference,
                    reference_status="ai_draft_unreviewed",
                    reference_text_sha256=hashes,
                )
            )
    output = directory / "questions.jsonl"
    with output.open("x", encoding="utf-8") as stream:
        for record in records:
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")
    manifest = dict(
        status="ai_draft_unreviewed",
        human_reviewed=False,
        human_accuracy=None,
        authoring="AI-authored draft based on local pilot chunks; not Ragas LLM testset generation",
        approval_scope="User approved 20 draft questions with Ragas and a small human audit",
        question_count=len(records),
        dataset_sha256=hashlib.sha256(output.read_bytes()).hexdigest(),
        authoring_script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        corpus_db_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        caution="gold_* field names follow the existing loader; these are unreviewed AI references",
    )
    with (directory / "manifest.json").open("x", encoding="utf-8") as stream:
        json.dump(manifest, stream, indent=2)
    import logging

    logging.basicConfig(level=logging.INFO)
    logging.info("Exported %d AI draft questions: %s", len(records), output)


if __name__ == "__main__":
    main()
