import argparse
import logging
import sqlite3
from pathlib import Path

import streamlit as st

from rag.config import Config, load_config
from rag.evaluation.answer_quality import MAX_CALLS, MAX_OUTPUT_TOKENS, evaluate_answer_quality
from rag.retrieval.pipeline import MODES
from rag.ui.catalog import CORPORA, DEFAULT_DEMO
from rag.ui.service import (
    MAX_API_CALLS_PER_SUBMIT,
    license_label,
    load_answer,
    load_corpus,
    load_demo,
    load_pdf_page,
    run_diagnostics,
    run_question,
    source_url,
    support_label,
)

logger = logging.getLogger(__name__)


def pdf_viewer(config: Config, paper_id: str, start: int, end: int, key: str) -> None:
    if st.checkbox("Lihat halaman PDF asli", key=f"pdf_{key}"):
        page = start
        if end > start:
            page = st.selectbox("Halaman PDF", range(start, end + 1), key=f"page_{key}")
        try:
            source = load_pdf_page(config, paper_id, page)
            st.image(source["image"], caption=f"Halaman PDF {page}", width="stretch")
            st.download_button(
                "Unduh PDF sumber",
                source["pdf"],
                file_name=source["filename"],
                mime="application/pdf",
                key=f"download_{key}",
            )
        except (ValueError, OSError, RuntimeError, sqlite3.Error):
            st.warning("PDF asli tidak tersedia atau identitasnya berubah. Periksa koleksi lokal.")


def clear_quality_state() -> None:
    for key in list(st.session_state):
        if key.startswith(("quality_", "evaluate_quality_")) or key == "diagnostic_results":
            st.session_state.pop(key, None)


def quality_panel(answer: dict, claim: dict, config: Config) -> None:
    claim_id = claim["claim_id"]
    result_key = f"quality_result_{claim_id}"
    st.caption("Evaluasi RAGAS untuk card ini")
    if result_key not in st.session_state:
        # Record the attempt before work so an interrupted rerun cannot repeat paid requests.
        st.session_state[result_key] = dict(
            status="failed", scores=dict(faithfulness=None, response_relevancy=None)
        )
        try:
            with st.spinner(f"Mengevaluasi card {claim['claim_order']}…"):
                st.session_state[result_key] = evaluate_answer_quality(
                    config, answer, allow_api=True, claim_id=claim_id
                )
        except (ValueError, RuntimeError, OSError, KeyError):
            logger.exception("Claim quality evaluation failed")
            st.session_state[result_key] = dict(
                status="failed", scores=dict(faithfulness=None, response_relevancy=None)
            )
    result = st.session_state[result_key]
    for column, (name, label) in zip(
        st.columns(2),
        [("faithfulness", "Faithfulness"), ("response_relevancy", "Response Relevancy")],
        strict=True,
    ):
        value = result["scores"].get(name)
        column.metric(label, "Belum tersedia" if value is None else f"{value:.3f}")
    if result["status"] in {"failed", "partial"}:
        st.warning(
            "Evaluasi belum lengkap. Periksa koneksi, environment evaluator, "
            "atau laporan evaluasi. Skor yang gagal tidak dihitung sebagai nol."
        )


def usage_panel(answer: dict) -> None:
    evaluations = [
        st.session_state.get(f"quality_result_{claim['claim_id']}", {})
        for claim in answer["claims"]
    ]
    stages = {
        "Generator": [answer.get("usage")],
        "Evaluasi RAGAS": [result.get("usage") for result in evaluations],
    }
    labels = {
        "input_tokens": "Input",
        "output_tokens": "Output",
    }
    rows = []
    totals = dict(input_tokens=0, output_tokens=0, backend_calls=0, cache_hits=0)
    incomplete = False
    for stage, usages in stages.items():
        known = [usage for usage in usages if usage is not None]
        partial = len(known) != len(usages) or any(
            usage.get("unknown_usage_attempts", 0) for usage in known
        )
        values = {key: sum(usage[key] for usage in known) for key in totals}
        for key, value in values.items():
            totals[key] += value
        rows.append(
            dict(
                Tahap=stage,
                **{
                    label: f"{values[key]:,}" if known or not usages else "Belum tersedia"
                    for key, label in labels.items()
                },
            )
        )
        incomplete |= partial
    rows.append(
        dict(Tahap="Total tercatat", **{label: f"{totals[key]:,}" for key, label in labels.items()})
    )
    with st.expander("Penggunaan token"):
        st.table(rows)
        st.caption(f"Request API: {totals['backend_calls']} · Cache hit: {totals['cache_hits']}")
        st.caption("Pemakaian pada proses jawaban ini. Cache hit tidak menambah token API baru.")
        if incomplete:
            st.caption(
                "Sebagian pemakaian belum diketahui; total hanya menjumlahkan nilai tercatat. "
                "Token generator demo tersimpan tidak dihitung sebagai pemakaian baru."
            )


