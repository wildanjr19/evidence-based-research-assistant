# Evidence-Based Research Assistant

Sistem RAG lokal untuk literatur ilmiah: setiap klaim dalam jawaban menunjuk ke chunk sumber (paper, halaman, kutipan), dan ketepatan sitasinya diukur, bukan diklaim.

Status: **fondasi M0 diimplementasikan**: loader config bertipe dan utilitas ID beserta test unit. Pipeline ingestion, retrieval, generation, dan evaluasi belum tersedia. Belum ada angka evaluasi.

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

Verifikasi M0 pada Python 3.11.0 / Windows: sinkronisasi dari environment baru dan `uv sync --locked` berhasil, 93 test lulus (juga dengan marker `not gpu`), lint serta format bersih. Pola pengabaian data, secret, dan cache diperiksa dengan `git check-ignore`; belum ada pipeline untuk dijalankan.

## Data dan lisensi

Hanya paper open access. PDF, teks penuh, dan indeks tidak disimpan di repo; yang disimpan hanya ID/URL, metadata lisensi, dan skrip unduh.

## Hasil evaluasi

Belum ada. Tabel perbandingan BM25 vs dense vs hybrid vs hybrid+rerank akan diisi dari `eval/results/<run_id>/` setelah M6.
