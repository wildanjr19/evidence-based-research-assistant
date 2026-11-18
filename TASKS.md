# TASKS.md

Milestone pengerjaan. Aturan: satu milestone selesai sebelum lanjut, dan "selesai" berarti acceptance criteria terpenuhi **dan** `pytest -q` + `ruff check .` bersih (AGENTS.md §12).

Spesifikasi teknis tiap milestone ada di `ARCHITECTURE.md`; jangan mengubah skema data atau format ID/sitasi selama implementasi tanpa memperbarui dokumen itu lebih dulu.

---

## M0 — Fondasi repo

**Deliverable:** `pyproject.toml`, `.gitignore`, `.env.example`, `configs/config.yaml`, `src/rag/__init__.py`, `src/rag/config.py`, `src/rag/ids.py`, `tests/test_ids.py`.

**Acceptance criteria:**

- [x] `uv sync` berhasil dari repo bersih.
- [x] `pytest -q` dan `ruff check .` lulus.
- [x] `config.py` memuat YAML dan memvalidasi kunci wajib; config yang cacat menimbulkan error jelas, bukan `KeyError`.
- [x] `ids.py` membuat dan memvalidasi ID sesuai regex di `ARCHITECTURE.md` §5, dengan test untuk ID valid dan tidak valid.
- [x] `data/`, `.env`, dan cache tidak akan ter-commit (pola diverifikasi dengan `git check-ignore`; pipeline belum tersedia).

**Verifikasi M0 (2026-11-18):** Python 3.11.0 / Windows; `python -m uv sync` berhasil membuat environment baru, `python -m uv sync --locked` berhasil; 93 test lulus pada jalur penuh dan `not gpu`; Ruff lint dan pemeriksaan format bersih. Perintah lengkap ada di README. CUDA, unduhan model, dan API LLM belum diuji.

**Dependensi (sudah disetujui):** runtime — `pyyaml`, `pymupdf`, `httpx`, `lancedb`, `sentence-transformers`, `torch`, `openai`, `streamlit`; dev — `pytest`, `ruff`.

Catatan: `torch` dari PyPI di Windows terpasang sebagai build CPU. Konfigurasi `embedding.device: cuda` baru bisa dipakai setelah build CUDA dipasang; sampai itu diverifikasi, jalankan dengan `device: cpu`. Dependensi lain di luar daftar ini tetap butuh konfirmasi (AGENTS.md §8).

---

## M1 — Ingestion metadata

**Deliverable:** klien sumber (arXiv untuk v1), penyimpanan metadata + lisensi ke tabel `paper`.

**Acceptance criteria:**

- [x] Bisa mengunduh metadata N paper untuk satu query domain, dengan batas jumlah dari config.
- [x] Setiap paper punya `license` terisi; paper tanpa lisensi jelas ditolak dengan log alasan.
- [x] Penulisan ulang paper yang sama bersifat idempoten.
- [x] Test memakai fixture respons API, tanpa jaringan.

**Verifikasi M1 (2026-11-18):** 130 test lulus pada jalur penuh dan `not gpu`; Ruff lint/format bersih. Fixture mencakup pagination, penolakan lisensi, ketidakcocokan versi, cache/jeda request, HTTP gagal, ukuran/header PDF, validasi kandidat, hash, dan idempotensi. Uji nyata satu kandidat pada query domain v1 berhasil melalui Discover + Fetch: `arxiv:2605.14488v1`, `CC-BY-4.0`. Data lokal berada di `data/m1-smoke/` dan diabaikan Git; korpus final belum dikumpulkan.

Karena skema mewajibkan hash PDF, metadata masuk JSONL dahulu dan baru disimpan ke `paper` setelah Fetch. Tidak ada perubahan skema. `max_papers` membatasi kandidat yang diperiksa, termasuk yang ditolak. Perintah CLI dan batas perilaku ada di README.

---

## M2 — Parsing dan chunking

**Deliverable:** parser PyMuPDF, section-aware chunker, tabel `chunk` terisi.

**Acceptance criteria:**

- [x] Setiap chunk punya `page_start`, `page_end`, `section` (bila terdeteksi), `n_tokens`.
- [x] Chunk di bawah `min_tokens` digabung atau dibuang, sesuai aturan di config.
- [x] Chunking deterministik: input sama → ID dan isi sama.
- [x] Test unit: chunking teks sintetis, termasuk teks dua kolom dan header/footer berulang.
- [x] Dilaporkan berapa paper gagal di-parse dan alasannya (`parse_status`).

