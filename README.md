# Evidence-Based Research Assistant

Sistem RAG lokal untuk literatur ilmiah: setiap klaim dalam jawaban menunjuk ke chunk sumber (paper, halaman, kutipan), dan ketepatan sitasinya diukur, bukan diklaim.

Status: **M0 dan M1 diimplementasikan**: fondasi config/ID, discovery arXiv dengan pemeriksaan lisensi, unduhan PDF, dan metadata SQLite. Parsing, retrieval, generation, dan evaluasi belum tersedia. Belum ada angka evaluasi.

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

Pemanggilan `python -m pytest` digunakan karena kebijakan Application Control Windows pada mesin pengembangan memblokir launcher `pytest.exe`.

Config default memakai `embedding.device: cpu`. CUDA belum diverifikasi; pasang build CUDA dan periksa perangkat sebelum mengganti config. Setup tidak mengunduh bobot model atau memanggil API LLM.

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

## Hasil evaluasi

Belum ada. Tabel perbandingan BM25 vs dense vs hybrid vs hybrid+rerank akan diisi dari `eval/results/<run_id>/` setelah M6.