def render_answer(answer: dict, corpus: dict, config: Config) -> None:
    identity = (answer["answer_id"], answer.get("database_path"), "auto-api-v1")
    if st.session_state.get("quality_answer") != identity:
        clear_quality_state()
        st.session_state["quality_answer"] = identity
    st.header("Jawaban dan bukti", anchor=False)
    st.write(answer["question"])
    if answer.get("retrieved_chunks") and (answer["status"] == "failed" or not answer["claims"]):
        st.subheader("Bukti hasil pencarian", anchor=False)
        st.caption("Kutipan yang ditemukan; belum menjadi klaim jawaban yang terverifikasi.")
        papers = {paper["paper_id"]: paper for paper in corpus["papers"]}
        for index, chunk in enumerate(answer["retrieved_chunks"], 1):
            paper = papers[chunk["paper_id"]]
            keys = ", ".join(corpus["citation_keys"].get(chunk["paper_id"], []))
            with st.expander(
                f"Bukti {index} · {keys or paper['title']} · hal. PDF {chunk['page_start']}"
            ):
                st.text(f"ID chunk: {chunk['chunk_id']}")
                st.text(chunk["text"])
                st.caption(f"Lisensi: {license_label(paper['license'])}")
                pdf_viewer(
                    config,
                    chunk["paper_id"],
                    chunk["page_start"],
                    chunk["page_end"],
                    f"retrieved_{index}",
                )
    if answer["status"] == "failed":
        st.error(
            "Generasi jawaban gagal. Periksa API key provider di environment atau .env, "
            "koneksi, dan laporan run sebelum mencoba lagi."
        )
        if answer.get("report_path"):
            st.text(f"Laporan lokal: {answer['report_path']}")
        usage_panel(answer)
        return
    if not answer["claims"]:
        st.info(
            "Tidak ada bukti yang cukup dalam konteks terambil untuk menjawab pertanyaan ini. "
            "Coba pertanyaan yang lebih spesifik."
        )
    references = {ref["chunk_id"]: ref for ref in answer["references"]}
    if answer["claims"]:
        st.caption("RAGAS otomatis mengevaluasi setiap klaim. Skor AI membantu pemeriksaan bukti.")
    for claim in answer["claims"]:
        with st.container(border=True, key=f"claim_{claim['claim_order']}"):
            st.markdown(f"### Klaim {claim['claim_order']}")
            numbers = ", ".join(f"[{references[key]['number']}]" for key in claim["citations"])
            st.text(claim["text"] + (f" {numbers}" if numbers else ""))
            if claim["unsupported"] or not claim["citations"]:
                st.caption("Tidak ada bukti untuk klaim ini.")
            quality_panel(answer, claim, config)
    usage_panel(answer)
    if answer["claims"]:
        with st.expander("Tentang skor RAGAS"):
            st.write(
                "Faithfulness (0 sampai 1) menilai klaim terhadap seluruh konteks terambil. "
                "Response Relevancy (cosine -1 sampai 1) menilai relevansi klaim terhadap "
                "pertanyaan; satu card belum tentu menjawab seluruh pertanyaan. "
                "Skor AI bukan jaminan kebenaran atau ketepatan setiap sitasi. "
                "Context Recall tetap tersedia pada evaluasi batch dengan jawaban acuan."
            )
            st.caption(
                f"API evaluasi aktif, cache-first; maksimal {MAX_CALLS} request per card, "
                f"{MAX_OUTPUT_TOKENS} output token/request. Pertanyaan, klaim dan konteks "
                "dikirim ke evaluator. Membuka sitasi atau PDF tidak mengulang evaluasi "
                "dalam sesi jawaban yang sama."
            )
    if answer["references"]:
        st.subheader("Sitasi dan sumber", anchor=False)
    for claim in answer["claims"]:
        for identifier in claim["citations"]:
            ref = references[identifier]
            pages = str(ref["page_start"])
            if ref["page_end"] != ref["page_start"]:
                pages += f"–{ref['page_end']}"
            keys = corpus["citation_keys"].get(ref["paper_id"], [])
            label = ", ".join(keys) + " · " if keys else ""
            with st.expander(f"[{ref['number']}] {label}{ref['title']} · hal. PDF {pages}"):
                st.text(f"ID chunk: {identifier}")
                if ref["section"]:
                    st.caption(f"Section perkiraan parser: {ref['section']}")
                with st.container(key=f"quote_{claim['claim_order']}_{ref['number']}"):
                    st.text(ref["quote"])
                st.caption(f"Lisensi: {license_label(ref['license'])}")
                if ref["url"]:
                    st.link_button("Buka paper sumber", ref["url"])
                else:
                    st.caption("Tautan daring belum tersedia; sumber tersimpan sebagai PDF lokal.")
                pdf_viewer(
                    config,
                    ref["paper_id"],
                    ref["page_start"],
                    ref["page_end"],
                    f"claim_{claim['claim_order']}_{ref['number']}",
                )
    if answer["claims"]:
        with st.expander("Diagnostik MiniCheck (opsional)"):
            records = answer["verification"] or st.session_state.get("diagnostic_results", [])
            if not records and st.button("Jalankan MiniCheck lokal", key="run_minicheck"):
                try:
                    with st.spinner("Menjalankan diagnostik lokal…"):
                        records = run_diagnostics(config, answer)
                    st.session_state["diagnostic_results"] = records
                except (ValueError, RuntimeError, OSError, ImportError, sqlite3.Error):
                    st.warning("Diagnostik gagal; jawaban tetap tersedia.")
            for claim in answer["claims"]:
                st.markdown(f"**Klaim {claim['claim_order']} · {support_label(claim, records)}**")
            for result in records:
                st.caption(f"{result['chunk_id']}: {result['label'] or 'belum diverifikasi'}")
            st.caption("Keputusan mesin untuk pemeriksaan tambahan; bukan penilaian manusia.")
    if answer["references"]:
        st.caption(
            "Nomor halaman mengikuti PDF. Tabel dan rumus dapat kehilangan struktur saat "
            "diekstrak; cocokkan angka dengan paper asli."
        )
    with st.expander("Catatan jawaban"):
        st.text(f"Run: {answer['run_id']}\nGenerator: {answer['model']}")
        if answer.get("report_path"):
            st.text(f"Laporan lokal: {answer['report_path']}")
        for claim in answer["claims"]:
            result = st.session_state.get(f"quality_result_{claim['claim_id']}", {})
            if result.get("directory"):
                st.text(f"Evaluasi card {claim['claim_order']}: {result['directory']}")


