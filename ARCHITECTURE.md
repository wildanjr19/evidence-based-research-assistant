# ARCHITECTURE.md

Spesifikasi teknis Evidence-Based Research Assistant. Dokumen ini adalah sumber kebenaran untuk arsitektur, skema data, format ID/sitasi, dan protokol evaluasi.

- Tujuan produk dan batasan: `OVERVIEW.md`
- Sistem desain UI: `DESIGN.md`
- Aturan kerja agent dan invarian proyek: `AGENTS.md`

**Status:** draft v0.1. Skema data (§4), format ID chunk (§5), dan format sitasi (§6) adalah kontrak tetap: mengubahnya berarti semua indeks dan hasil evaluasi harus dibangun ulang, jadi butuh persetujuan eksplisit (AGENTS.md §4.3, §10).

---

## 1. Prinsip

1. **Satu arah data.** Ingestion hanya menulis ke SQLite + indeks. Retrieval hanya membaca. Generation tidak pernah menyentuh disk korpus langsung.
2. **Logika terpisah dari I/O.** Fungsi inti (chunking, fusion RRF, parsing sitasi, validasi ID) murni dan bisa diuji tanpa jaringan/GPU/disk.
3. **Semua yang bisa dieksperimenkan masuk config.** Ukuran chunk, bobot RRF, top-k, nama model, seed — tidak ada yang hardcoded di fungsi.
4. **Jawaban adalah data terstruktur dulu, teks belakangan.** LLM menghasilkan klaim + ID chunk dalam bentuk JSON yang divalidasi, baru dirender ke Markdown. Ini yang membuat citation precision/recall bisa dihitung mesin.
5. **Reproduksibel.** Setiap eksekusi evaluasi menghasilkan `run_id` baru dengan manifest config + versi model + seed. Tidak ada penimpaan hasil.

---

## 2. Peta modul

```
src/rag/
  config.py        loader + validasi config YAML -> objek bertipe
  ids.py           pembuatan & validasi ID chunk, paper, run
  ingestion/       klien arXiv/OpenAlex/PMC, unduh PDF, metadata + lisensi
  parsing/         parser PyMuPDF, normalisasi teks, deteksi section (GROBID: v2)
  chunking/        section-aware chunking, penetapan halaman
  indexing/        embedding, vector store, BM25/FTS5, penulisan SQLite
  retrieval/       dense, BM25, RRF, reranker, orkestrasi
  generation/      prompt, klien LLM, skema output klaim, render sitasi
  verification/    MiniCheck, LLM-judge, agregasi label
  evaluation/      metrik retrieval, metrik sitasi, penulisan laporan run
  ui/              Streamlit app
eval/              dataset uji (pertanyaan, gold paper/chunk, label manual)
configs/           config.yaml + variasi eksperimen
tests/             unit test; marker `gpu` untuk test yang butuh GPU
data/              korpus + indeks (tidak di-commit)
```

Aturan dependensi antar modul: `ingestion → parsing → chunking → indexing`, lalu `retrieval → generation → verification`, dan `evaluation` boleh mengimpor semua modul lainnya. Tidak ada impor balik ke arah hulu.

---

## 3. Data flow

Setiap tahap adalah perintah terpisah yang idempoten dan bisa dijalankan ulang per-paper.

| # | Tahap | Input | Output | Artefak |
|---|---|---|---|---|
| 1 | Discover | query/kategori domain, batas jumlah | metadata kandidat + status open access + lisensi | `data/raw/candidates.jsonl` |
| 2 | Fetch | ID kandidat | PDF + `sha256` + metadata SQLite | `data/raw/pdf/<safe_paper_id>.pdf` |
| 3 | Parse | PDF | teks per halaman, section, referensi | `data/parsed/<paper_id>.json` |
| 4 | Chunk | teks terparse | chunk + halaman + section | tabel `chunk` |
| 5 | Index | chunk | vektor + indeks BM25 | `data/index/vectors.lance`, tabel FTS5 |
| 6 | Retrieve | pertanyaan | kandidat berperingkat | (in-memory) |
| 7 | Generate | top-k chunk | klaim + sitasi tervalidasi | tabel `answer`, `claim` |
| 8 | Verify | klaim + chunk tersitasi | label dukungan + skor | tabel `verification` |
| 9 | Evaluate | gold set + output | metrik per run | `eval/results/<run_id>/` |

