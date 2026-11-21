import argparse
import logging
import sqlite3
from pathlib import Path

import streamlit as st

from rag.config import Config, load_config
from rag.evaluation.answer_quality import MAX_CALLS, MAX_OUTPUT_TOKENS, evaluate_answer_quality
from rag.retrieval.pipeline import MODES
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
DEFAULT_DEMO = "eval/results/2026-11-19T01-25-11Z_7492c6"
LOCAL_UI = "data/skripsi/ui-local/2026-11-21T08-16-45Z_07d296"
LOCAL_RECEIPT = "data/skripsi/kb-local-all/2026-11-20T01-59-17Z_c95c3b/admission-receipt.json"
CORPORA = {
    "Referensi skripsi lengkap (41 PDF)": (
        "configs/skripsi-local.yaml",
        LOCAL_UI + "/demo",
        LOCAL_RECEIPT,
    ),
    "Pilot skripsi (5 PDF)": (
        "configs/skripsi-pilot.yaml",
        None,
        "data/skripsi/pilot-v1/index/reports/prepare-2026-11-19T07-11-50Z_3aa5f1.json",
    ),
    "Benchmark MVP": (
        "data/m6-multipaper/20261119T004114Z/config-citations-surplus-gpt-authorized-v1.yaml",
        DEFAULT_DEMO,
        None,
    ),
}


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


def quality_panel(answer: dict, config: Config) -> None:
    st.subheader("Evaluasi kualitas", anchor=False)
    identity = (answer["answer_id"], answer.get("database_path"))
    if st.session_state.get("quality_answer") != identity:
        for key in ("quality_result", "quality_api_permission", "diagnostic_results"):
            st.session_state.pop(key, None)
        st.session_state["quality_answer"] = identity
    if answer["status"] != "ok" or not answer["claims"]:
        st.caption("Evaluasi memerlukan jawaban yang berisi klaim.")
        return
    allow_api = st.checkbox(
        f"Izinkan API evaluasi (maks. {MAX_CALLS} request, "
        f"{MAX_OUTPUT_TOKENS} output token/request)",
        value=False,
        key="quality_api_permission",
    )
    st.caption(
        "Jawaban dan konteks dikirim ke evaluator terpisah jika API diizinkan. "
        "Cache diperiksa lebih dahulu; embedding pertanyaan berjalan lokal."
    )
    if st.button("Evaluasi kualitas", key="evaluate_quality"):
        st.session_state.pop("quality_result", None)
        try:
            with st.spinner("Menghitung Faithfulness dan Response Relevancy…"):
                st.session_state["quality_result"] = evaluate_answer_quality(
                    config, answer, allow_api=allow_api
                )
        except (ValueError, RuntimeError, OSError, KeyError):
            logger.exception("Answer quality evaluation failed")
            st.session_state["quality_result"] = dict(
                status="failed", scores=dict(faithfulness=None, response_relevancy=None)
            )
    result = st.session_state.get("quality_result")
    if result is None:
        st.caption("Belum dievaluasi. Jawaban tetap dapat dibaca tanpa menjalankan evaluator.")
        return
    for column, (name, label) in zip(
        st.columns(2),
        [("faithfulness", "Faithfulness"), ("response_relevancy", "Response Relevancy")],
        strict=True,
    ):
        value = result["scores"].get(name)
        column.metric(label, "Belum tersedia" if value is None else f"{value:.3f}")
    if result["status"] in {"failed", "partial"}:
        st.warning(
            "Evaluasi belum lengkap. Periksa cache, izin API, environment evaluator, "
            "atau laporan evaluasi. Skor yang gagal tidak dihitung sebagai nol."
        )
    st.caption(
        "Faithfulness: dukungan seluruh konteks terambil terhadap jawaban (0–1). "
        "Relevancy: kesesuaian jawaban dengan pertanyaan (cosine −1–1). "
        "Skor adalah estimasi AI, bukan jaminan kebenaran atau ketepatan setiap sitasi. "
        "Context Recall tersedia pada evaluasi batch dengan jawaban acuan."
    )
    if usage := result.get("usage"):
        st.caption(f"Request evaluasi: {usage['backend_calls']} · Cache hit: {usage['cache_hits']}")
    if result.get("directory"):
        st.caption(f"Laporan evaluasi: {result['directory']}")