def main(
    config_path: str | None = None,
    demo_dir: str | None = None,
    bibliography_report: str | None = None,
) -> None:
    st.set_page_config(
        page_title="Bukti Riset | Evidence-Based Research Assistant", layout="centered"
    )
    st.html(Path(__file__).with_name("style.css"))
    st.html("<script>document.documentElement.lang = 'id';</script>", unsafe_allow_javascript=True)
    st.title("Baca klaim. Periksa buktinya.", anchor=False)
    st.write("Evidence-Based Research Assistant · Korpus lokal")
    selected_corpus = None
    if config_path is None and demo_dir is None and bibliography_report is None:
        selected_corpus = st.selectbox("Korpus", list(CORPORA))
        config_path, demo_dir, bibliography_report = CORPORA[selected_corpus]
    config_path = config_path or "configs/config.yaml"
    try:
        config = load_config(config_path)
    except (ValueError, OSError):
        st.error("Config tidak dapat dibaca. Periksa path --config dan panduan USAGE.md.")
        return
    try:
        corpus = load_corpus(config, Path(bibliography_report) if bibliography_report else None)
    except (ValueError, OSError, KeyError, TypeError, sqlite3.Error):
        logger.exception("Cannot load corpus identity")
        st.error(
            "Korpus belum tersedia atau laporan bibliografi tidak cocok. Periksa --config "
            "dan --bibliography-report; selesaikan indexing sesuai panduan USAGE.md."
        )
        return
    if st.session_state.get("corpus_fingerprint") != corpus["fingerprint"]:
        st.session_state.pop("query_answer", None)
        st.session_state.pop("paid_api_permission", None)
        clear_quality_state()
        st.session_state["corpus_fingerprint"] = corpus["fingerprint"]
    registered = (
        f"{corpus['registered']} referensi terdaftar · " if corpus["registered"] is not None else ""
    )
    st.caption(
        f"Korpus aktif: {registered}{corpus['indexed']} paper terindeks · {corpus['chunks']} chunk"
    )
    with st.expander("Paper dalam korpus aktif"):
        for paper in corpus["papers"]:
            keys = corpus["citation_keys"].get(paper["paper_id"], [])
            label = ", ".join(keys) + " · " if keys else ""
            st.text(f"{label}{paper['title']} ({paper['chunks']} chunk)")
            st.caption(f"Lisensi: {license_label(paper['license'])}")
            if not source_url(paper["landing_url"]):
                st.caption("Tautan daring belum tersedia; PDF lokal tersimpan.")
            if not paper["chunks"]:
                st.caption("Belum ada teks yang lolos pemeriksaan kualitas parsing.")
        if corpus["registered"] is not None:
            st.caption(
                "Jawaban hanya memakai paper terindeks. Referensi lain belum menjadi sumber bukti."
            )
    if demo_dir is None and bibliography_report is None:
        demo_dir = DEFAULT_DEMO
    mode = (
        st.radio(
            "Sumber jawaban",
            ["Demo tersimpan", "Tanya korpus"],
            horizontal=True,
            index=1 if selected_corpus else 0,
        )
        if demo_dir is not None
        else "Tanya korpus"
    )
    answer = None
    if mode == "Demo tersimpan":
        st.caption(
            "Jawaban tersimpan; RAGAS otomatis mengevaluasi klaim memakai API jika cache kosong."
        )
        try:
            records = load_demo(config, Path(demo_dir))
            if not records:
                st.info(
                    "Run demo belum berisi pertanyaan. Pilih run evaluasi lain melalui --demo-dir."
                )
                return
            selected = st.selectbox(
                "Contoh pertanyaan",
                range(len(records)),
                index=None,
                placeholder="Pilih pertanyaan dari evaluasi",
                format_func=lambda index: f"{records[index]['qid']} · {records[index]['question']}",
            )
            if selected is not None:
                with st.spinner("Membaca klaim dan kutipan dari korpus lokal…"):
                    answer = load_answer(config, records[selected]["answer_id"])
            else:
                st.info(
                    "Pilih contoh untuk membaca jawaban. Buka sitasinya untuk memeriksa kutipan."
                )
        except (ValueError, OSError, KeyError, TypeError, sqlite3.Error):
            logger.exception("Cannot load the saved demo")
            st.error(
                "Demo tidak cocok atau belum tersedia. Gunakan database yang sesuai dengan "
                "--demo-dir, lalu periksa perintah di USAGE.md."
            )
    else:
        answer = query_form(config)
    if answer is not None:
        render_answer(answer, corpus, config)


