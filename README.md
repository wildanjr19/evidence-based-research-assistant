# Evidence-Based Research Assistant

Sistem RAG lokal untuk literatur ilmiah: setiap klaim dalam jawaban menunjuk ke chunk sumber (paper, halaman, kutipan), dan ketepatan sitasinya diukur, bukan diklaim.

Status: **tahap perancangan**. Belum ada pipeline yang berjalan. Belum ada angka evaluasi.

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

```bash
uv sync
pytest -q
ruff check . && ruff format --check .
```

`torch` dari PyPI di Windows adalah build CPU. Jalankan dengan `embedding.device: cpu`, atau pasang build CUDA lebih dulu lalu ubah config. Perintah ingestion/indexing/evaluasi di `AGENTS.md` §2 akan gagal sampai milestone terkait selesai.

## Data dan lisensi

Hanya paper open access. PDF, teks penuh, dan indeks tidak disimpan di repo; yang disimpan hanya ID/URL, metadata lisensi, dan skrip unduh.

## Hasil evaluasi

Belum ada. Tabel perbandingan BM25 vs dense vs hybrid vs hybrid+rerank akan diisi dari `eval/results/<run_id>/` setelah M6.
