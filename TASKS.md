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

**Verifikasi M0 (2026-11-18):** Python 3.11.0 / Windows; `python -m uv sync` berhasil membuat environment baru, `python -m uv sync --locked` berhasil; 93 test lulus pada jalur penuh dan `not gpu`; Ruff lint dan pemeriksaan format bersih. Perintah lengkap ada di [USAGE.md](USAGE.md). CUDA, unduhan model, dan API LLM belum diuji pada tahap M0.

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

Karena skema mewajibkan hash PDF, metadata masuk JSONL dahulu dan baru disimpan ke `paper` setelah Fetch. Tidak ada perubahan skema. `max_papers` membatasi kandidat yang diperiksa, termasuk yang ditolak. Perintah CLI dan batas perilaku ada di [USAGE.md](USAGE.md).

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

Test memakai PDF sintetis di direktori sementara, termasuk dua kolom, header/footer berulang, inline bold pada daftar bernomor, file rusak, dan halaman tanpa teks. PDF nyata yang diuji adalah `arxiv:2605.14488v1`; config, database salinan metadata M1, teks parsed, dan laporan ada di `data/m2-smoke-v2/`. Percobaan versi normalisasi awal tetap tersimpan di `data/m2-smoke/`.

Default `lexical-v1` tidak mengklaim jumlah token model. `merge` hanya menggabungkan ekor dalam section yang sama dan dapat melebihi target; section pendek yang tidak dapat digabung dibuang. Jumlah token terbuang dicatat. M3 wajib memeriksa batas model embedding. OCR, layout kompleks, dan kalibrasi kualitas pada korpus penuh belum dilakukan.

---

## M3 — Indexing

**Deliverable:** embedding `bge-base-en-v1.5` ke vector store, indeks BM25/FTS5, embedding cache.

**Acceptance criteria:**

- [x] Seluruh chunk terindeks; jumlah di vector store = jumlah di tabel `chunk`.
- [x] Cache embedding mencegah perhitungan ulang saat run diulang.
- [x] Waktu indexing dan jumlah token/embedding dicatat.
- [x] Test yang butuh GPU diberi marker `gpu`; jalur default tetap lulus tanpa GPU.

**Verifikasi awal M3 (2026-11-18):** 185 test lulus, satu test GPU dilewati karena PyTorch CPU; Ruff lint/format bersih. Test memakai embedder mock dan LanceDB/FTS5 nyata, mencakup cache, deduplikasi/batch, special tokens, penolakan truncation, cache rusak, kelanjutan indeks parsial, konflik metadata/model, dan laporan run unik. Uji BGE nyata pada CPU menghasilkan 21 baris SQLite = 21 vektor = 21 FTS5 pada database baru `data/m3-smoke/`. Run pertama: 21 embedding, 8.758 token model, 20,38 detik termasuk pemuatan model/unduhan. Pengulangan offline: 21 cache hit, nol embedding/token baru, 6,00 detik. Target eksperimen diturunkan menjadi 380 token leksikal; maksimum input 491 token model. Data M2 dipertahankan, termasuk chunk lama 514 token yang melebihi batas BGE 512. Korpus penuh dan kualitas retrieval belum dievaluasi.

**Penutupan M3 (2026-11-18):** seluruh acceptance criteria terpenuhi. Pengguna memasang PyTorch `2.15.0+cu132`; CUDA aktif pada RTX 3060 Ti 8 GB. Verifikasi ulang: 186 test lulus, termasuk operasi tensor GPU; Ruff lint/format bersih. Embedding BGE nyata masih baru diuji pada CPU. Config default tetap CPU dan `uv.lock` belum mengunci varian CUDA yang dipasang manual.

PyTorch dan LanceDB berhasil diimpor setelah blokir Windows ditangani manual. Keberhasilan uji satu paper belum menjadi benchmark korpus penuh atau ukuran kualitas retrieval/sitasi.

**Handoff sesi berikutnya:** baca AGENTS.md, README, [USAGE.md](USAGE.md), ARCHITECTURE, dan bagian M4 di bawah. Perubahan M3 masih ada di working tree, belum di-commit saat penutupan. Gunakan `.venv/Scripts/python.exe` langsung; hindari sinkronisasi environment sebelum memutuskan sumber/lock CUDA karena dapat mengganti build GPU. Jika ingin memakai GPU, rapikan konfigurasi/lock dan lakukan uji embedding nyata ke direktori eksperimen baru; cache CPU tidak membuktikan encoding GPU. Setelah itu lanjut M4: dense, BM25, RRF, reranker, dan Recall@k/MRR pada set validasi kecil. Jangan mengubah data M2/M3 atau dataset evaluasi untuk memperbaiki hasil. Pada penutupan M3, implementasi M4–M7 belum tersedia; status terkini ada pada bagian milestone masing-masing.

