# Evidence-Based Research Assistant

Sistem RAG lokal untuk literatur ilmiah: setiap klaim dalam jawaban menunjuk ke chunk sumber (paper, halaman, kutipan), dan ketepatan sitasinya diukur, bukan diklaim.

Status: **M0–M3 diimplementasikan**: fondasi config/ID, ingestion arXiv berlisensi, parsing PDF, chunking deterministik, embedding cache, serta indeks LanceDB dan SQLite FTS5. Retrieval, generation, dan evaluasi belum tersedia. Belum ada angka evaluasi.

## Dokumentasi

| File | Isi |
|---|---|
| `OVERVIEW.md` | Tujuan, stack, batasan, masalah dan solusinya |
| `ARCHITECTURE.md` | Arsitektur, skema data, format ID/sitasi, protokol evaluasi |
| `TASKS.md` | Milestone dan acceptance criteria |
| `DESIGN.md` | Token desain visual UI |
| `AGENTS.md` | Aturan kerja untuk AI coding agent |

## Rencana singkat

Ingestion paper open access → parsing → section-aware chunking → hybrid retrieval (BM25 + dense + RRF + rerank) → generasi bersitasi per klaim → verifikasi klaim (MiniCheck lokal + LLM-judge sampel) → evaluasi citation precision/recall.

## Setup

Gunakan Python 3.11+. Bila `uv` belum terpasang, jalankan `python -m pip install --user uv`.
Dari root repo (perintah ini juga bisa dipakai di PowerShell tanpa mengaktifkan virtual environment):

```bash
python -m uv sync --locked
python -m uv run python -m pytest -q
python -m uv run python -m pytest -q -m "not gpu"
python -m uv run ruff check .
python -m uv run ruff format --check .
```

`uv.lock` mengunci versi dependensi; `uv sync` membuat `.venv` dan memasang dependensi runtime serta dev yang sudah disetujui. Bentuk `python -m uv` bisa dipakai ketika executable `uv` belum ada di `PATH`.

Jika `.venv` sudah aktif, gunakan `python -m pytest`, `python -m ruff`, dan `python -m rag...` langsung. `uv` yang dipasang di Python luar tidak otomatis tersedia dalam `.venv`. Di Windows, `py -3.11 -m uv sync --locked` memanggil `uv` dari Python luar ketika environment aktif.

Pemanggilan `python -m pytest` digunakan karena kebijakan Application Control Windows pada mesin pengembangan memblokir launcher `pytest.exe`.

Config default memakai `embedding.device: cpu`. PyTorch CUDA telah dipasang manual dan operasi tensor GPU sudah diverifikasi pada mesin pengembangan; embedding nyata GPU belum diuji. `uv.lock` masih memakai sumber PyPI awal. `uv sync` atau `uv run` yang menyinkronkan environment dapat mengganti build CUDA; gunakan Python `.venv` langsung sampai sumber/lock CUDA dirapikan. Setup tidak mengunduh bobot model atau memanggil API LLM.

## Fondasi M0

```python
from rag.config import load_config
from rag.ids import make_chunk_id, make_paper_id

config = load_config("configs/config.yaml")
paper_id = make_paper_id("arxiv", "2401.12345v1")
chunk_id = make_chunk_id(paper_id, page=7, ordinal=3)
# arxiv:2401.12345v1:p7:c03
```

Jalankan kode melalui `python -m uv run python` agar package tersedia. Loader menolak kunci hilang/tidak dikenal, tipe salah, dan nilai di luar batas dengan `ConfigError`. Path di dalam YAML tetap relatif terhadap direktori kerja, bukan lokasi file config.

Validator ID memeriksa sintaks, versi arXiv, dan batas halaman/ordinal. Keberadaan chunk di database dan keanggotaannya dalam konteks retrieval harus diperiksa saat M5. Run ID memakai waktu UTC dan sufiks acak; penulisan hasil tanpa menimpa run lama diimplementasikan bersama evaluasi.