def render_answer(answer: dict, corpus: dict, config: Config) -> None:
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
    if usage := answer.get("usage"):
        st.caption(
            f"Percobaan API: {usage['backend_calls']} · Cache hit: {usage['cache_hits']} · "
            f"Token API tercatat: {usage['input_tokens']} input / {usage['output_tokens']} output"
        )
        if usage["unknown_usage_attempts"]:
            st.caption("Pemakaian token sebagian percobaan gagal belum diketahui.")
    if answer["status"] == "failed":
        if answer.get("api_allowed"):
            st.error(
                "Generasi jawaban gagal. Periksa API key provider di environment atau .env, "
                "koneksi, dan laporan run sebelum mencoba lagi."
            )
        else:
            st.error(
                "Jawaban belum tersedia dari cache. Aktifkan izin API berbayar untuk membuat "
                "jawaban baru. Periksa laporan run jika cache rusak."
            )
        if answer.get("report_path"):
            st.text(f"Laporan lokal: {answer['report_path']}")
        return
    if not answer["claims"]:
        st.info(
            "Tidak ada bukti yang cukup dalam konteks terambil untuk menjawab pertanyaan ini. "
            "Coba pertanyaan yang lebih spesifik."
        )
    references = {ref["chunk_id"]: ref for ref in answer["references"]}
    for claim in answer["claims"]:
        numbers = ", ".join(f"[{references[key]['number']}]" for key in claim["citations"])
        st.text(claim["text"] + (f" {numbers}" if numbers else ""))
        if claim["unsupported"] or not claim["citations"]:
            st.caption("Tidak ada bukti untuk klaim ini.")
    quality_panel(answer, config)
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
        for key in (
            "quality_answer",
            "quality_result",
            "quality_api_permission",
            "diagnostic_results",
        ):
            st.session_state.pop(key, None)
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
            "Baca hasil evaluasi tersimpan. Tidak menjalankan model atau mengirim request API."
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
        "Tanyakan hal baru tentang paper dalam korpus. Jawaban memakai bukti lokal; "
        "aktifkan izin API untuk membuat jawaban yang belum tersedia di cache."
    )
    limit = min(config.generation.max_calls_per_run, MAX_API_CALLS_PER_SUBMIT)
    with st.form("question_form"):
        question = st.text_area(
            "Pertanyaan riset", placeholder="Tulis pertanyaan tentang literatur dalam korpus"
        )
        default_mode = "hybrid+rerank" if config.retrieval.use_reranker else "hybrid"
        mode = st.selectbox("Metode retrieval", MODES, index=MODES.index(default_mode))
        allow_api = st.checkbox(
            f"Izinkan API berbayar saat cache kosong (maks. {limit} request per submit)",
            value=False,
            key="paid_api_permission",
            help="Cache selalu diperiksa lebih dulu. Izin berlaku untuk setiap klik Cari bukti.",
        )
        st.caption(
            f"Generator: {config.generation.model}. Pertanyaan dan chunk bukti dikirim ke "
            f"provider {config.generation.provider} jika API dipakai. "
            f"Batas output {config.generation.max_output_tokens} token per request. "
            "API key dibaca dari environment atau .env."
        )
        submitted = st.form_submit_button("Cari bukti", type="primary")
    if submitted:
        st.session_state.pop("query_answer", None)
        for key in (
            "quality_answer",
            "quality_result",
            "quality_api_permission",
            "diagnostic_results",
        ):
            st.session_state.pop(key, None)
        if not question.strip():
            st.error("Tulis pertanyaan sebelum mencari bukti.")
        else:
            try:
                with st.spinner("Mengambil bukti dan menyiapkan jawaban…"):
                    st.session_state["query_answer"] = run_question(
                        question.strip(), config, mode, allow_api=allow_api
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
