# Evidence-Based Research Assistant

> Asisten riset literatur yang menjawab pertanyaan ilmiah dengan sitasi yang dapat ditelusuri sampai ke paper, halaman, dan kutipan aslinya.

---

## 1. Overview

Peneliti sering kesulitan membaca, membandingkan, dan menyintesis banyak paper sekaligus. Alat ringkasan berbasis AI memang membantu, tetapi jawabannya sering tidak disertai bukti yang bisa diperiksa, bahkan kadang mengarang sitasi.

Proyek ini adalah sistem **Retrieval-Augmented Generation (RAG)** yang berjalan lokal, dengan fokus pada **verifiability**: setiap klaim dalam jawaban harus menunjuk ke potongan teks (chunk) spesifik dari paper sumber, dan ketepatan sitasi tersebut **diukur secara kuantitatif**.

**Ruang lingkup (v1):**

- Korpus referensi skripsi pengguna dari ekspor BibTeX Mendeley; mulai dengan 5–10 dokumen open access berlisensi jelas.
- Ingestion paper berizin (metadata dan full text), indexing, dan hybrid retrieval.
- Tanya-jawab dengan sitasi per klaim.
- Evaluasi ketepatan sitasi.
- Opsional (v2): tabel perbandingan metode dan evidence map.

**Di luar scope:** deployment production, autentikasi multi-user, paper berbayar/paywalled, dan scraping tanpa izin.

**Pengguna utama (v1):** peneliti akademik yang perlu memetakan literatur dan menelusuri bukti dengan cepat.

**Arah pengembangan aktif (2026-11-19):** evidence-based assistant untuk referensi
skripsi pengguna. Seluruh 83 entri dalam `reference-skripsi.bib` masuk audit;
hasil impor awal memetakan 82 referensi berdasarkan DOI atau metadata identik.
Referensi mencakup NLP, aspect-based sentiment analysis, evaluasi model, dan
kualitas layanan kesehatan; ini deskripsi bibliografi, bukan penetapan judul skripsi.
Pertanyaan Indonesia dan Inggris menjadi target pengujian. Jumlah referensi
tidak menjamin jumlah PDF berlisensi yang tersedia atau berhasil diindeks.

Benchmark MVP *RAG evaluation* empat paper tetap dipertahankan terpisah sebagai
hasil historis; target awal 100–500 paper tidak menjadi syarat korpus skripsi.
Impor/audit BibTeX sudah tersedia, sedangkan pengunduhan sumber tambahan dan
pipeline skripsi berikutnya dilacak di [TASKS-SKRIPSI.md](TASKS-SKRIPSI.md).

**Tipe pertanyaan yang wajib didukung:**

| Tipe | Contoh | Ekspektasi jawaban |
|---|---|---|
| Lookup faktual | "What metric does paper X use for citation recall?" | 1–2 klaim dengan sitasi chunk spesifik |
| Comparison | "How does RRF compare to learned fusion?" | Klaim per sisi perbandingan, masing-masing bersitasi |
| Synthesis | "What are common failure modes reported for RAG evaluation?" | Beberapa klaim dari paper berbeda |
| Unanswerable (kontrol) | Pertanyaan di luar korpus | Menolak menjawab dan menyatakan tidak ada bukti |

---

## 2. Goals

| # | Goal | Indikator keberhasilan |
|---|------|------------------------|
| 1 | Membangun korpus dari referensi skripsi dengan metadata lisensi | Setiap referensi memiliki status; dokumen yang memenuhi syarat terindeks dengan sumber dan lisensi jelas |
| 2 | Retrieval yang akurat lewat pendekatan hybrid | Hybrid (+rerank) mengungguli BM25 dan dense saja pada metrik retrieval |
| 3 | Jawaban dengan sitasi per klaim yang dapat ditelusuri | Setiap klaim memiliki ID chunk, paper, dan halaman |
| 4 | Evaluasi sitasi yang terukur | Laporan citation precision, citation recall, dan faithfulness pada 30-50 pertanyaan uji |
| 5 | Dapat dijalankan penuh di lokal dengan biaya rendah | Satu PC, tanpa server cloud, biaya API hanya beberapa dolar |
| 6 | Dokumentasi layak portofolio | README memperkenalkan proyek dan menautkan panduan penggunaan, arsitektur, keputusan desain, hasil evaluasi, dan analisis kegagalan |

**Prioritas pengerjaan:** Goal 1-4 adalah inti. Goal 5-6 dikerjakan paralel. Tabel perbandingan metode dan evidence map hanya dikerjakan bila waktu tersisa.

---

## 3. Stack