---

## M4 — Retrieval

**Deliverable:** dense, BM25, RRF, reranker, orkestrasi dengan knob dari config.

**Acceptance criteria:**

- [x] Empat konfigurasi bisa dijalankan: BM25, dense, hybrid, hybrid+rerank.
- [x] RRF punya test unit dengan nilai yang sudah dihitung manual.
- [x] Recall@5/10/20 dan MRR dihitung terhadap gold chunk pada set validasi kecil.
- [x] Hasil per konfigurasi tersimpan per `run_id`, tidak saling menimpa.

**Verifikasi M4 (2026-11-18):** 219 test lulus; Ruff lint dan format bersih. Test memakai LanceDB/FTS5 nyata, embedding/reranker mock, serta fixture lokal tanpa jaringan/API berbayar. Cakupan meliputi RRF dan metrik dengan hitungan manual, empat mode, filter kualitas sebelum cutoff, ID/teks chunk kanonis, cache query/pasangan, batas token, indeks parsial/berbeda, skor tidak valid, validasi gold set, laporan gagal, tabrakan run ID, dan dispatch/error CLI. Wrapper reranker diperiksa dengan model/tokenizer mock, termasuk revision, raw logit, dan truncation dokumen saja.

Validasi sintetis terpisah memakai 30 chunk (satu `low_quality`) dan lima pertanyaan, termasuk comparison, synthesis, dan unanswerable. Keempat mode berhasil menghasilkan run terpisah di `data/m4-validation/2026-11-18T06-02-41Z_be478e/results/`; backend mock dicatat di manifest. Ini verifikasi logika/alur, bukan ukuran kualitas model. Fixture berada di `tests/fixtures/retrieval_questions.jsonl`; gold set final `eval/` belum dibuat atau diubah.

**Smoke test CPU awal (tanpa reranker):** BGE dari cache offline dipakai pada indeks M3 berisi 21 chunk dari satu paper, dengan lima pertanyaan lookup dan gold chunk yang dipilih sebelum retrieval. Config, dataset validasi lokal, dan laporan ada di `data/m4-smoke/2026-11-18T06-00-30Z_4cfc6b/`. Hash database sebelum/sesudah sama; tabel vektor tetap versi 1. Pengulangan memakai cache query tanpa encoding baru.

| Mode | Recall@5 | Recall@10 | Recall@20 | MRR (kedalaman 20) |
|---|---|---|---|---|
| BM25 | 0.8 | 1.0 | 1.0 | 0.7250 |
| Dense | 0.8 | 1.0 | 1.0 | 0.5952 |
| Hybrid | 1.0 | 1.0 | 1.0 | 0.7067 |

Run CPU dengan manifest akhir: BM25 `2026-11-18T06:02:44Z_972e53`, dense `2026-11-18T06:02:44Z_000659`, hybrid `2026-11-18T06:02:50Z_2c6f0e`. Angka satu paper/lima pertanyaan ini belum membuktikan keunggulan hybrid pada korpus penuh atau ketepatan sitasi.

**Verifikasi reranker nyata CPU (2026-11-18):** `BAAI/bge-reranker-base` revision `2cfc18c9415c912f9d8155881c133215df768a70` berhasil dimuat melalui wrapper produksi, tanpa mock. Enam file model/tokenizer (1.134.374.819 byte) diunduh ke cache model; persiapan termasuk hash file selesai dalam 15,71 detik. Setelah itu, inference pertama dan pengulangan dijalankan offline dengan dataset lima pertanyaan yang sama, tanpa perubahan gold.

Run pertama menghitung 105 pasangan (21 kandidat per pertanyaan), dengan nol cache hit reranker. Semua ranking evaluasi berisi 20 ID unik dengan skor finite yang terurut menurun. Top-1 berubah pada kelima pertanyaan. Pengulangan di proses baru menghitung nol pasangan/embedding query baru, memakai 105 cache hit, dan menghasilkan ranking serta skor identik. Backend reranker tidak dimuat pada pengulangan karena semua skor tersedia di cache. Hash database dan seluruh file indeks vektor sebelum/sesudah sama.

