# Evidence-Based Research Assistant

Asisten riset literatur untuk menjawab pertanyaan dari referensi skripsi pengguna,
dengan bukti yang dapat ditelusuri ke paper, halaman PDF, dan kutipan asli.

## Tujuan dan cakupan

Sistem RAG mengambil chunk lokal lalu menyusun jawaban bersitasi per klaim.
Klaim tanpa sitasi valid diberi label "tidak ada bukti". Validitas sitasi dan
dukungan makna dinilai terpisah; skor mesin bukan jaminan kebenaran.

Korpus berasal dari ekspor Mendeley dan file pengguna. Bibliografi sumber memiliki
82 referensi kanonis; salinan turunan KB memiliki 83 setelah penambahan Szeghalmy.
Topiknya mencakup NLP, ABSA, evaluasi model, dan kualitas layanan kesehatan;
judul skripsi tidak disimpulkan dari bibliografi.

Target pertanyaan: lookup faktual, perbandingan, sintesis lintas paper, serta
kontrol di luar korpus. Pertanyaan Indonesia dan Inggris harus diuji. Kesiapan
seluruh tipe pertanyaan dan akurasi manusia belum dibuktikan.

## Produk saat ini

Per 2026-11-21, KB lokal berisi 41 PDF/746 halaman terdaftar, 40 searchable,
dan 2.514 chunk. Parasuraman sudah di-OCR tetapi belum menghasilkan chunk lolos
kualitas; tiga TXT belum berpeta halaman. Sumber/lisensi belum terverifikasi
ditampilkan sebagai label, sesuai izin pemrosesan lokal pengguna.

Alur pengguna: pilih korpus, tanya, baca klaim dan sitasi, lalu buka halaman PDF.
Jawaban tampil lalu RAGAS otomatis menilai Faithfulness dan Response Relevancy
di tiap card. API UI aktif otomatis/cache-first; pemakaian token ditampilkan.
MiniCheck tersedia sebagai diagnostik opsional.

| Bagian | Implementasi |
|---|---|
| Bibliografi/admission | BibTeX Mendeley, manifest dan receipt berhash |
| Parsing KB aktif | Docling, Heron/TableFormer accurate, EasyOCR id/en |
| Parser baseline | PyMuPDF; juga dipakai untuk render dan pembanding native |
| Retrieval | BGE base Inggris, LanceDB, SQLite FTS5, RRF, reranker opsional |
| Generation | DeepSeek Flash non-thinking melalui API, cache-first |
| Evaluasi | RAGAS isolated; MiniCheck lokal; JEV 1.14 masih eksperimen |
| Penyimpanan/UI | SQLite dan Streamlit lokal |

Model/revision/device dan batas runtime mengikuti config. Embedding default CPU;
CUDA tersedia lokal tetapi Torch manual belum selaras dengan lockfile. Docling
dan RAGAS memiliki environment terpisah. Jangan `uv sync`/`uv run` pada `.venv` CUDA.

## Batas hasil dan pekerjaan berikut

- Gate parsing menahan tabel/OCR ambigu; lolos gate belum berarti seluruh isi benar.
- BGE Inggris telah diuji terbatas pada pertanyaan Indonesia/Inggris, belum semua domain.
- RAGAS menilai konteks/relevansi, bukan ketepatan setiap sitasi. Diagnosis MiniCheck
  menemukan kandidat false negative; agreement antar-AI bukan akurasi manusia.
- Pengolahan sumber dan retrieval lokal; generation/evaluasi API dapat mengirim
  pertanyaan, klaim, dan konteks ke provider. Pengguna mengizinkan API UI otomatis
  pada 2026-11-22; batas request tetap berlaku dan CLI default cache-only.
- Clone repo tidak menyertakan PDF, model, database, indeks, atau cache lokal.
- Deployment production, autentikasi multi-user, scraping paywall, sinkronisasi
  Mendeley langsung, evidence map, dan fine-tuning belum menjadi scope aktif.

Agenda berikutnya merapikan UI; sesi peringkasan dokumentasi tidak mengubah UI.
Target awal 100-500 paper, daftar alternatif model, serta estimasi biaya/VRAM awal
bukan persyaratan runtime. Benchmark MVP empat paper tetap terpisah dari KB skripsi.

Panduan operasi: [USAGE.md](USAGE.md). Kontrak teknis: [ARCHITECTURE.md](ARCHITECTURE.md).
Status/bukti korpus: [TASKS-SKRIPSI.md](TASKS-SKRIPSI.md). Riwayat MVP: [TASKS.md](TASKS.md).