### Lingkungan kerja
PC lab: Intel i9 HX, RAM 64 GB, VRAM 8 GB. Cukup untuk menjalankan embedding, reranker, dan model NLI di GPU secara lokal. LLM utama memakai API.

### Komponen

| Lapisan | Pilihan | Catatan |
|---|---|---|
| Sumber data | arXiv API, OpenAlex, Semantic Scholar API, PMC Open Access, Unpaywall | Hanya sumber berizin; simpan lisensi di metadata |
| Parsing PDF | **PyMuPDF (default)**; alternatif: GROBID (Docker) | PyMuPDF dipakai lebih dulu karena tanpa Docker; GROBID untuk struktur section/referensi ditunda ke v2 |
| Chunking | Section-aware chunking | Simpan nomor halaman dan nama section per chunk |
| Embedding | **`bge-base-en-v1.5` (default)**; alternatif: `bge-small`, `e5`, `all-MiniLM-L6-v2`, `bge-large`, `bge-m3` | Via sentence-transformers; jalan di GPU 8 GB tanpa masalah. Detail di bagian 3.1 |
| Vector store | **LanceDB (default)**; alternatif: Chroma | Lokal, tanpa server |
| Keyword search | **SQLite FTS5 (default)**; alternatif: `rank_bm25` | Pasangan untuk dense retrieval |
| Fusion | Reciprocal Rank Fusion (RRF) | Menggabungkan hasil BM25 dan dense |
| Reranker | **`bge-reranker-base` (default)**; alternatif: `ms-marco-MiniLM-L-6-v2`, `bge-reranker-large`, `bge-reranker-v2-m3` | Dibandingkan dengan dan tanpa reranker. Detail di bagian 3.1 |
| LLM (generasi) | API: Gemini Flash, DeepSeek, atau GPT-4o-mini | Dipilih murah; dibuat modular agar mudah ganti |
| Verifikasi klaim | **MiniCheck (lokal) + LLM-as-judge pada sampel (default)**; alternatif: NLI cross-encoder (DeBERTa-v3), AlignScore, LLM-as-judge penuh | Mengecek apakah chunk yang dikutip benar-benar mendukung klaim. Detail di bagian 3.1 |
| Metadata store | SQLite | Paper, chunk, lisensi, hasil evaluasi |
| UI | **Streamlit (default)**; alternatif: Gradio | Cukup untuk demo |
| Evaluasi | Skrip Python + dataset uji buatan sendiri | Opsional: RAGAS sebagai pembanding |
| Lainnya | Python 3.11+, `uv`/`venv`, Git; Docker hanya bila GROBID (v2) dipakai | |

### 3.1 Model ML: default dan alternatif

> Semua angka adalah **perkiraan kasar** (asumsi: korpus ~500 paper, ~20-30 ribu chunk @ ~400 token, GPU 8 GB VRAM). Akan diverifikasi lewat benchmark di PC lab; hasil verifikasi awal dicatat di TASKS.md dan laporan evaluasi di `eval/results/<run_id>/`.

#### a. Embedding

| Model | Parameter | Dimensi | Ukuran (fp16) | Status | Catatan |
|---|---|---|---|---|---|
| `bge-base-en-v1.5` | 109M | 768 | ~220 MB | **Default** | Keseimbangan kualitas dan biaya terbaik. |
| `bge-small-en-v1.5` | 33M | 384 | ~65 MB | Alternatif | Cepat; titik awal yang baik untuk prototyping. |
| `all-MiniLM-L6-v2` | 22M | 384 | ~45 MB | Alternatif | Paling ringan, kualitas retrieval paling rendah. Konteks pendek (256 token). |
| `bge-large-en-v1.5` | 335M | 1024 | ~670 MB | Alternatif | Kualitas sedikit lebih tinggi, ~3x lebih lambat. |
| `bge-m3` | 568M | 1024 | ~1.1 GB | Alternatif | Untuk multibahasa (misal paper campur Indonesia/Inggris) atau konteks panjang. |

- **VRAM:** `bge-base` batch 32-64 sekitar 1-2 GB.
- **Waktu indexing:** GPU beberapa menit; CPU sekitar 10-30 menit (`bge-small`), 2-3x lebih lama untuk `bge-base`. Dijalankan sekali.
- **Penyimpanan vektor:** 30 ribu chunk × 768 dim × 4 byte ≈ 90 MB.
- **Eksperimen:** bandingkan 2-3 model embedding (small vs base vs m3) sebagai bagian dari evaluasi.

#### b. Reranker

Cross-encoder: setiap pasangan (query, chunk) diproses bersama, sehingga biaya naik linear terhadap jumlah kandidat.

