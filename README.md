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

Stack utama: Python, PyMuPDF, BGE, LanceDB, SQLite FTS5, dan UI Streamlit. Rincian komponen dan keputusan desain ada di [ARCHITECTURE.md](ARCHITECTURE.md).

## Status

**M0 sampai M7 selesai untuk benchmark awal:** ingestion, parsing, chunking, indexing, retrieval, generation bersitasi, MiniCheck lokal, judge generatif GPT-4o-mini melalui Surplus, dan UI demo Streamlit.

Dataset yang ditinjau pengguna berisi 30 pertanyaan lintas empat paper berlisensi, dengan 236 chunk. [Laporan M6](eval/results/2026-11-19T01-25-11Z_7492c6/m6-summary.md) memuat hasil, biaya estimasi, dan pengulangan dari cache. [Analisis kegagalan](eval/results/2026-11-19T01-25-11Z_7492c6/failure-analysis.md) membahas sitasi yang tidak didukung dan kontrol abstention. Label manusia 52 pasangan dari eksperimen satu paper dilaporkan terpisah; accuracy terhadap manusia pada klaim generation baru belum diukur. Target korpus 100–500 paper dan inference model di GPU masih tertunda. Catatan verifikasi dan handoff ada di [TASKS.md](TASKS.md).

## Demo lokal

UI menampilkan jawaban per klaim. Buka sitasi untuk membaca kutipan asli, ID chunk,
halaman, section, dan lisensi, lalu buka tautan paper untuk memeriksa sumbernya.
Label dukungan otomatis dibedakan dari klaim tanpa bukti dan klaim yang belum
diverifikasi. Label tersebut bukan penilaian manusia.

Dengan korpus dan config M6 lokal yang sesuai:

```powershell
.venv/Scripts/python.exe -m streamlit run src/rag/ui/app.py --server.address 127.0.0.1 -- --config data/m6-multipaper/20261119T004114Z/config-citations-surplus-gpt-authorized-v1.yaml
```

Mode **Demo tersimpan** membaca 30 jawaban M6 tanpa inference atau API baru.
Mode **Tanya korpus** menjalankan retrieval/verifikasi lokal dan hanya membaca
cache LLM. Cache miss ditampilkan sebagai kegagalan, bukan jawaban tanpa bukti.
Database query dibuat sebagai salinan baru agar database benchmark tetap utuh.
Petunjuk untuk korpus lain dan urutan demo ada di [USAGE.md](USAGE.md#ui-streamlit-dan-demo-lokal).
PDF, database, dan cache perlu disiapkan lokal; clone repo saja belum cukup.

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