def query_form(config: Config) -> dict | None:
    st.caption(
        "Jawaban memakai bukti KB lokal. API generator dan evaluasi RAGAS aktif otomatis; "
        "cache diperiksa lebih dahulu."
    )
    limit = min(config.generation.max_calls_per_run, MAX_API_CALLS_PER_SUBMIT)
    with st.form("question_form"):
        question = st.text_area(
            "Pertanyaan riset", placeholder="Tulis pertanyaan tentang literatur dalam korpus"
        )
        default_mode = "hybrid+rerank" if config.retrieval.use_reranker else "hybrid"
        mode = st.selectbox("Metode retrieval", MODES, index=MODES.index(default_mode))
        st.caption(
            f"Generator: {config.generation.model}. Pertanyaan dan chunk bukti dikirim ke "
            f"provider {config.generation.provider}; maksimal {limit} request per submit, "
            f"{config.generation.max_output_tokens} output token/request. "
            f"Evaluasi maksimal {MAX_CALLS} request per card."
        )
        submitted = st.form_submit_button("Cari bukti", type="primary")
    if submitted:
        st.session_state.pop("query_answer", None)
        clear_quality_state()
        if not question.strip():
            st.error("Tulis pertanyaan sebelum mencari bukti.")
        else:
            try:
                with st.spinner("Mengambil bukti dan menyiapkan jawaban…"):
                    st.session_state["query_answer"] = run_question(
                        question.strip(), config, mode, allow_api=True
                    )
            except (ValueError, RuntimeError, OSError, ImportError, sqlite3.Error):
                logger.exception("Local query failed")
                st.error(
                    "Pencarian lokal gagal. Periksa database, indeks, dan model di config; "
                    "lihat USAGE.md."
                )
    return st.session_state.get("query_answer")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Local evidence browser with optional bounded API")
    parser.add_argument("--config", default=None)
    parser.add_argument("--demo-dir", default=None)
    parser.add_argument("--bibliography-report", default=None)
    args = parser.parse_args()
    main(args.config, args.demo_dir, args.bibliography_report)