| Model | Parameter | Ukuran (fp16) | Status | Catatan |
|---|---|---|---|---|
| `bge-reranker-base` | 278M | ~560 MB | **Default** | Pas untuk skala proyek ini. |
| `ms-marco-MiniLM-L-6-v2` | 22M | ~45 MB | Alternatif | Sangat cepat; baseline murah. |
| `bge-reranker-large` | 560M | ~1.1 GB | Alternatif | Lebih akurat, lebih lambat. |
| `bge-reranker-v2-m3` | 568M | ~1.1 GB | Alternatif | Multibahasa; umumnya lebih baik dari generasi sebelumnya. |

- **VRAM:** sekitar 1-2 GB saat inferensi.
- **Latensi (rerank top-50):** GPU ~0.1-0.5 detik, CPU ~2-6 detik per query. Rerank top-20 memangkas biaya lebih dari setengah.
- **Pola default:** hybrid retrieval ambil top-50, rerank, kirim top-5 sampai top-8 ke LLM. Ini juga menekan token API.

#### c. Verifikasi klaim

Tugas: diberi satu klaim dan chunk yang dikutip, apakah chunk tersebut benar-benar **mendukung** klaim?

| Opsi | Contoh | VRAM | Kecepatan | Biaya | Status | Catatan |
|---|---|---|---|---|---|---|
| Model khusus fact-checking | **MiniCheck** (~0.4-0.8B), AlignScore | 1-2 GB | Cepat | Gratis (lokal) | **Default (lapis 1)** | Dirancang untuk mengecek klaim terhadap dokumen grounding; performa mendekati LLM besar. |
| LLM-as-judge via API | GPT-4o-mini, Gemini Flash, dsb. | 0 | Sedang | Murah, berbayar | **Default (lapis 2, sampel)** | Fleksibel dan dapat memberi alasan; rawan bias dan inkonsistensi. |
| NLI cross-encoder | DeBERTa-v3-base/large fine-tuned NLI | 0.5-1 GB | Sangat cepat | Gratis (lokal) | Alternatif | Sederhana; terbatas ~512 token dan lemah untuk bukti yang tersebar. |
| LLM-as-judge penuh | Sama seperti di atas, untuk semua klaim | 0 | Sedang | Lebih mahal | Alternatif | Dipakai bila ingin membandingkan dengan pendekatan dua lapis. |

**Pendekatan default (tiga langkah):**

