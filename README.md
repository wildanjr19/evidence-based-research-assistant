# Evidence-Based Research Assistant

Asisten riset literatur ilmiah yang dirancang untuk menjawab pertanyaan dengan bukti yang bisa ditelusuri sampai ke paper, halaman, dan kutipan aslinya.

Proyek ini memakai Retrieval-Augmented Generation (RAG): sistem mengambil potongan teks (chunk) dari korpus, lalu menyusun jawaban berdasarkan bukti tersebut. Setiap klaim wajib memiliki sitasi chunk yang valid atau diberi label "tidak ada bukti". Ketepatan sitasinya diukur melalui evaluasi.

## Ruang lingkup

Aplikasi menjawab pertanyaan dari **KB referensi skripsi pengguna**, dengan sitasi
per klaim yang dapat dibuka sampai ke kutipan dan halaman PDF asli. Jawaban hanya
memakai chunk hasil retrieval; klaim tanpa bukti diberi label yang sesuai.

KB aktif berisi **41 PDF terdaftar, 40 searchable, dan 2.514 chunk** dari koleksi
lokal pengguna. Bibliografi turunan memuat 83 referensi; ekspor Mendeley sumber
memuat 82 referensi. Satu PDF scan belum menghasilkan chunk yang lolos kualitas,
dan tiga TXT belum berpeta halaman. Status sumber/lisensi dicatat sebagai label;
koleksi ini tidak diklaim seluruhnya open access.

## Alur aplikasi

1. Pilih korpus dan tulis pertanyaan Indonesia atau Inggris.
2. Retrieval mengambil bukti lokal; generator menyusun jawaban bersitasi.
3. Buka sitasi untuk membaca kutipan, halaman PDF, dan lisensi sumber.
4. Klik **Evaluasi kualitas** bila ingin menghitung Faithfulness dan Response
   Relevancy RAGAS. MiniCheck tersedia sebagai diagnostik opsional.

Jawaban tampil sebelum evaluasi. Skor RAGAS adalah estimasi AI terhadap konteks
atau relevansi, bukan jaminan kebenaran maupun ketepatan setiap sitasi. Context
Recall tersedia pada evaluasi batch yang memiliki jawaban acuan. Evaluasi gagal
atau cache miss ditampilkan sebagai belum tersedia, bukan skor nol.

Parsing dan indeks KB memakai snapshot Docling; retrieval memakai BGE, LanceDB,
dan SQLite FTS5. UI memakai Streamlit, generator aktif DeepSeek Flash. RAGAS
berjalan di environment terpisah, dengan embedding pertanyaan lokal. PDF, teks
korpus, indeks, dan cache berada di `data/` dan tidak di-commit.

## Menjalankan aplikasi lokal

Dari root repo, dengan environment dan data lokal yang sudah disiapkan:

```powershell
.venv/Scripts/python.exe -m streamlit run src/rag/ui/app.py --server.address 127.0.0.1
```

Buka [localhost:8501](http://127.0.0.1:8501). Default memakai KB skripsi penuh
melalui `configs/skripsi-local.yaml`. Mode **Demo tersimpan** menyediakan delapan
jawaban pilot tanpa panggilan generator baru. Pilihan korpus juga menyediakan
pilot lima PDF dan benchmark historis dengan config masing-masing.

Untuk membuat jawaban baru, centang izin API generator sebelum **Cari bukti**:
maksimal dua request per submit, termasuk koreksi format. Izin API evaluasi
terpisah dan default mati: maksimal lima request dengan 1.024 token output per
request. Cache selalu diperiksa lebih dahulu. Pertanyaan, jawaban, atau konteks
terkait dikirim ke provider bila API diizinkan. API key hanya dari environment
atau `.env`; clone repo saja belum menyediakan model, PDF, database, dan cache.

Jawaban baru dan diagnostik menulis salinan database tersendiri. Evaluasi RAGAS
menyimpan artefak baru yang mengikat jawaban, seluruh konteks generation, config,
model, hash, dan usage. Kegagalan evaluasi tidak menghalangi pembacaan jawaban.
Panduan setup, batas biaya, dan troubleshooting ada di [USAGE.md](USAGE.md).
Jangan menjalankan `uv sync` atau `uv run` pada environment CUDA lokal saat ini.

## Status dan batas hasil

Integrasi KB penuh, jawaban bersitasi, PDF sumber, dan evaluasi RAGAS opsional
sudah tersedia. Tes utama dan tes adapter RAGAS memakai provider mock; alur
cache-only, worker terpisah, dan embedding lokal sudah diuji. Fitur evaluasi UI
baru belum diuji dengan request API berbayar nyata. Akurasi manusia dan kualitas
retrieval untuk seluruh jenis pertanyaan belum dibuktikan.

Benchmark MVP empat paper dan hasil eksperimen terdahulu dipertahankan sebagai
riwayat terpisah, termasuk [laporan M6](eval/results/2026-11-19T01-25-11Z_7492c6/m6-summary.md).
Status pekerjaan aktif ada di [TASKS-SKRIPSI.md](TASKS-SKRIPSI.md); riwayat benchmark
ada di [TASKS.md](TASKS.md).

## Mulai dan dokumentasi

Untuk menyiapkan environment dan menjalankan pipeline, ikuti [panduan penggunaan](USAGE.md). Catatan environment CUDA ada di bagian setup panduan tersebut.

| Dokumen | Isi |
|---|---|
| [USAGE.md](USAGE.md) | Setup, perintah pipeline, dan batas penggunaan |
| [OVERVIEW.md](OVERVIEW.md) | Tujuan, ruang lingkup, pilihan stack, dan batasan proyek |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Arsitektur, skema data, format sitasi, dan protokol evaluasi |
| [TASKS.md](TASKS.md) | Ringkasan milestone dan bukti benchmark MVP |
| [TASKS-SKRIPSI.md](TASKS-SKRIPSI.md) | Status aktif, keputusan, hasil dan indeks artefak skripsi |
| [KB-PREPARATION.md](KB-PREPARATION.md) | Alur admission, parsing, gate kualitas dan chunking KB |
| [DESIGN.md](DESIGN.md) | Sistem desain visual UI |
| [AGENTS.md](AGENTS.md) | Aturan kerja untuk AI coding agent |