Verifikasi M0 pada Python 3.11.0 / Windows: sinkronisasi dari environment baru dan `uv sync --locked` berhasil, 93 test lulus (juga dengan marker `not gpu`), lint serta format bersih. Pola pengabaian data, secret, dan cache diperiksa dengan `git check-ignore`; pada tahap M0 pipeline belum tersedia.

## Data dan lisensi

Hanya paper open access. PDF, teks penuh, dan indeks tidak disimpan di repo; yang disimpan hanya ID/URL, metadata lisensi, dan skrip unduh.

## Ingestion M1

Atur bagian `ingestion` di `configs/config.yaml`, lalu jalankan tahap-tahap ini secara berurutan:

```bash
python -m uv run python -m rag.ingestion discover --config configs/config.yaml
python -m uv run python -m rag.ingestion fetch --config configs/config.yaml
```

`discover` mencari metadata lewat Atom API dan memeriksa lisensi lewat OAI-PMH `arXivRaw`, lalu menyimpan kandidat yang diterima ke `data/raw/candidates.jsonl`. `max_papers` membatasi jumlah hasil pencarian yang diperiksa, termasuk kandidat yang ditolak; jumlah paper diterima bisa lebih kecil. Default 10 kandidat ditujukan untuk uji awal, bukan korpus final 100–500 paper.