**Verifikasi M2 (2026-11-18):** 165 test lulus pada jalur penuh dan `not gpu`; Ruff lint/format bersih. Uji lokal satu PDF nyata 16 halaman menghasilkan 20 chunk, 0 token leksikal terbuang, dan baris yang identik saat diulang. Artefak terverifikasi ada di `data/m2-smoke-v2/`; percobaan awal tetap disimpan, tanpa penghapusan data M1 atau chunk lama.

Default `lexical-v1` tidak mengklaim jumlah token model. `merge` hanya menggabungkan ekor dalam section yang sama dan dapat melebihi target; section pendek yang tidak dapat digabung dibuang. Jumlah token terbuang dicatat. M3 wajib memeriksa batas model embedding. OCR, layout kompleks, dan kalibrasi kualitas pada korpus penuh belum dilakukan.

---

## M3 — Indexing

**Deliverable:** embedding `bge-base-en-v1.5` ke vector store, indeks BM25/FTS5, embedding cache.

**Acceptance criteria:**

- [ ] Seluruh chunk terindeks; jumlah di vector store = jumlah di tabel `chunk`.
- [ ] Cache embedding mencegah perhitungan ulang saat run diulang.
- [ ] Waktu indexing dan jumlah token/embedding dicatat.
- [ ] Test yang butuh GPU diberi marker `gpu`; jalur default tetap lulus tanpa GPU.

---

## M4 — Retrieval

**Deliverable:** dense, BM25, RRF, reranker, orkestrasi dengan knob dari config.

**Acceptance criteria:**

- [ ] Empat konfigurasi bisa dijalankan: BM25, dense, hybrid, hybrid+rerank.
- [ ] RRF punya test unit dengan nilai yang sudah dihitung manual.
- [ ] Recall@5/10/20 dan MRR dihitung terhadap gold chunk pada set validasi kecil.
- [ ] Hasil per konfigurasi tersimpan per `run_id`, tidak saling menimpa.

---

## M5 — Generation dan sitasi

**Deliverable:** prompt grounding, klien LLM modular, validasi JSON klaim, render sitasi.

**Acceptance criteria:**

- [ ] Prompt hanya berisi chunk terambil; ada test yang memastikan tidak ada teks luar yang bocor ke prompt.
- [ ] Output LLM non-JSON atau ID tidak valid ditangani tanpa crash, dan dicatat sebagai kegagalan.
- [ ] Klaim tanpa sitasi valid dirender sebagai "tidak ada bukti", bukan dihapus.
- [ ] Test penuh memakai LLM mock; tidak ada panggilan API berbayar di test.
- [ ] Token in/out tiap panggilan tercatat.

---

## M6 — Verifikasi dan evaluasi

**Deliverable:** MiniCheck lokal, LLM-judge sampel, dataset 30–50 pertanyaan, skrip evaluasi, laporan run pertama.

**Acceptance criteria:**

- [ ] Dataset uji punya gold paper + gold chunk, dan tidak diubah setelah run pertama tanpa dicatat sebagai versi baru.
- [ ] Dataset memuat campuran lookup, comparison, synthesis, dan unanswerable (~10–15%), dengan jumlah per tipe dilaporkan.
- [ ] Pertanyaan unanswerable dinilai benar bila sistem menolak menjawab; klaim yang tetap muncul dihitung gagal.
- [ ] ID model MiniCheck diverifikasi ke Hugging Face sebelum dipakai, bukan diasumsikan dari nama di config.
- [ ] Metrik di `ARCHITECTURE.md` §9 dihitung otomatis dan ditulis ke `eval/results/<run_id>/`.
- [ ] Laporan mencantumkan `run_id`, `config_hash`, versi model, seed, jumlah pertanyaan.
- [ ] Label manual 50–100 pasangan klaim-chunk tersedia dan Cohen's kappa dihitung.

---

## M7 — UI dan dokumentasi

**Deliverable:** Streamlit app, README final, demo.

**Acceptance criteria:**

- [ ] UI menampilkan jawaban per klaim, kutipan chunk, nomor halaman, dan penanda klaim tanpa bukti.
- [ ] Tema UI mengikuti `DESIGN.md` (token yang tidak masuk akal diperbaiki dan dicatat di sana).
- [ ] README memuat arsitektur, keputusan desain, tabel hasil evaluasi, dan analisis kegagalan.
- [ ] Tidak ada secret, PDF, atau isi `data/` di repo.

---

## Backlog (v2, jangan dikerjakan sebelum M7)

- Tabel perbandingan metode antar paper.
- Evidence map.
- Dukungan multibahasa (`bge-m3`).
- GROBID sebagai parser utama untuk referensi dan section yang lebih akurat.