| Run CPU | Recall@5/10/20 | MRR (kedalaman 20) | Waktu run |
|---|---|---|---|
| Hybrid pembanding | 1.0 / 1.0 / 1.0 | 0.7067 | 6,09 detik |
| Hybrid+rerank, 105 pasangan baru | 1.0 / 1.0 / 1.0 | 0.5667 | 21,91 detik |
| Hybrid+rerank, cache offline | 1.0 / 1.0 / 1.0 | 0.5667 | 6,35 detik |

Waktu hybrid mencakup pemuatan embedding; run reranker pertama mencakup pemuatan reranker, dengan embedding sudah dimuat. Pengulangan memakai proses baru dan tetap memuat embedding untuk memeriksa identitas indeks. Angka ini bukan benchmark latensi yang memisahkan waktu model dari startup.

Puncak working set proses pengujian pertama adalah 3,07 GiB; puncak private commit 5,15 GiB. Proses pengulangan mencapai 1,26 GiB working set. Pengukuran memakai [Windows process memory counters](https://learn.microsoft.com/en-us/windows/win32/api/psapi/ns-psapi-process_memory_counters_ex), mencakup runtime, embedding, dan reranker; bukan RAM reranker saja atau VRAM.

Peringkat gold untuk lima pertanyaan berubah dari `[1, 3, 1, 1, 5]` menjadi `[2, 1, 3, 2, 2]`. MRR turun, meskipun semua gold tetap ditemukan dalam top-5. Dataset dan label tidak diubah untuk meningkatkan skor. Sampel satu paper ini belum cukup untuk memilih konfigurasi terbaik; perbandingan kualitas tetap menjadi pekerjaan M6.

Artefak baru ada di `data/m4-reranker-smoke/2026-11-18T07-06-30Z_b88c51/`: config, salinan dataset dengan hash sama, skrip `smoke.py`, `download-evidence.json`, `first-evidence.json`, `repeat-evidence.json`, dan laporan per run. Run hybrid: `2026-11-18T07:08:31Z_072b8f`; reranker pertama: `2026-11-18T07:08:37Z_122a4b`; cache offline: `2026-11-18T07:09:22Z_3084e3`. Semua artefak/model berada di `data/` yang diabaikan Git. Verifikasi repo: 219 test lulus, Ruff lint/format bersih.

**Batas verifikasi:** embedding query/reranker GPU dan benchmark korpus penuh belum diuji. Tidak ada dependensi baru, perubahan skema SQLite/ID/sitasi, sinkronisasi environment CUDA, atau panggilan LLM. Smoke test CPU reranker nyata sudah selesai.

**Handoff M5:** panduan CLI retrieval/evaluasi ada di [USAGE.md](USAGE.md). Implementasikan grounding prompt, klien LLM modular, validasi JSON klaim/sitasi, serta test LLM mock sesuai bagian M5. Gunakan `.venv/Scripts/python.exe` langsung; sumber/lock CUDA masih perlu dirapikan bila GPU akan dipakai. Bobot reranker CPU sudah tersedia di cache. Untuk menguji GPU, gunakan cache eksperimen baru agar membuktikan inference nyata, lalu simpan hasil sebagai run baru. Korpus M2/M3 dan hasil M4 tetap dipertahankan.

---

## M5 — Generation dan sitasi

**Deliverable:** prompt grounding, klien LLM modular, validasi JSON klaim, render sitasi.

**Acceptance criteria:**

- [x] Prompt hanya berisi chunk terambil; ada test yang memastikan tidak ada teks luar yang bocor ke prompt.
- [x] Output LLM non-JSON atau ID tidak valid ditangani tanpa crash, dan dicatat sebagai kegagalan.
- [x] Klaim tanpa sitasi valid dirender sebagai "tidak ada bukti", bukan dihapus.
- [x] Test penuh memakai LLM mock; tidak ada panggilan API berbayar di test.
- [x] Token in/out tiap panggilan tercatat.

**Verifikasi M5 (2026-11-18):** 268 test lulus; Ruff lint/format bersih. Test mencakup prompt tanpa teks chunk di luar retrieval, JSON/schema/Unicode invalid, sintaks/keberadaan/keanggotaan ID, deduplikasi sitasi, klaim unsupported, rendering metadata kanonis, cache/provenance, satu retry format, batas panggilan, respons terpotong, usage hilang/invalid, error tanpa bocor key, konflik skema, kegagalan SQLite, run collision, integrasi FTS, dan CLI. SDK OpenAI nyata diuji dengan transport HTTP mock untuk DeepSeek/OpenAI; request/token usage diperiksa, termasuk HTTP 500 tanpa retry SDK. Tidak ada jaringan/provider berbayar pada test.

**Smoke test M5:** salinan database dan indeks M3 dibuat di `data/m5-smoke/2026-11-18T08-20-39Z_028e06/`. Retrieval memakai embedding dan reranker CPU nyata dari cache offline; generator memakai `FixtureLLM`, bukan provider API. Pertanyaan baru mengambil delapan chunk; satu klaim fixture bersitasi ke `arxiv:2605.14488v1:p7:c11`, satu klaim fixture tanpa bukti mempertahankan label unsupported. Kutipan/judul/halaman berasal dari database. Panggilan backend API nyata diblokir pada skrip smoke.

Run pertama `2026-11-18T08:21:57Z_58718c` menyimpan satu run, satu answer, dan dua claim pada tabel sesuai arsitektur. Pengulangan proses baru `2026-11-18T08:22:54Z_07f2d8` memakai satu cache hit LLM, nol panggilan backend baru, serta menghasilkan Markdown/referensi identik; total menjadi dua run, dua answer, empat claim. Foreign key check bersih. Hash database/seluruh file indeks M3 asli tetap sama; baris paper/chunk/FTS pada salinan eksperimen juga tetap sama. Token dari mock adalah fixture nol, bukan pengukuran tokenizer/usage layanan nyata. Jumlah panggilan API berbayar: nol.

| Proses smoke M5 | Waktu seluruh alur | Puncak working set | Puncak private commit | Puncak VRAM PyTorch |
|---|---|---|---|---|
| Retrieval/reranker CPU nyata + LLM mock | 12,55 detik | 3,03 GiB | 5,04 GiB | 0 byte |
| Pengulangan dengan cache | 6,28 detik | 1,26 GiB | 3,07 GiB | 0 byte |

RAM diukur dengan Windows process memory counters dan mencakup runtime, embedding, reranker, serta pipeline. VRAM adalah alokasi allocator PyTorch proses ini; CUDA tidak diinisialisasi. Angka nol bukan pengukuran pemakaian seluruh GPU oleh Windows/proses lain. Waktu mencakup retrieval/pemuatan model dan penyimpanan; belum mencakup latensi API LLM nyata. `generation.elapsed_seconds` hanya mengukur tahap generation setelah retrieval; tabel di atas memakai pengukuran seluruh alur pada skrip smoke.

Config, salinan data, skrip `smoke.py`, `first-evidence.json`, `repeat-evidence.json`, dan laporan generation tersimpan di direktori smoke tersebut, diabaikan Git. Tidak ada dependensi baru, sinkronisasi CUDA, perubahan format sitasi, atau perubahan baris korpus/dataset evaluasi.

**Batas verifikasi:** LLM/provider API nyata, biaya/token aktual provider, dukungan semantik klaim, GPU, dan korpus penuh belum diuji. Config masih `deepseek-chat`; dokumentasi DeepSeek yang diperiksa kini mencantumkan `deepseek-flash` dan `deepseek-v4-pro`, sehingga alias awal perlu dikonfirmasi sebelum API berbayar. API key tidak dibaca dari `.env` otomatis.

**Handoff M6:** implementasikan verifier lokal, runner evaluasi sitasi, dataset/gold set versi pertama sesuai protokol, dan laporan metrik. Pertahankan dataset yang sudah diberi label; jangan mengubah label untuk menaikkan skor. Validasi ID M5 bukan verifikasi bahwa teks chunk mendukung klaim. Sebelum memakai LLM live, pilih model yang tersedia dan lakukan smoke test berbayar terbatas lewat perintah eksplisit; pemilihan provider berdasarkan biaya/latensi masih terbuka. Untuk GPU, rapikan sumber/lock CUDA dan gunakan cache eksperimen baru agar membuktikan inference nyata.

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
- [ ] README memperkenalkan proyek dan menautkan panduan penggunaan, arsitektur/keputusan desain, serta laporan evaluasi dan analisis kegagalan di `eval/results/<run_id>/`.
- [ ] Tidak ada secret, PDF, atau isi `data/` di repo.

---

## Backlog (v2, jangan dikerjakan sebelum M7)

- Tabel perbandingan metode antar paper.
- Evidence map.
- Dukungan multibahasa (`bge-m3`).
- GROBID sebagai parser utama untuk referensi dan section yang lebih akurat.