Default lisensi yang diterima: `CC-BY-4.0`, `CC-BY-3.0`, dan `CC0-1.0`. Lisensi hilang/tidak dikenal/di luar daftar ditolak dengan alasan di log. OAI-PMH hanya memberikan metadata versi terbaru, sehingga versi hasil pencarian wajib sama dengan versi terbaru pada riwayat OAI; sistem tidak menebak versi atau menerapkan lisensi terbaru pada versi lama. Referensi: [metadata OAI-PMH arXiv](https://info.arxiv.org/help/oa/index.html) dan [lisensi per versi](https://info.arxiv.org/help/license/index.html).

Request berlangsung satu per satu dengan jeda minimal 3 detik, sesuai [ketentuan API arXiv](https://info.arxiv.org/help/api/tou.html). Respons metadata di-cache per hari UTC di `data/cache/arxiv/`. Jangan menjalankan beberapa proses ingestion bersamaan. Timeout, batas ukuran PDF, dan jeda request tersedia di config; tidak ada retry otomatis untuk respons HTTP gagal.

`fetch` hanya mengunduh kandidat berlisensi yang diizinkan config, memeriksa header PDF serta ukuran maksimum, lalu menghitung SHA-256 dan menyimpan metadata ke tabel `paper` pada `data/index/corpus.db`. Hash tidak pernah diisi dengan placeholder. Nama file memakai `arxiv_<source_id>.pdf`, dengan `/` pada ID lama diganti `_` agar aman di Windows; ID kanonis di database tetap memakai format arsitektur.

Pengulangan memakai PDF lokal dan mempertahankan baris SQLite serta `parse_status`. Bila hash berbeda untuk versi paper yang sama, proses gagal tanpa memperbarui metadata atau menimpa file lama. Pemeriksaan struktur PDF lengkap ditunda ke parsing M2; M1 baru memeriksa header `%PDF-`.

Verifikasi M1 pada 2026-11-18: 130 test lulus (semua memakai respons lokal untuk ingestion), lint serta format bersih. Uji nyata dibatasi satu kandidat pada query domain v1: `arxiv:2605.14488v1` diterima dengan lisensi `CC-BY-4.0`, PDF terunduh dan metadata tersimpan. Artefak uji berada di `data/m1-smoke/`, diabaikan Git. Ini belum membuktikan kualitas seleksi atau cakupan korpus final.

## Parsing dan chunking M2

Jalankan M1 dengan config yang sama lebih dulu, lalu:

```bash
python -m uv run python -m rag.parsing --config configs/config.yaml
python -m uv run python -m rag.chunking --config configs/config.yaml
```

Kedua perintah mendukung `--paper-id arxiv:2401.12345v1` untuk satu paper. Perintah berjalan lokal, tanpa jaringan, model ML, GPU, atau API LLM.

Parser memakai posisi baris dan informasi font dari [PyMuPDF](https://pymupdf.readthedocs.io/en/latest/recipes-text.html). Ia mengurutkan dua kolom sederhana, menormalkan Unicode/whitespace, membuang teks margin yang berulang lintas halaman, serta mendeteksi heading umum/bernomor. Nomor halaman PDF tetap 1-indexed. Teks dan section disimpan ke `data/parsed/<safe_paper_id>.json` bersama hash dokumen, hash PDF, versi PyMuPDF, versi normalisasi, dan config parsing. `paper.parse_status` menjadi `ok` atau `failed`; alasan kegagalan tersimpan di laporan per run pada `data/parsed/reports/`.

Chunker menjaga batas section, rentang halaman, urutan global chunk per paper, dan overlap dari config. `chunking.tokenizer: lexical-v1` menghitung kata dan tanda baca dengan regex `\w+|[^\w\s]`. Angka `n_tokens` **bukan jumlah token model embedding/LLM**; pemeriksaan batas model menjadi pekerjaan M3. Tidak ada bobot model yang diunduh untuk M2.

`short_chunk_policy: merge` menggabungkan ekor pendek dengan chunk sebelumnya dalam section yang sama; hasil gabungan dapat melebihi `target_tokens`. Pilihan `drop` membuang token baru pada ekor pendek. Section yang seluruhnya lebih pendek dari `min_tokens` dibuang pada kedua kebijakan, karena tidak digabung melintasi section. Jumlah token unik yang dibuang dilaporkan. `quality_flag=low_quality` hanya menandai karakter pengganti Unicode atau kontrol yang rusak; belum menjadi ukuran kualitas parsing secara menyeluruh.

Pengulangan memakai hasil parsing dengan manifest yang sama dan memverifikasi kesamaan seluruh baris chunk. Bila input/config parsing atau isi chunk berbeda, proses menolak menimpa hasil lama. Gunakan `parsed_dir` dan database terpisah untuk eksperimen; penghapusan/rebuild data lama memerlukan persetujuan. Nama file tetap aman di Windows, sedangkan format ID/sitasi dan skema SQLite tidak berubah. Config M0/M1 tetap bisa dimuat; field M2 yang belum ada memakai default dan dicatat dalam config efektif laporan.

Verifikasi M2 pada 2026-11-18: 165 test lulus pada jalur penuh dan `not gpu`, lint serta format bersih. Test membuat PDF sintetis di direktori sementara, termasuk dua kolom, header/footer berulang, inline bold pada daftar bernomor, file rusak, dan halaman tanpa teks. Uji PDF nyata `arxiv:2605.14488v1` menghasilkan 20 chunk dari 16 halaman, tanpa token leksikal terbuang; pengulangan identik. Config, database salinan metadata M1, teks parsed, dan laporan berada di `data/m2-smoke-v2/` yang diabaikan Git. PDF asli dan database M1 dipertahankan. Percobaan awal dengan versi normalisasi lama tetap tersimpan di `data/m2-smoke/`.

OCR belum tersedia. Tabel, rumus, layout lebih dari dua kolom, serta heading yang tidak biasa belum divalidasi pada korpus besar. Keberhasilan satu PDF tidak mengukur akurasi sitasi atau kualitas retrieval.

## Indexing M3

Setelah M2, jalankan dengan config korpus yang sama:

```bash
python -m uv run python -m rag.indexing --config configs/config.yaml
```

Dalam `.venv` aktif, cukup `python -m rag.indexing --config configs/config.yaml`. Tahap ini memproses seluruh tabel `chunk`, termasuk `low_quality`; penyaringan kualitas dilakukan saat retrieval M4. Jalankan satu proses indexing pada satu korpus, tanpa ingestion/chunking bersamaan.

Embedder memakai [BAAI/bge-base-en-v1.5](https://huggingface.co/BAAI/bge-base-en-v1.5) berlisensi MIT melalui sentence-transformers. `embedding.revision` mengunci commit model, default `a5beb1e3e68b9ab74eb54cfd186867f64f240e1a`; `max_tokens: 512` membatasi input termasuk special tokens. Embedding dokumen tidak memakai prefix query, memakai float32, dan dinormalisasi. Bobot diunduh ke `paths.cache_dir/models/` pada penggunaan pertama. Tidak ada API LLM berbayar yang dipanggil.

M3 menghitung token dengan tokenizer model sebelum encoding. Chunk yang melebihi batas ditolak dengan ID dan jumlah tokennya; teks tidak dipotong. Target 400 token leksikal M2 tidak menjamin muat dalam 512 token model. Bila terjadi penolakan, buat database chunk baru dengan target lebih kecil. Jangan mengganti teks atau menghapus chunk pada database lama.

Vektor dan metadata ID/paper/halaman/section/kualitas disimpan dalam tabel `chunks` di `paths.index_dir/vectors.lance/`. Manifest mengunci identitas model dan dimensi. `chunk_fts` adalah virtual table FTS5 dalam database korpus, dengan tokenizer `unicode61 remove_diacritics 2`. Tokenizer ini sudah diuji terhadap pencarian huruf beraksen. SQLite `bm25()` menghasilkan skor lebih kecil untuk hasil lebih baik. Skema inti `paper`/`chunk` dan ID sitasi tetap sama.

Cache embedding berada di `paths.cache_dir/embeddings/`, berdasarkan hash teks dan identitas model, revision, dimensi, batas token, normalisasi, serta prefix dokumen. Teks identik berbagi satu cache. Pengulangan memuat cache dan hanya menambah baris indeks yang belum ada. Cache rusak, metadata indeks berbeda, atau manifest model berubah ditolak tanpa penggantian otomatis. Run parsial dapat dilanjutkan dengan input yang sama; penulisan LanceDB dan FTS5 tidak berada dalam satu transaksi bersama.

Laporan baru di `paths.index_dir/reports/` mencatat config efektif dan hash, seed, versi library, identitas model, jumlah chunk/vektor/FTS, waktu, token model, embedding baru, dan cache hit. Token model mencakup seluruh chunk; `computed_tokens` hanya menghitung teks unik yang baru di-encode. Waktu mencakup pemuatan model dan unduhan bila diperlukan. Kegagalan juga dilaporkan. Run lama tidak ditimpa.

Verifikasi M3 pada 2026-11-18: 185 test lulus dan satu test GPU dilewati pada build CPU; Ruff lint/format bersih. Test menggunakan embedder mock bersama LanceDB dan SQLite FTS5 nyata, tanpa unduhan model/API. Uji model nyata pada CPU memakai paper M2 dan database baru di `data/m3-smoke/`: target 380 token leksikal menghasilkan 21 chunk, maksimum 491 token model. Jumlah di SQLite, LanceDB, dan FTS5 sama-sama 21. Run pertama menghitung 21 embedding/8.758 token dalam 20,38 detik. Pengulangan offline menghitung nol embedding, memakai 21 cache, dan selesai 6,00 detik. Ini uji satu paper, bukan benchmark korpus penuh. Database M2 asli tetap berisi 20 chunk; satu chunk lamanya berisi 514 token model dan tidak diubah.

PyTorch dan LanceDB sudah berhasil diimpor setelah blokir Windows ditangani manual. Pengguna kemudian memasang PyTorch `2.15.0+cu132`; CUDA aktif pada RTX 3060 Ti 8 GB. Verifikasi ulang menghasilkan 186 test lulus, termasuk operasi tensor GPU; Ruff lint/format bersih. Embedding BGE nyata masih baru diuji pada CPU. Config default tetap `device: cpu`; permintaan `device: cuda` gagal dengan pesan jelas bila CUDA tidak tersedia.

M3 ditutup pada 2026-11-18. Catatan handoff sesi berikutnya ada pada bagian M3 di `TASKS.md`: rapikan sumber/lock CUDA dan uji embedding GPU bila dipakai, lalu lanjut M4. Hasil CPU/corpus lama dipertahankan; uji GPU harus memakai cache/direktori baru untuk membuktikan encoding nyata, bukan hanya membaca cache CPU.

## Hasil evaluasi

Belum ada. Tabel perbandingan BM25 vs dense vs hybrid vs hybrid+rerank akan diisi dari `eval/results/<run_id>/` setelah M6.
