# Evidence-Based Research Assistant

Asisten riset literatur ilmiah yang dirancang untuk menjawab pertanyaan dengan bukti yang bisa ditelusuri sampai ke paper, halaman, dan kutipan aslinya.

Proyek ini memakai Retrieval-Augmented Generation (RAG): sistem mengambil potongan teks (chunk) dari korpus, lalu menyusun jawaban berdasarkan bukti tersebut. Setiap klaim wajib memiliki sitasi chunk yang valid atau diberi label "tidak ada bukti". Ketepatan sitasinya akan diukur melalui evaluasi.

## Ruang lingkup

Versi pertama berfokus pada literatur **RAG evaluation** dari arXiv, dengan target 100 sampai 500 paper open access berlisensi yang diizinkan. Sistem ditujukan untuk membantu peneliti menelusuri fakta, membandingkan temuan, dan menyintesis bukti lintas paper.

Parsing, indexing, retrieval, dan verifikasi dirancang berjalan lokal; generasi jawaban memakai API LLM. PDF, teks penuh, indeks, dan cache tidak disimpan di Git.

## Alur sistem

```text
Paper open access -> Parsing PDF -> Chunking -> Embedding + indeks BM25
                                                       |
Pertanyaan -> Hybrid retrieval + rerank -> Jawaban bersitasi -> Verifikasi
```

Stack utama: Python, PyMuPDF, BGE, LanceDB, dan SQLite FTS5. UI direncanakan memakai Streamlit. Rincian komponen dan keputusan desain ada di [ARCHITECTURE.md](ARCHITECTURE.md).

## Status

**M0 sampai M5 sudah diimplementasikan:** ingestion, parsing, chunking, indexing, retrieval dengan reranker opsional, evaluasi retrieval, serta generasi JSON klaim dengan validasi sitasi dan cache respons.

Retrieval dengan embedding/reranker nyata diuji pada satu paper di CPU; generasi diuji dengan LLM mock dan satu pertanyaan melalui DeepSeek Flash API nyata. Verifikasi dukungan klaim, evaluasi sitasi, UI, korpus final, dan dataset evaluasi final belum tersedia. Hasil verifikasi ada di [TASKS.md](TASKS.md).

## Mulai dan dokumentasi

Untuk menyiapkan environment dan menjalankan pipeline, ikuti [panduan penggunaan](USAGE.md). Catatan environment CUDA ada di bagian setup panduan tersebut.

| Dokumen | Isi |
|---|---|
| [USAGE.md](USAGE.md) | Setup, perintah pipeline, dan batas penggunaan |
| [OVERVIEW.md](OVERVIEW.md) | Tujuan, ruang lingkup, pilihan stack, dan batasan proyek |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Arsitektur, skema data, format sitasi, dan protokol evaluasi |
| [TASKS.md](TASKS.md) | Milestone, acceptance criteria, hasil verifikasi, dan handoff |
| [DESIGN.md](DESIGN.md) | Sistem desain visual UI |
| [AGENTS.md](AGENTS.md) | Aturan kerja untuk AI coding agent |
