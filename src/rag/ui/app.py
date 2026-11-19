import argparse
import logging
import sqlite3
from pathlib import Path

import streamlit as st

from rag.config import Config, load_config
from rag.retrieval.pipeline import MODES
from rag.ui.service import load_answer, load_demo, run_question, support_label

logger = logging.getLogger(__name__)
DEFAULT_DEMO = "eval/results/2026-11-19T01-25-11Z_7492c6"


def render_answer(answer: dict) -> None:
    st.subheader("Jawaban dan bukti", anchor=False)
    st.write(answer["question"])
    if answer["status"] == "failed":
        st.error(
            "Jawaban belum tersedia. Cache LLM mungkin belum berisi pertanyaan ini. "
            "Pilih demo tersimpan atau siapkan cache lewat CLI; UI tidak memanggil API."
        )
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
        "Retrieval dan MiniCheck berjalan lokal. Jawaban hanya dibaca dari cache LLM; "
        "pertanyaan baru dapat gagal bila respons belum tersimpan."
    )
    with st.form("question_form"):
        question = st.text_area(
            "Pertanyaan riset", placeholder="Tulis pertanyaan tentang literatur dalam korpus"
        )
        mode = st.selectbox("Metode retrieval", MODES, index=3)
        submitted = st.form_submit_button("Cari bukti", type="primary")
    if submitted:
        st.session_state.pop("query_answer", None)
        if not question.strip():
            st.error("Tulis pertanyaan sebelum mencari bukti.")
        else:
            try:
                with st.spinner("Mengambil chunk, membaca cache jawaban, dan memeriksa dukungan…"):
                    st.session_state["query_answer"] = run_question(question.strip(), config, mode)
            except (ValueError, RuntimeError, OSError, ImportError, sqlite3.Error):
                logger.exception("Local query failed")
                st.error(
                    "Pencarian lokal gagal. Periksa database, indeks, dan model di config; "
                    "lihat USAGE.md atau pilih demo tersimpan."
                )
    return st.session_state.get("query_answer")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Local evidence browser; no paid API calls")
    parser.add_argument("--config", default="configs/config.yaml")
    parser.add_argument("--demo-dir", default=DEFAULT_DEMO)
    args = parser.parse_args()
    main(args.config, args.demo_dir)
