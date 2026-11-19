# Evidence-Based Research Assistant

Asisten riset literatur ilmiah yang dirancang untuk menjawab pertanyaan dengan bukti yang bisa ditelusuri sampai ke paper, halaman, dan kutipan aslinya.

Proyek ini memakai Retrieval-Augmented Generation (RAG): sistem mengambil potongan teks (chunk) dari korpus, lalu menyusun jawaban berdasarkan bukti tersebut. Setiap klaim wajib memiliki sitasi chunk yang valid atau diberi label "tidak ada bukti". Ketepatan sitasinya diukur melalui evaluasi.

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

**M0 sampai M6 selesai untuk benchmark awal:** ingestion, parsing, chunking, indexing, retrieval, generation bersitasi, MiniCheck lokal, dan judge generatif GPT-4o-mini melalui Surplus.

Dataset yang ditinjau pengguna berisi 30 pertanyaan lintas empat paper berlisensi, dengan 236 chunk. [Laporan M6](eval/results/2026-11-19T01-25-11Z_7492c6/m6-summary.md) memuat hasil, biaya estimasi, pengulangan dari cache, serta analisis kegagalan. Label manusia 52 pasangan dari eksperimen satu paper dilaporkan terpisah; accuracy terhadap manusia pada klaim generation baru belum diukur. UI M7, target korpus 100–500 paper, dan inference model di GPU belum dikerjakan. Catatan verifikasi dan handoff ada di [TASKS.md](TASKS.md).

Pilot [Jev dibandingkan dengan MiniCheck](eval/results/2026-11-18T11-50-46Z_ad072b/report.md)
memeriksa 12 pasangan kandidat klaim–chunk dari satu paper. Jev menjawab seluruh
pasangan; MiniCheck memeriksa 10 dan menolak dua input yang melewati batas token.
Keduanya sepakat pada 10 pasangan yang dapat dibandingkan. Laporan menyimpan
probabilitas, confidence, identitas model, token, latensi, dan kegagalan secara
terpisah. Hasil ini adalah agreement antar-model, belum akurasi terhadap manusia
atau bukti bahwa salah satu verifier lebih unggul.

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