Tahap 2–5 bersifat *build once*: dijalankan untuk seluruh korpus, lalu diulang hanya untuk paper baru. Tahap 6–8 per pertanyaan. Tahap 9 memerlukan tahap 6–8 untuk seluruh pertanyaan uji.

Implementasi M1 mempertahankan `paper.pdf_sha256 NOT NULL`: Discover menyimpan kandidat berlisensi ke JSONL; Fetch memasukkan metadata ke tabel `paper` hanya setelah PDF tersedia dan hash nyata dihitung. `safe_paper_id` adalah nama file, bukan ID baru: `arxiv:2401.12345v1` menjadi `arxiv_2401.12345v1`, dan `/` pada source ID lama diganti `_` karena batas nama file Windows. Format ID/sitasi dan skema SQLite tidak berubah.

Pencarian memakai Atom API arXiv; lisensi diperiksa melalui OAI-PMH `arXivRaw` dari sumber arXiv yang sama. Karena OAI mengekspos metadata versi terbaru, nomor versi kandidat wajib cocok dengan versi terbaru dalam riwayat OAI sebelum lisensinya dipakai. Kandidat tanpa lisensi yang dikenali dan diizinkan config ditolak dengan log alasan. Metadata di-cache per hari UTC, request serial dengan jeda minimal 3 detik. Batas `ingestion.max_papers` menghitung hasil pencarian yang diperiksa, bukan hanya paper yang lolos. Referensi protokol: [OAI-PMH](https://info.arxiv.org/help/oa/index.html), [lisensi](https://info.arxiv.org/help/license/index.html), [ketentuan API](https://info.arxiv.org/help/api/tou.html).

Pemisahan penting: **parsing dan chunking tidak boleh dipanggil saat query time.** Kalau terjadi, latensi dan biaya tidak terkontrol.

### 3.1 Alur runtime (query time)

Tahap 6–8 dari tabel di atas, dirinci beserta cabang kegagalannya. Tidak ada langkah yang mem-parse PDF atau mengubah indeks.

```mermaid
sequenceDiagram
    autonumber
    actor U as Pengguna
    participant UI as ui (Streamlit)
    participant R as retrieval
    participant G as generation
    participant V as verification
    participant DB as SQLite + vector store

    U->>UI: pertanyaan
    UI->>DB: INSERT run (kind=query) -> run_id
    UI->>R: retrieve(question, config)
    R->>DB: dense top-k + BM25 top-k (buang quality_flag=low_quality)
    R->>R: RRF -> rerank -> final_top_k
    R-->>UI: chunks[]
    alt chunks kosong
        UI-->>U: "tidak ada bukti pada korpus" (LLM tidak dipanggil)
    else chunks tersedia
        UI->>G: generate(question, chunks)
        G->>G: klien LLM -> JSON klaim
        G->>DB: validasi tiap chunk_id terhadap tabel chunk
        G->>DB: INSERT answer, claim
        G-->>UI: claims[] (valid + unsupported)
        UI->>V: verify(claims)
        V->>DB: INSERT verification (MiniCheck; LLM-judge pada sampel)
        V-->>UI: label dukungan
        UI-->>U: klaim + kutipan + penanda bukti
    end
```

| Kondisi gagal | Perilaku | Yang dicatat |
|---|---|---|
| Retrieval kosong atau semua chunk `low_quality` | Tidak memanggil LLM; UI menampilkan "tidak ada bukti" | `run` selesai dengan 0 klaim |
| Respons LLM bukan JSON valid | Satu kali retry dengan instruksi format, lalu berhenti | `raw_response` + kegagalan format |
| ID chunk tidak valid atau tidak ada di DB | ID dibuang, klaim dipertahankan | `hallucinated_citation` |
| Klaim tanpa sitasi valid | Dirender sebagai "tidak ada bukti" | `claim.unsupported = 1` |
| Verifier error / model tidak tersedia | Jawaban tetap ditampilkan dengan label "belum diverifikasi" | Status verifikasi di `verification` |
| Melebihi `generation.max_calls_per_run` | Run dihentikan, bukan dilanjutkan diam-diam | Alasan di `run.notes` |

Aturan: kegagalan dicatat sebagai data, tidak pernah ditelan oleh `except: pass`. Angka pada laporan evaluasi harus bisa ditelusuri ke baris di tabel ini.

---

## 4. Skema data (SQLite)

Satu database: `data/index/corpus.db`. Vektor disimpan terpisah di vector store, dirujuk lewat `chunk_id`.

```sql
-- Metadata paper. Satu baris per versi paper yang diindeks.
CREATE TABLE paper (
    paper_id      TEXT PRIMARY KEY,      -- "arxiv:2401.12345v1"
    source        TEXT NOT NULL,         -- arxiv | openalex | pmc
    source_id     TEXT NOT NULL,         -- ID di sumber asal
    title         TEXT NOT NULL,
    authors       TEXT,                  -- JSON array
    year          INTEGER,
    venue         TEXT,
    doi           TEXT,
    license       TEXT NOT NULL,         -- wajib, mis. "CC-BY-4.0"
    license_url   TEXT,
    landing_url   TEXT NOT NULL,
    pdf_sha256    TEXT NOT NULL,
    fetched_at    TEXT NOT NULL,         -- ISO-8601 UTC
    parse_status  TEXT NOT NULL DEFAULT 'pending'  -- pending|ok|failed
);

-- Satu baris per chunk. Unit sitasi terkecil.
CREATE TABLE chunk (
    chunk_id      TEXT PRIMARY KEY,      -- lihat §5
    paper_id      TEXT NOT NULL REFERENCES paper(paper_id),
    page_start    INTEGER NOT NULL,
    page_end      INTEGER NOT NULL,
    section       TEXT,                  -- nama section hasil parsing, boleh NULL
    section_order INTEGER,
    chunk_order   INTEGER NOT NULL,      -- urutan dalam paper
    text          TEXT NOT NULL,
    n_tokens      INTEGER NOT NULL,
    quality_flag  TEXT                   -- ok | low_quality (mis. teks rusak)
);

-- Satu baris per eksekusi pipeline (retrieval+generation+verify) atau per evaluasi.
CREATE TABLE run (
    run_id        TEXT PRIMARY KEY,      -- "2026-11-18T02:10:00Z_ab12cd"
    kind          TEXT NOT NULL,         -- query | eval
    config_hash   TEXT NOT NULL,         -- sha256 config efektif
    config_json   TEXT NOT NULL,         -- config efektif lengkap
    code_version  TEXT,                  -- git commit atau "dirty"
    seed          INTEGER NOT NULL,
    model_gen     TEXT,
    model_embed   TEXT,
    model_rerank  TEXT,
    model_verify  TEXT,
    started_at    TEXT NOT NULL,
    finished_at   TEXT,
    notes         TEXT
);

-- Satu baris per pertanyaan yang dijawab.
CREATE TABLE answer (
    answer_id     TEXT PRIMARY KEY,
    run_id        TEXT NOT NULL REFERENCES run(run_id),
    question      TEXT NOT NULL,
    raw_response  TEXT,                  -- respons mentah LLM, untuk audit
    created_at    TEXT NOT NULL
);

-- Satu baris per klaim. Klaim tanpa sitasi valid tetap disimpan agar bisa dihitung.
CREATE TABLE claim (
    claim_id      TEXT PRIMARY KEY,
    answer_id     TEXT NOT NULL REFERENCES answer(answer_id),
    claim_order   INTEGER NOT NULL,
    text          TEXT NOT NULL,
    citations     TEXT NOT NULL,         -- JSON array chunk_id (boleh kosong)
    unsupported   INTEGER NOT NULL DEFAULT 0  -- 1 = dilabeli "tidak ada bukti"
);

-- Satu baris per pasangan (klaim, chunk tersitasi) beserta hasil verifikasi.
CREATE TABLE verification (
    claim_id      TEXT NOT NULL REFERENCES claim(claim_id),
    chunk_id      TEXT NOT NULL REFERENCES chunk(chunk_id),
    verifier      TEXT NOT NULL,         -- minicheck | llm_judge | manual
    model         TEXT,
    label         TEXT NOT NULL,         -- supported | partially_supported | not_supported
    score         REAL,                  -- probabilitas/likuiditas model, boleh NULL
    rationale     TEXT,
    created_at    TEXT NOT NULL,
    PRIMARY KEY (claim_id, chunk_id, verifier)
);
```

Catatan desain:

- `verification` memakai primary key gabungan supaya beberapa verifier bisa menilai pasangan yang sama dan hasilnya bisa dibandingkan (MiniCheck vs LLM-judge vs label manusia).
- `claim.citations` menyimpan JSON array, bukan tabel relasi, karena urutan sitasi per klaim bermakna untuk evaluasi. Validitas tetap dicek terhadap `chunk.chunk_id`.
- `paper.license` NOT NULL: paper tanpa lisensi jelas tidak boleh masuk indeks (AGENTS.md §5).

Dataset uji disimpan sebagai file di `eval/`, bukan di SQLite, agar mudah di-diff dan di-review:

```
eval/
  questions.jsonl        # satu pertanyaan per baris
  gold_labels.jsonl      # label manual untuk sampel klaim (Cohen's kappa)
  results/<run_id>/      # metrics.json, per_question.jsonl, report.md
```

```jsonc
// eval/questions.jsonl
{
  "qid": "q001",
  "question": "How does RRF compare to learned fusion for hybrid retrieval?",
  "qtype": "comparison",              // lookup | comparison | synthesis
  "gold_paper_ids": ["arxiv:2401.12345v1"],
  "gold_chunk_ids": ["arxiv:2401.12345v1:p5:c02"],
  "reference_answer": "..."           // opsional, untuk audit kualitas dataset
}
```

---

## 5. Format ID

**Paper ID:** `<source>:<source_id>` — contoh `arxiv:2401.12345v1`, `pmc:PMC10234567`. Versi arXiv wajib disertakan supaya ID stabil.

**Chunk ID:** `<paper_id>:p<page>:c<ordinal>`

- `page` = halaman PDF 1-indexed tempat chunk **dimulai**.
- `ordinal` = urutan chunk di seluruh paper, 2 digit minimum (chunk ke-3 → `c03`).
- Contoh: `arxiv:2401.12345v1:p7:c03`

Regex validasi tunggal (dipakai di `src/rag/ids.py` dan saat memvalidasi output LLM):

```
^[a-z]+:[A-Za-z0-9._\-/]+:p[0-9]{1,4}:c[0-9]{2,4}$
```

Alasan bentuk ini:

- **Tanpa nama section di ID.** Judul section mengandung spasi, karakter unicode, dan bisa berubah bila PDF di-parse ulang. Section tetap tersimpan di kolom `chunk.section` untuk ditampilkan, tetapi bukan bagian dari identitas.
- **Page di ID.** Halaman adalah tingkat bukti yang diminta OVERVIEW ("paper, halaman, kutipan") dan muncul di UI.
- **Ordinal, bukan hash.** Lebih mudah dibaca manusia saat menelusuri jawaban; keunikan dijamin oleh pasangan paper+halaman+urutan.
- **Konsekuensi:** chunking harus deterministik. Bila strategi chunking berubah, semua chunk ID berubah → indeks dan gold set harus dibangun ulang. Ini alasan ukuran chunk/overlap dikunci di config dan dicatat di manifest run.

`chunk_id` tidak boleh dikarang. Setiap ID dari LLM harus lolos regex **dan** ada di tabel `chunk`; jika tidak, klaim ditolak (lihat §6).

---

## 6. Format sitasi

LLM tidak menulis Markdown bebas. Ia dipaksa mengembalikan JSON terstruktur:

```json
{
  "claims": [
    {
      "text": "RRF improves recall over single-retriever baselines on heterogeneous corpora.",
      "citations": ["arxiv:2401.12345v1:p5:c02", "arxiv:2310.54321v2:p11:c07"]
    },
    {
      "text": "No retrieved chunk reports latency measurements for the multi-lingual setting.",
      "citations": [],
      "unsupported": true
    }
  ]
}
```

Pipeline validasi (semua di `src/rag/generation/citations.py`, murni dan teruji):

1. Parse JSON. Gagal → jawaban ditolak, dicatat sebagai kegagalan format.
2. Untuk setiap ID: cek regex, cek keberadaan di tabel `chunk`. ID tidak valid dibuang, dan kejadiannya dicatat sebagai `hallucinated_citation` (metrik tersendiri, karena ini kegagalan yang berbeda dari sitasi salah).
3. Klaim yang sitasinya habis setelah langkah 2 diberi `unsupported = 1` dan dirender sebagai "tidak ada bukti" — tidak dihapus diam-diam, supaya citation recall bisa dihitung.
4. Deduplikasi ID per klaim, jaga urutan kemunculan.

Rendering ke pengguna: nomor referensi `[1]`, `[2]` dengan daftar di bawah jawaban yang memuat `paper title — p.<page>, <section>` dan teks kutipan chunk. Nomor hanya kosmetik; identitas kebenaran tetap `chunk_id`.

Konsekuensi untuk evaluasi: karena setiap klaim dan setiap sitasinya tersimpan terpisah, citation precision dan recall dihitung langsung dari tabel tanpa parsing ulang teks.

---

## 7. Retrieval

Konfigurasi default (semua nilai berasal dari `configs/config.yaml`):

1. Dense: `bge-base-en-v1.5`, ambil top-50.
2. BM25: SQLite FTS5, ambil top-50.
3. Fusion: RRF dengan `k = 60`, ambil top-50 gabungan.
4. Rerank: `bge-reranker-base` atas 50 kandidat, ambil top-8 untuk prompt.
5. Filter: buang chunk `quality_flag = 'low_quality'` sebelum fusion.

Kondisi eksperimen yang wajib dilaporkan (Goal 2): BM25 saja, dense saja, hybrid (RRF), hybrid + rerank. Metrik retrieval: recall@k dan MRR terhadap `gold_chunk_ids`, dengan k = 5, 10, 20.

Reranker bersifat opsional saat runtime (flag config) supaya ablasi bisa dijalankan tanpa mengubah kode.

---

## 8. Generation dan verifikasi

- Prompt hanya berisi chunk hasil retrieval. Tidak ada pengetahuan luar, tidak ada instruksi "gunakan pengetahuanmu" (AGENTS.md §4.1).
- Chunk di prompt diberi label `chunk_id` eksplisit agar model bisa merujuk tanpa mengarang.
- Bila tidak ada chunk yang mendukung sebuah klaim, model diinstruksikan menandainya `unsupported: true` alih-alih mengisi sitasi asal.

Verifikasi dua lapis (default, sesuai OVERVIEW §3.1c):

1. **MiniCheck (lokal)** untuk semua pasangan (klaim, chunk) → label + skor.
2. **LLM-judge dari keluarga model berbeda** untuk sampel ~20–30% klaim → label + alasan.
3. **Label manual** 50–100 pasangan sebagai gold → Cohen's kappa antara verifier dan manusia.

Pemilihan sampel memakai seed dari manifest run agar reproducible.

---

## 9. Protokol evaluasi

Dataset: 30–50 pertanyaan pada satu domain sempit (RAG evaluation), dengan gold paper dan gold chunk yang ditentukan manual. Dataset tidak boleh diubah untuk memperbaiki skor; perubahan dicatat sebagai versi dataset baru (AGENTS.md §4.5).

Komposisi wajib: campuran pertanyaan lookup faktual, comparison, synthesis, dan **unanswerable** (target ~10–15%). Untuk pertanyaan unanswerable, jawaban benar adalah menolak menjawab dengan label "tidak ada bukti"; klaim yang tetap dihasilkan dihitung sebagai kegagalan faithfulness.

Metrik yang dilaporkan per run:

| Metrik | Definisi | Sumber |
|---|---|---|
| Citation precision | pasangan (klaim, chunk) berlabel `supported` ÷ total pasangan tersitasi | `verification` |
| Citation recall | klaim dengan ≥1 sitasi `supported` ÷ total klaim yang butuh bukti | `verification`, `claim` |
| Hallucinated citation rate | sitasi yang dibuang saat validasi ÷ total sitasi yang dihasilkan | log validasi |
| Faithfulness | klaim `supported` ÷ total klaim | MiniCheck + sampel judge |
| Retrieval recall@k, MRR | gold chunk ditemukan di top-k | `eval/questions.jsonl` |
| Verifier agreement | Cohen's kappa vs label manual | `eval/gold_labels.jsonl` |

Aturan pelaporan:

- Hasil ditulis ke `eval/results/<run_id>/metrics.json` + `report.md`. Run lama tidak pernah ditimpa.
- Setiap laporan mencantumkan `run_id`, `config_hash`, versi model, seed, dan jumlah pertanyaan.
- Perbandingan antar konfigurasi memakai tabel yang sama, bukan angka yang diketik manual di README.

---

## 10. Reproducibility dan biaya

- `run.config_json` menyimpan config efektif setelah default digabung, bukan hanya path file.
- Embedding dan respons LLM di-cache di `data/cache/` dengan key = hash(model + input). Cache ikut di-gitignore.
- Setiap panggilan LLM mencatat token in/out; total per run ditulis di `metrics.json`.
- Batas keras jumlah panggilan per run ditetapkan di config, bukan hanya diharapkan (AGENTS.md §6).
- Test tidak pernah memanggil API berbayar; klien LLM dan embedder di-mock.

---

## 11. Konfigurasi

`configs/config.yaml` memuat seluruh knob. Kunci wajib (lihat file untuk nilai default):

`ingestion` (query, max_papers, page_size, request_delay_seconds, timeout_seconds, max_pdf_bytes, allowed_licenses), `chunking` (target_tokens, overlap_tokens, min_tokens), `embedding` (model, batch_size, device), `retrieval` (dense_top_k, bm25_top_k, rrf_k, rerank_candidates, final_top_k, use_reranker), `generation` (model, temperature, max_calls_per_run), `verification` (minicheck_model, judge_model, judge_sample_rate, seed), `evaluation` (ks, dataset_path).

---

## 12. Keputusan terkunci

Diputuskan sebelum M0. Mengubahnya berarti perubahan dependensi dan/atau pembangunan ulang indeks, jadi perlakukan seperti perubahan skema.

| Area | Keputusan | Konsekuensi |
|---|---|---|
| Domain v1 | RAG evaluation | Dataset uji dan query ingestion dibatasi pada topik ini |
| Sumber korpus | arXiv saja untuk v1 | OpenAlex/PMC masuk backlog v2 |
| Parser | PyMuPDF sebagai jalur utama | GROBID masuk backlog v2 |
| Vector store | LanceDB | Dependensi `lancedb`; filter metadata lewat kolom scalar |
| Keyword search | SQLite FTS5 | Tanpa dependensi tambahan; tokenizer diuji di M3 |
| Embedding | `BAAI/bge-base-en-v1.5` | Sesuai OVERVIEW §3.1a |
| Reranker | `BAAI/bge-reranker-base` | Sesuai OVERVIEW §3.1b |
| Verifier lokal | MiniCheck kelas ~0.8B | Muat bersama embedding+reranker di VRAM 8 GB |
| UI | Streamlit | Dependensi `streamlit`; token `DESIGN.md` dipetakan di M7 |
| Repo | `git init` lokal, `LICENSE` menyusul sebelum publikasi | Jangan publikasikan repo tanpa lisensi |

### 12.1 Yang masih terbuka

1. **Ambang `low_quality`:** rasio simbol/karakter aneh dan panjang minimum belum ditentukan. Diputuskan di M2 berdasarkan distribusi korpus nyata, bukan angka karangan.
2. **Jumlah paper final:** target 100–500 dari OVERVIEW; angka pastinya ditentukan setelah uji unduh M1.
3. **Provider LLM generator:** `deepseek-chat` sebagai default di config, tetapi provider final dipilih setelah uji biaya/latensi singkat di M5.
4. **ID model MiniCheck:** perlu diverifikasi ke Hugging Face saat M6 (`lytang/MiniCheck-Flan-T5-Large` atau varian RoBERTa yang lebih ringan). Jangan diasumsikan benar sebelum diuji.
5. **Komposisi dataset uji:** 30–50 pertanyaan dengan campuran lookup, comparison, synthesis, dan unanswerable; proporsi unanswerable (target ~10–15%) dikunci saat dataset dibuat.
