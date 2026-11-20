# Evidence-Based Research Assistant

Asisten riset literatur ilmiah yang dirancang untuk menjawab pertanyaan dengan bukti yang bisa ditelusuri sampai ke paper, halaman, dan kutipan aslinya.

Proyek ini memakai Retrieval-Augmented Generation (RAG): sistem mengambil potongan teks (chunk) dari korpus, lalu menyusun jawaban berdasarkan bukti tersebut. Setiap klaim wajib memiliki sitasi chunk yang valid atau diberi label "tidak ada bukti". Ketepatan sitasinya diukur melalui evaluasi.

## Ruang lingkup

Arah pengembangan aktif memakai **referensi skripsi pengguna dari Mendeley**.
Impor BibTeX sudah tersedia; pengumpulan PDF dan korpus pilot dilacak di
[TASKS-SKRIPSI.md](TASKS-SKRIPSI.md). Hanya dokumen open access berlisensi jelas
yang boleh menjadi bukti. Sistem membantu menelusuri fakta, membandingkan
temuan, dan menyintesis bukti lintas paper.

Benchmark MVP **RAG evaluation** dari arXiv tetap menjadi hasil historis yang
terpisah. Target awal 100–500 paper belum tercapai dan tidak menjadi syarat
jumlah referensi untuk korpus skripsi.

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

**Korpus skripsi S0–S4 pilot:** scope ditetapkan dan impor offline membaca 83 entri
menjadi 82 referensi berdasarkan DOI/metadata. Lima PDF pilot berlisensi sudah
tersedia lokal (66 halaman), dengan 26/30 request jaringan dan replay tanpa
request baru. Parsing/indexing lima PDF selesai: 310 chunk, 310 vektor, dan
310 FTS; replay offline identik. Pencarian Indonesia/Inggris baru diuji dengan
12 query draf AI, belum benchmark berlabel manusia. Tabel/section parser masih
memiliki batas. UI skripsi tersedia dengan jumlah referensi/dokumen terindeks
terpisah dan citation key asal pada sitasi. Retrieval/reranking CPU dan alur
jawaban mock sudah direplay. S5 menambahkan RAGAS terpisah dan 20 pertanyaan
draf AI; pilot nyata empat pertanyaan memakai 4 request DeepSeek dan 11 judge
GPT-4o-mini, dengan replay identik tanpa request baru. Skor ini belum menjadi
akurasi manusia. Audit kecil selesai: 9 acuan awal dan 1 revisi diterima;
keputusan verifier masih terbuka.
Evaluasi penuh S5, cakupan full text Indonesia, dan
sisa koleksi masih terbuka; detail di [TASKS-SKRIPSI.md](TASKS-SKRIPSI.md).
Panduan perintah impor ada di [USAGE.md](USAGE.md#impor-referensi-skripsi-s1).
Perintah membuka korpus skripsi ada di
[USAGE.md bagian S4](USAGE.md#tanya-korpus-skripsi-di-streamlit-s4).
Panduan evaluasi otomatis ada di [USAGE.md bagian S5](USAGE.md#evaluasi-skripsi-dengan-ragas-s5).

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
Mode **Tanya korpus** menjalankan retrieval/verifikasi lokal. Untuk pertanyaan
baru, centang **Izinkan API berbayar saat cache kosong**, lalu klik **Cari bukti**.
Generator memakai model dari config dan tetap hanya menjawab dari chunk lokal.
Tanpa centang, UI hanya membaca cache LLM. Maksimum dua percobaan API per submit
(atau batas config yang lebih kecil), termasuk satu koreksi format. Respons
disimpan ke cache; percobaan API dan pemakaian token ditampilkan di UI.
Cache miss tanpa izin ditampilkan sebagai kegagalan, bukan jawaban tanpa bukti.
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
| [TASKS-SKRIPSI.md](TASKS-SKRIPSI.md) | Scope dan tahapan korpus referensi skripsi |
| [DESIGN.md](DESIGN.md) | Sistem desain visual UI |
| [AGENTS.md](AGENTS.md) | Aturan kerja untuk AI coding agent |