1. **Verifier lokal (MiniCheck)** untuk semua klaim: cepat, gratis, dan bisa menandai klaim berbukti lemah di UI.
2. **LLM-judge dari keluarga model berbeda dari generator** untuk sampel (~20-30% klaim), menghindari bias model menilai jawabannya sendiri.
3. **Label manual 50-100 klaim** sebagai gold standard, lalu hitung kesesuaian verifier dengan manusia (misal Cohen's kappa).

**Metrik:** mengikuti kerangka ALCE, yaitu **citation precision** (sitasi yang diberikan benar-benar mendukung) dan **citation recall** (klaim yang butuh bukti sudah disitasi).

**Estimasi biaya LLM-judge:** ~250 klaim × ~1.000 token ≈ 250 ribu token per putaran evaluasi, umumnya di bawah 1 dolar pada model murah. Cek harga terbaru di penyedia.

#### d. Anggaran VRAM (konfigurasi default, dimuat bersamaan)

| Komponen | Model | Kisaran VRAM |
|---|---|---|
| Embedding | `bge-base` | ~1 GB |
| Reranker | `bge-reranker-base` | ~1-1.5 GB |
| Verifier | MiniCheck (~0.8B) | ~2 GB |
| **Total** | | **~4-5 GB** |

Masih muat di VRAM 8 GB dengan ruang sisa. LLM generasi memakai API sehingga tidak membebani VRAM.

### Arsitektur ringkas

```
Sumber (arXiv/OpenAlex/PMC)
        |
   Ingestion -> Parsing (PyMuPDF) -> Chunking
        |                              |
   SQLite (metadata)        Embedding + BM25 index
                                       |
Pertanyaan -> Hybrid retrieval (+ rerank) -> LLM (API)
                                       |
              Jawaban + sitasi per klaim -> Verifikasi klaim
                                       |
                        UI (Streamlit) + Laporan evaluasi
```

---

## 4. Limitations

- **Cakupan korpus terbatas.** Hanya paper open access pada satu domain sempit; sistem tidak mewakili seluruh literatur.
- **Kualitas parsing tidak sempurna.** Tabel, rumus, gambar, dan layout dua kolom dapat menghasilkan teks yang rusak.
- **Bergantung pada API eksternal.** Kualitas dan biaya generasi bergantung pada penyedia LLM, dan membutuhkan koneksi internet.
- **Evaluasi berskala kecil.** Dataset uji 30-50 pertanyaan buatan sendiri cukup untuk menunjukkan metodologi, tetapi belum signifikan secara statistik.
- **Verifikasi sitasi tidak 100% andal.** LLM-as-judge dan NLI sendiri bisa keliru, sehingga hasilnya perlu dipahami sebagai estimasi.
- **Bukan sistem production.** Tidak ada deployment, autentikasi, skalabilitas, atau monitoring.
- **Bukan pengganti pembacaan paper.** Sistem membantu eksplorasi dan sintesis, bukan menggantikan penilaian peneliti.
- **VRAM 8 GB** membatasi ukuran model lokal. Konfigurasi default (embedding + reranker + verifier) memakai sekitar 4-5 GB, tetapi LLM 7B+ tidak dijalankan bersamaan di lokal.
- **Angka biaya dan performa model masih estimasi**, belum diukur di perangkat sebenarnya.

---

## 5. Problems and Solutions

| # | Masalah | Dampak | Solusi |
|---|---------|--------|--------|
| 1 | **Halusinasi dan sitasi palsu**: LLM mengutip paper atau klaim yang tidak ada | Hilangnya kepercayaan terhadap jawaban | LLM hanya boleh menjawab dari chunk yang diambil; setiap klaim wajib memakai ID chunk; klaim tanpa dukungan ditolak atau diberi label "tidak ada bukti" |
| 2 | **Sitasi ada tetapi tidak mendukung klaim** (citation looks right, but is wrong) | Sitasi menyesatkan | Verifikasi per klaim: MiniCheck lokal (default) + LLM-judge pada sampel, divalidasi dengan label manual (lihat 3.1c); hitung citation precision dan recall. Alternatif: NLI DeBERTa, AlignScore, LLM-judge penuh |
| 3 | **Parsing PDF berantakan** | Chunk berisi teks rusak, retrieval buruk | Mulai dari arXiv (format lebih bersih), parsing PyMuPDF + filter chunk berkualitas rendah, catat kasus gagal; GROBID sebagai opsi v2 |
| 4 | **Retrieval melewatkan bukti penting** | Jawaban tidak lengkap | Hybrid retrieval (BM25 + dense + RRF), reranking, dan perbandingan metrik antar konfigurasi |
| 5 | **Chunk kehilangan konteks** | Kutipan ambigu atau salah tafsir | Section-aware chunking, overlap, dan penyimpanan section serta halaman sebagai metadata |
| 6 | **Tidak ada ground truth untuk evaluasi** | Klaim kualitas tidak bisa dibuktikan | Buat 30-50 pertanyaan dengan jawaban dan paper rujukan secara manual; laporkan metrik jelas |
| 7 | **Isu lisensi dan hak cipta** | Risiko legal, terutama bila repo dipublikasikan | Hanya paper open access; simpan lisensi di metadata; jangan commit PDF ke repo publik, cukup simpan ID/URL dan skrip unduh |
| 8 | **Biaya API membengkak** | Anggaran proyek terlampaui | Pilih model murah, cache hasil embedding dan respons, batasi konteks, tetapkan batas anggaran dan logging token |
| 9 | **Scope creep** | Proyek tidak selesai | Kunci v1 pada ingestion, retrieval, QA bersitasi, dan evaluasi; fitur lain masuk v2 |
| 10 | **Hasil sulit direproduksi** | Portofolio kurang kredibel | Kunci versi dependensi, simpan konfigurasi eksperimen, pisahkan data mentah dan hasil, sediakan skrip satu perintah |

---

## 6. Deliverables

- Kode sumber dengan struktur modular (ingestion, indexing, retrieval, generation, evaluation, UI).
- Dataset uji (pertanyaan, jawaban rujukan, paper rujukan) dengan campuran lookup, comparison, synthesis, dan unanswerable.
- UI demo Streamlit dengan lingkup v1: input pertanyaan dan contoh pertanyaan; klaim beserta sitasi yang bisa dibuka (paper, halaman, section, kutipan asli); penanda untuk klaim tanpa bukti.
- Laporan evaluasi: BM25 vs dense vs hybrid vs hybrid+rerank, serta metrik ketepatan sitasi.
- README sebagai pengantar proyek, USAGE.md untuk panduan penggunaan, serta tautan ke arsitektur, keputusan desain, dan laporan evaluasi/analisis kegagalan.
- Demo singkat (GIF atau video).
