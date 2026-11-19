import argparse
import logging
import sqlite3
from pathlib import Path

import streamlit as st

from rag.config import Config, load_config
from rag.retrieval.pipeline import MODES
from rag.ui.service import (
    MAX_API_CALLS_PER_SUBMIT,
    load_answer,
    load_demo,
    run_question,
    support_label,
)

logger = logging.getLogger(__name__)
DEFAULT_DEMO = "eval/results/2026-11-19T01-25-11Z_7492c6"


def render_answer(answer: dict) -> None:
    st.subheader("Jawaban dan bukti", anchor=False)
    st.write(answer["question"])
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
                "jawaban baru, atau pilih demo tersimpan. Periksa laporan run jika cache rusak."
            )
        if answer.get("report_path"):
            st.text(f"Laporan lokal: {answer['report_path']}")
        return
    if not answer["claims"]:
        st.info(
            "Tidak ada bukti pada korpus untuk pertanyaan ini. Coba pertanyaan yang lebih spesifik."
        )
    references = {ref["chunk_id"]: ref for ref in answer["references"]}
    for claim in answer["claims"]:
        st.divider()
        label = support_label(claim, answer["verification"])
        st.markdown(f"**Klaim {claim['claim_order']} · {label}**")
        st.text(claim["text"])
        for identifier in claim["citations"]:
            ref = references[identifier]
            pages = str(ref["page_start"])
            if ref["page_end"] != ref["page_start"]:
                pages += f"–{ref['page_end']}"
            with st.expander(f"[{ref['number']}] {ref['title']} · hal. {pages}"):
                st.caption(f"{identifier} · {ref['section'] or 'Section tidak tersedia'}")
                with st.container(key=f"quote_{claim['claim_order']}_{ref['number']}"):
                    st.text(ref["quote"])
                st.caption(f"Lisensi: {ref['license']}")
                if ref["url"]:
                    st.link_button("Buka paper sumber", ref["url"])
                for result in answer["verification"]:
                    if result["claim_id"] != claim["claim_id"] or result["chunk_id"] != identifier:
                        continue
                    st.caption(f"{result['verifier']}: {result['label'] or 'belum diverifikasi'}")
                    if result.get("rationale"):
                        st.text(result["rationale"])
    st.caption(
        "Label otomatis perlu diperiksa dengan membaca kutipan; label bukan penilaian manusia."
    )
    with st.expander("Catatan jawaban"):
        st.text(f"Run: {answer['run_id']}\nGenerator: {answer['model']}")
        if answer.get("report_path"):
            st.text(f"Laporan lokal: {answer['report_path']}")


def main(config_path: str = "configs/config.yaml", demo_dir: str = DEFAULT_DEMO) -> None:
    st.set_page_config(
        page_title="Bukti Riset | Evidence-Based Research Assistant", layout="centered"
    )
    st.html(Path(__file__).with_name("style.css"))
    st.html("<script>document.documentElement.lang = 'id';</script>", unsafe_allow_javascript=True)
    st.title("Baca klaim. Periksa buktinya.", anchor=False)
    st.write("Evidence-Based Research Assistant · Literatur RAG evaluation")
    try:
        config = load_config(config_path)
    except (ValueError, OSError):
        st.error("Config tidak dapat dibaca. Periksa path --config dan panduan USAGE.md.")
        return
    mode = st.radio("Sumber jawaban", ["Demo tersimpan", "Tanya korpus"], horizontal=True)
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
                "Demo tidak cocok atau belum tersedia. Gunakan database M6 yang sesuai dengan "
                "--demo-dir, lalu periksa perintah di USAGE.md."
            )
    else:
        answer = query_form(config)
    if answer is not None:
        render_answer(answer)


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
        mode = st.selectbox("Metode retrieval", MODES, index=3)
        allow_api = st.checkbox(
            f"Izinkan API berbayar saat cache kosong (maks. {limit} request per submit)",
            value=False,
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
        if not question.strip():
            st.error("Tulis pertanyaan sebelum mencari bukti.")
        else:
            try:
                with st.spinner("Mengambil bukti, menyiapkan jawaban, dan memeriksa dukungan…"):
                    st.session_state["query_answer"] = run_question(
                        question.strip(), config, mode, allow_api=allow_api
                    )
            except (ValueError, RuntimeError, OSError, ImportError, sqlite3.Error):
                logger.exception("Local query failed")
                st.error(
                    "Pencarian lokal gagal. Periksa database, indeks, dan model di config; "
                    "lihat USAGE.md atau pilih demo tersimpan."
                )
    return st.session_state.get("query_answer")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Local evidence browser with optional bounded API")
    parser.add_argument("--config", default="configs/config.yaml")
    parser.add_argument("--demo-dir", default=DEFAULT_DEMO)
    args = parser.parse_args()
    main(args.config, args.demo_dir)
