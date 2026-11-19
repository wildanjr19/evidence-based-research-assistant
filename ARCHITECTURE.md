# ARCHITECTURE.md

Spesifikasi teknis Evidence-Based Research Assistant. Dokumen ini adalah sumber kebenaran untuk arsitektur, skema data, format ID/sitasi, dan protokol evaluasi.

- Tujuan produk dan batasan: `OVERVIEW.md`
- Sistem desain UI: `DESIGN.md`
- Aturan kerja agent dan invarian proyek: `AGENTS.md`

**Status:** draft v0.1. Skema data (§4), format ID chunk (§5), dan format sitasi (§6) adalah kontrak tetap: mengubahnya berarti semua indeks dan hasil evaluasi harus dibangun ulang, jadi butuh persetujuan eksplisit (AGENTS.md §4.3, §10).

---

## 1. Prinsip

1. **Satu arah data.** Ingestion menulis SQLite + indeks. Retrieval hanya membaca. Generation memakai metadata store untuk validasi ID dan penyimpanan `run`/`answer`/`claim`; generation tidak mengubah paper, chunk, PDF, atau indeks.
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
  files.py         penulisan file atomik bersama, tanpa mengganti format ID
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
| 3 | Parse | PDF | teks per halaman dan section; referensi sebagai teks | `data/parsed/<safe_paper_id>.json` |
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

### Implementasi preprocessing M2

Parser memakai baris, bounding box, dan font dari PyMuPDF. Urutan baca dua kolom dipisahkan oleh baris yang melintasi tengah halaman. Teks margin hanya dibuang bila pola yang sama muncul di cukup banyak halaman, sesuai `parsing.margin_ratio`, `repeated_margin_ratio`, dan `min_repeated_pages`. Heading umum atau bernomor dideteksi dengan batas `heading_max_words`; bold parsial dalam daftar bernomor tidak dianggap sebagai bold seluruh heading. Ini heuristik, bukan ekstraksi struktur paper yang sempurna.

Artefak parsed menyimpan halaman 1-indexed, teks per baris, section, urutan section, serta manifest hash PDF, versi PyMuPDF, versi normalisasi, dan config parsing. Hash isi dokumen diverifikasi sebelum chunking. Parser memperbarui `paper.parse_status`; kegagalan satu paper tidak menghentikan paper lain. Detail kegagalan dan config efektif ditulis ke laporan run baru di `data/parsed/reports/` tanpa mengubah skema SQLite.

Tokenisasi M2 adalah `lexical-v1`: regex `\w+|[^\w\s]`, bukan tokenizer model. `n_tokens` menghitung token leksikal pada teks chunk. Batas section dipertahankan, overlap diterapkan dalam section yang sama, dan ordinal chunk tetap global per paper. Kebijakan `merge` boleh membuat chunk terakhir melebihi target ketika ekor pendek digabung; `drop` membuang ekor pendek. Section pendek yang tidak dapat digabung dalam section yang sama dibuang pada kedua kebijakan, dengan jumlah token yang dibuang dicatat. M3 wajib memeriksa batas tokenizer embedding sebelum indexing; tidak boleh memotong teks diam-diam.

Pengulangan parsing memerlukan manifest yang sama. Penyimpanan chunk hanya menerima data baru atau baris yang persis sama dengan yang sudah ada. Perubahan input/config yang menghasilkan artefak berbeda ditolak tanpa menghapus chunk atau menimpa hasil parsed lama; gunakan direktori/database terpisah untuk eksperimen. Nama file memakai `safe_paper_id` seperti M1, tanpa mengubah ID kanonis. OCR dan ekstraksi tabel/referensi terstruktur belum termasuk M2.

### Implementasi indexing M3

Indexing membaca snapshot seluruh chunk ber-ID valid dari paper dengan `parse_status=ok`, termasuk `low_quality`. Tokenizer model menghitung special tokens tanpa truncation; input di atas `min(embedding.max_tokens, model.max_seq_length)` ditolak sebelum encoding/penulisan indeks. Chunk lama tidak diubah. Gunakan database/direktori terpisah untuk target chunking baru.

Model BGE dikunci lewat `embedding.revision` berupa commit SHA, dengan embedding dokumen float32, ternormalisasi, tanpa prefix query. Cache per teks unik berada di `paths.cache_dir/embeddings/`; key mencakup hash teks dan identitas model/revision/dimensi/batas token/normalisasi/prefix. Cache diverifikasi sebelum dipakai. Bobot model berada di `paths.cache_dir/models/`.

Tabel LanceDB `chunks` di `paths.index_dir/vectors.lance/` menyimpan `chunk_id`, `paper_id`, rentang halaman, section, quality flag, hash teks, dan fixed-size vector float32. Manifest model terpisah mencegah pencampuran embedding yang tidak kompatibel. Indeks keyword memakai virtual table FTS5 `chunk_fts(chunk_id UNINDEXED, text)` dengan tokenizer `unicode61 remove_diacritics 2` dalam database korpus. Ini implementasi indeks yang direncanakan pada tahap 5; tabel inti §4 dan format sitasi tetap sama. Pencarian BM25 mengurutkan skor SQLite secara ascending.

Pengulangan hanya menambah ID yang belum ada, memverifikasi metadata/teks lama, dan memastikan jumlah baris kedua indeks sama dengan seluruh tabel `chunk`. Indeks yang berbeda, duplikat ID, atau cache rusak ditolak tanpa penghapusan otomatis. Indexing berjalan serial pada korpus yang tidak sedang dimodifikasi. Tidak ada transaksi lintas LanceDB dan SQLite; run parsial dilanjutkan dengan input sama dan belum dianggap sukses sebelum kedua jumlah cocok.

Laporan baru di `paths.index_dir/reports/` mencatat config/hash, seed, versi library, model/revision, waktu termasuk pemuatan model/unduhan, jumlah chunk/vektor/FTS, token model seluruh chunk, token teks unik yang di-encode, embedding baru, dan cache hit teks unik. Laporan gagal juga disimpan; nama run dipesan sebelum indexing dan tidak menimpa run lama. Belum ada filter kualitas, fusion, reranking, atau evaluasi retrieval pada M3.

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

### Implementasi M4

`retrieval.Retriever` membuka SQLite dengan `mode=ro`, memuat snapshot chunk kanonis, dan memeriksa indeks yang dipakai terhadap snapshot itu. Indeks yang hilang/parsial, teks atau metadata yang berbeda, dan model query yang tidak cocok dengan manifest M3 ditolak. Retrieval tidak membuat tabel atau memperbarui korpus. Jalankan pada korpus yang tidak sedang diubah. Model dimuat saat diperlukan; BM25 dan hasil kosong karena semua chunk `low_quality` tidak memuat model.

BM25 mengekstrak term leksikal, mengutipnya sebagai literal FTS5, lalu menggabungkannya dengan OR; operator dari input pengguna tidak dieksekusi sebagai sintaks FTS. Filter kualitas diterapkan sebelum LIMIT. Dense memakai cosine exact search di LanceDB dengan prefilter kualitas. Semua jarak kandidat diurutkan menurut jarak lalu ID, termasuk skor seri pada batas top-k. Ini baseline exact scan untuk skala v1, bukan ANN. Kedua indeks hanya mengembalikan ID/skor; teks dan metadata jawaban diambil dari snapshot SQLite.

Query embedding memakai `retrieval.query_prefix`, default instruksi Inggris dari [model card BGE](https://huggingface.co/BAAI/bge-base-en-v1.5), tanpa mengubah embedding dokumen M3. Nilai kosong menonaktifkan prefix. Batas tokenizer mencakup prefix dan special tokens, tanpa truncation. Encoding memakai cache embedding M3 berdasarkan teks berprefix dan identitas model. RRF memakai rank mulai 1, satu kontribusi per ID per daftar, bobot sama, dan pemecah skor seri menurut ID. Hasil fusion dibatasi `rerank_candidates` sebelum reranking opsional, kemudian `final_top_k` untuk konteks jawaban.

[BGE reranker](https://huggingface.co/BAAI/bge-reranker-base) memakai revision commit yang dikunci, inference lokal/eval, dan satu raw logit per pasangan query/dokumen. Device mengikuti embedding; batch serta panjang pasangan berasal dari config. Kebijakan `only_second` mempertahankan query dan memotong hanya tampilan dokumen untuk reranker. Query yang tidak menyisakan ruang ditolak. Chunk asli dan ID sitasi tidak diubah. Cache per pasangan mencakup model/revision, batas token, kebijakan truncation, serta hash query dan teks. Nilai cache/inference harus finite. Skor BM25, cosine, RRF, dan logit memiliki jenis berbeda dan tidak dibandingkan lintas mode.

### Evaluasi retrieval M4

`python -m rag.evaluation` menjalankan empat mode atau satu mode pilihan. Format dataset tetap seperti §4; fixture validasi sintetis berada di `tests/fixtures/`, terpisah dari gold set final M6. Runner memvalidasi qid, tipe pertanyaan, ID chunk/paper, dan keanggotaan gold chunk dalam korpus; tidak menulis ulang dataset.

Ranking evaluasi memiliki kedalaman `max(evaluation.ks)` agar default Recall@20 tidak dibatasi `final_top_k=8` untuk prompt. Kapasitas dense/BM25/fusion tetap mengikuti config. MRR dihitung terhadap ranking yang dikembalikan pada kedalaman itu (default 20), dengan 0 bila tidak ada gold yang ditemukan. Recall dan MRR dirata-ratakan per pertanyaan answerable. Pertanyaan unanswerable tetap dilaporkan, dengan metrik `null` dan tanpa kontribusi pada rata-rata; evaluasi abstention/faithfulness menunggu generation dan M6.

Setiap mode memesan direktori run baru, lalu menyimpan `metrics.json`, `per_question.jsonl`, dan `report.md`, termasuk pada kegagalan inference. Manifest mencatat mode, kedalaman ranking, config efektif/hash, seed, code version, versi library/SQLite, identitas model dan backend aktual, versi tabel vektor, hash dataset/korpus, jumlah pertanyaan, statistik cache, dan waktu. Override path dataset dicatat pada config efektif. Nama direktori memakai run ID dengan `:` diganti `-` untuk Windows; run ID di JSON tetap sesuai `ids.py`. Hasil lama tidak ditimpa.

---

## 8. Generation dan verifikasi

- Prompt hanya berisi chunk hasil retrieval. Tidak ada pengetahuan luar, tidak ada instruksi "gunakan pengetahuanmu" (AGENTS.md §4.1).
- Chunk di prompt diberi label `chunk_id` eksplisit agar model bisa merujuk tanpa mengarang.
- Bila tidak ada chunk yang mendukung sebuah klaim, model diinstruksikan menandainya `unsupported: true` alih-alih mengisi sitasi asal.

### Implementasi M5

`generation.generate_answer` menerima pertanyaan dan hasil retrieval. Metadata store memeriksa ID, teks, paper, halaman, section, kualitas, serta status parsing terhadap SQLite; konteks yang berubah atau duplikat ditolak sebelum inference. Judul referensi selalu diambil dari database. `answer_question` menghubungkan retrieval M4 dengan generator; caller yang sudah memiliki chunk dapat memanggil `generate_answer` langsung. Context kosong menyelesaikan run dengan nol klaim tanpa panggilan LLM.

Prompt terdiri atas instruksi grounding/format generik dan JSON pertanyaan/chunk kanonis. Tidak ada contoh fakta dari luar konteks. Instruksi di dalam pertanyaan/chunk diperlakukan sebagai data tak tepercaya. Output harus mengikuti format §6, tanpa field tambahan atau key JSON duplikat. Respons non-JSON, struktur tidak valid, Unicode tidak valid, atau finish reason selain `stop` memperoleh satu retry format. Retry memakai bukti yang sama, tanpa menambahkan klaim dari respons gagal ke prompt. Setelah dua kegagalan, run berstatus gagal dan tidak menyimpan klaim parsial.

Parser sitasi tetap murni: caller memasok himpunan ID korpus dan konteks. Sintaks salah, ID hilang, dan ID di luar konteks dicatat terpisah lalu dibuang. Urutan sitasi valid dipertahankan setelah deduplikasi. Klaim tanpa sitasi valid dipertahankan dengan `unsupported=true`; flag unsupported dari LLM tidak dihapus meskipun ada ID valid. Renderer membuat nomor referensi dari ID kanonis, dengan judul, rentang halaman, section, dan kutipan asli. Teks/metadata di-escape untuk Markdown. Validitas ID belum menjadi bukti dukungan semantik; hasil masih berlabel "belum diverifikasi" sampai M6.

Adapter mendukung provider DeepSeek dan OpenAI melalui SDK OpenAI yang sudah menjadi dependensi. Endpoint standar dipilih dari provider, atau `generation.base_url` berupa HTTPS tanpa credential/query/fragment. API key dibaca dari environment sesuai provider; bila variabel belum ada, adapter mengambil key terpilih dari `.env` di direktori kerja tanpa mengubah environment proses. Loader terbatas pada assignment satu baris dengan kutip/komentar opsional; tidak ada eksekusi, interpolasi, atau pemuatan variabel lain. CLI memerlukan `--allow-api` untuk cache miss; tanpa flag itu tidak ada panggilan provider. SDK memakai timeout dan batas token output dari config, JSON object mode, serta `max_retries=0` agar retry transport tidak melewati `max_calls_per_run`. Rujukan: [DeepSeek JSON Output](https://api-docs.deepseek.com/guides/json_mode/) dan [OpenAI Chat Completions](https://developers.openai.com/api/reference/python/resources/chat/subresources/completions/methods/create).

Cache `paths.cache_dir/llm/` memakai provider/endpoint, model, temperature, batas output, backend, dan seluruh prompt sebagai identitas. Namespace backend memisahkan mock dari provider nyata. Respons menyimpan model yang dilaporkan server, input/output tokens, finish reason, provenance, dan checksum. Cache rusak ditolak tanpa penghapusan/panggilan pengganti otomatis. Cache hit memakai nol jatah panggilan/token baru; usage asli tetap dicatat. Usage hilang atau invalid menyebabkan kegagalan dengan `unknown_usage_attempts`, bukan asumsi biaya nol. Total token pada laporan menjumlahkan usage baru yang diketahui, termasuk respons gagal format. Counter backend adalah jumlah attempt, termasuk mock/attempt yang gagal; bukan bukti tagihan provider.

Metadata store membuat tabel `run`, `answer`, dan `claim` persis sesuai §4, tanpa mengubah tabel sumber atau format ID/sitasi. Nama kolom tabel hasil yang tidak cocok ditolak sebelum membuat tabel lain. Run/answer/claim ditulis secara append; internal `answer_id` memakai `<run_id>:a01` dan `claim_id` memakai `<answer_id>:c<ordinal>`. ID internal ini bukan ID sitasi. `answer.raw_response` menyimpan respons terakhir yang diterima pipeline; laporan/cache mempertahankan attempt sebelumnya. `run.notes` menyimpan status, statistik token/cache, kegagalan format, dan sitasi yang ditolak. Model embedding/reranker pada run BM25 dibiarkan NULL.

Laporan `paths.index_dir/reports/generation-<run_id>.json` dipesan dengan mode create-exclusive sebelum inference. Laporan mencatat config/hash, seed, code version, context ID/hash, backend, versi SDK, attempt/usage, klaim, referensi, serta status verifikasi. Kegagalan penyimpanan diberi status gagal pada laporan. Run/report lama tidak ditimpa. Seed disimpan untuk penelusuran eksperimen; determinisme keluaran provider belum dijamin, sehingga pengulangan memakai cache respons.

Pengguna memilih `deepseek-flash` sebagai generator; config memakai `generation.thinking: false`. Adapter DeepSeek mengirim `extra_body.thinking.type` berupa `disabled` atau `enabled`, mengikuti [Thinking Mode](https://api-docs.deepseek.com/guides/thinking_mode/); parameter tidak dikirim ke OpenAI. Mode thinking menjadi bagian identitas cache, dengan nilai default `false` untuk config lama. Verifikasi M5 memakai mock/transport lokal; uji API nyata setelah penutupan M5 berhasil pada satu pertanyaan dan pengulangan cache. Hasilnya dicatat di TASKS.md; kualitas jawaban lintas pertanyaan dan perbandingan model belum dievaluasi.

### Verifikasi klaim (M6)

Verifikasi dua lapis (default, sesuai OVERVIEW §3.1c):

1. **MiniCheck (lokal)** untuk semua pasangan (klaim, chunk) → label + skor.
2. **LLM-judge dari keluarga model berbeda** untuk sampel ~20–30% klaim → label + alasan.
3. **Label manual** 50–100 pasangan sebagai gold → Cohen's kappa antara verifier dan manusia.

Pemilihan sampel memakai seed dari manifest run agar reproducible.

### Implementasi awal M6

`verification.MiniCheck` melalui modul `verification.minicheck` memakai dependensi
Transformers/PyTorch yang sudah ada. ID model diverifikasi melalui API Hugging
Face pada 2026-11-18: `lytang/MiniCheck-Flan-T5-Large`, revision
`96eafd01cee2d16cf81aaa2fb226b14f422a37b3`, metadata lisensi MIT. Format input dan
softmax token label mengikuti kode upstream. Adapter v1 menilai pasangan utuh,
tanpa segmentasi kalimat atau truncation. Input melampaui batas config/model
ditolak sebagai belum terverifikasi. Cache mencakup identitas backend/model,
revision, kebijakan input, device, threshold, dan hash kedua teks; checksum serta
provenance diperiksa saat membaca.

`verification.pipeline.verify_answer` memeriksa klaim terhadap generation yang
tersimpan, membaca bukti kanonis dari SQLite, lalu menambah baris pada tabel
`verification` persis sesuai §4. Tabel dengan kolom berbeda ditolak; hasil lama
tidak diganti. Gagal inference dicatat di laporan dengan label null, tanpa
menulis label semantik palsu ke tabel atau menghilangkan klaim.

`evaluation.citations.evaluate_citations` menghubungkan ranking M4, konteks
`final_top_k`, generation M5, verifier, sampel judge opsional, dan metrik §9.
Client generation dibagi antar pertanyaan/mode agar batas request mencakup
seluruh batch; judge mempunyai batas batch terpisah. Sampel memakai kunci
qid/ordinal dan seed agar tidak bergantung pada ID run acak. Keluarga judge dan
generator harus berbeda pada endpoint provider standar atau gateway Surplus
yang dibatasi secara eksplisit. Label judge serta
agreement dilaporkan terpisah dari metrik utama MiniCheck.

Metrik dihitung dengan penyebut eksplisit: pasangan tersitasi, semua klaim
termasuk unsupported, dan ID unik per klaim setelah deduplikasi M5. Semua ID
yang ditolak validasi dihitung pada hallucinated citation rate. Klaim pada
unanswerable tidak mendapat kredit dukungan; generation gagal tidak mendapat
kredit abstention. Metrik dukungan agregat null bila generation gagal atau
verifikasi tidak lengkap; jumlah kegagalan/cakupan tetap dilaporkan. Penyebut
nol menghasilkan null. Aturan ini mencegah kegagalan terlihat sebagai skor baik.

Laporan mencatat hash dataset/korpus/config, versi model/backend/library, seed,
tipe/jumlah pertanyaan, ranking, klaim/ID sumber, usage, statistik cache, dan
peak RAM/VRAM proses. Kutipan penuh tidak ditulis ke hasil evaluasi di `eval/`;
pasangan untuk anotasi diekspor ke `data/annotations/` tanpa label atau prediksi
verifier. Label manusia dicocokkan berdasarkan hash klaim, chunk ID, dan hash
teks sumber. `evaluation.agreement` menilai file berlabel manusia secara lokal
dan menghitung Cohen's kappa tanpa bobot pada tiga kelas; label parsial tetap
kelas berbeda dari dua kelas keluaran MiniCheck. Belum ada label manusia nyata.

Draf 30 pertanyaan satu paper di `eval/questions.draft-v1.jsonl` belum menjadi
gold set manual final. Rincian provenance, bahan anotasi, dan batas cakupan ada
di `eval/README.md`; verifikasi/handoff ada di TASKS.md. Tidak ada perubahan
skema SQLite, format sitasi, dataset final, atau konfigurasi sumber CUDA.

### Judge generatif melalui Surplus

`verification.judge_provider: surplus-chat` memakai Chat Completions dengan
`SURPLUS_API_KEY`, `SURPLUS_API_URL`, dan `GPT_MODEL_ID` dari environment/`.env`.
Endpoint dibatasi ke HTTPS `api.surplusintelligence.ai/v1`, tanpa credential,
query, atau fragment. Model harus keluarga GPT; generator OpenAI tetap ditolak
karena gateway tidak membuat kedua model berasal dari keluarga berbeda.
Config/hash run mencatat model dan endpoint efektif. Respons harus melaporkan
model yang diminta atau snapshot bertanggalnya; substitusi model ditolak.

Judge tetap menghasilkan label dan alasan sesuai protokol M6. Cache M5
membedakan provider/endpoint/model/backend/prompt; token dan model respons
dicatat. Batas batch dan larangan retry SDK tetap berlaku. Adapter memakai SDK
yang sudah terpasang, tanpa perubahan skema SQLite atau format sitasi.

### Jev decision judge opsional (pilot M6)

Pengguna mengizinkan eksperimen Jev melalui Surplus pada 2026-11-18.
`verification.jev.JevJudge` menilai pasangan yang sama dengan tiga pilihan label
dukungan melalui native `POST /v1/decisions`. Format `state` dan map `questions`
mengikuti [kontrak Surplus](https://www.surplusintelligence.ai/docs/api-reference/decisions).
Adapter membaca `SURPLUS_API_KEY`, `SURPLUS_API_URL`, dan `JEV_MODEL_ID` melalui
loader environment/`.env` yang sudah ada, tanpa mengeksekusi nilai atau mencetak
key. Endpoint dibatasi ke HTTPS Surplus `/v1` atau `/v1/decisions`, tanpa
credential/query/fragment; redirect dan retry otomatis dinonaktifkan.

`verification.judge_provider: surplus` mengaktifkannya pada runner sitasi.
Model dari `JEV_MODEL_ID` serta endpoint efektif dicatat dalam config/hash run.
ID alias rolling ditolak; model yang dilaporkan server harus berasal dari versi
Jev yang diminta. Full resolved model, probabilitas tiap label, confidence, usage,
dan HTTP latency dipertahankan. Confidence adalah keluaran model, belum ambang
yang dikalibrasi terhadap gold lokal. Generator harus keluarga berbeda yang
dikenali; default generator DeepSeek tidak berubah.

Berbeda dari judge generatif default, Jev tidak menulis alasan naratif. Ekstensi
pilot ini memakai `rationale=NULL` dan score probabilitas supported, sesuai kolom
nullable yang sudah ada; tidak mengarang alasan atau mengubah skema. Baris SQL
tetap `verifier=llm_judge`; laporan memberi `judge_kind=decision`. Primary metrics
MiniCheck dan kebutuhan 50–100 label manusia tetap mengikuti protokol M6.

Request/response Jev memakai cache M5 dengan identitas backend, endpoint, model,
dan payload native lengkap. Backend jaringan bertanda `requires_api` sehingga
tetap memerlukan `--allow-api`, meskipun diinjeksikan ke client cache. Seluruh
batch tunduk pada `judge_max_calls_per_run`. Mock memakai namespace berbeda.
Probabilitas harus finite, lengkap untuk tiga label, berjumlah satu, dan cocok
dengan pilihan pemenang. Refusal, model lain, respons rusak, atau usage hilang
tidak dijadikan label valid. Gagal tidak memicu request pengganti otomatis.

`python -m rag.evaluation.decisions` menjalankan perbandingan pilot yang membaca
SQLite tanpa menulisnya, seperti evaluasi retrieval M4. Input pasangan dicek
terhadap hash chunk kanonis, sampel dibekukan dengan seed sebelum inference,
dan laporan ditulis pada direktori run baru. Label kandidat/label manusia tidak
dipakai sebagai target atau diubah. Agreement dihitung hanya pada pasangan yang
berhasil diperiksa kedua model, dengan coverage dan kegagalan tetap dilaporkan.
`accuracy_against_human_gold` tetap null bila tidak ada evaluasi manusia.

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

`ingestion` (query, max_papers, page_size, request_delay_seconds, timeout_seconds, max_pdf_bytes, allowed_licenses), `parsing` (margin_ratio, repeated_margin_ratio, min_repeated_pages, heading_max_words), `chunking` (target_tokens, overlap_tokens, min_tokens, short_chunk_policy, tokenizer), `embedding` (model, revision, max_tokens, batch_size, device), `retrieval` (dense_top_k, bm25_top_k, rrf_k, rerank_candidates, final_top_k, use_reranker), `generation` (model, temperature, max_calls_per_run), `verification` (minicheck_model, judge_model, judge_sample_rate, seed), `evaluation` (ks, dataset_path).

Untuk kompatibilitas config M0/M1, bagian `parsing` dan field baru `chunking.short_chunk_policy`/`tokenizer` memakai default bila tidak diberikan. Nilai efektif tetap disimpan di laporan. Nilai eksplisit yang salah, termasuk `parsing: null`, tetap ditolak.

Config sebelum M3 memakai default `embedding.revision: a5beb1e3e68b9ab74eb54cfd186867f64f240e1a` dan `max_tokens: 512`. Revision itu milik `BAAI/bge-base-en-v1.5`; mengganti model wajib menyertakan revision yang sesuai. Device menerima `cpu`, `cuda`, atau `cuda:<index>`, tanpa fallback CPU diam-diam.

Config sebelum M4 memakai default `retrieval.query_prefix: 'Represent this sentence for searching relevant passages: '`, `reranker_revision: 2cfc18c9415c912f9d8155881c133215df768a70`, `reranker_max_tokens: 512`, dan `reranker_batch_size: 16`. Revision default milik `BAAI/bge-reranker-base`; mengganti reranker memerlukan revision model yang sesuai. Revision wajib commit SHA 40 karakter. Default M3 CPU dan lockfile CUDA tidak berubah.

Config sebelum M5 memakai default `generation.max_output_tokens: 2048`, `timeout_seconds: 60.0`, dan `base_url: ''` (endpoint standar provider). Config tanpa `generation.thinking` memakai `false`; field ini mengatur thinking pada DeepSeek. Provider generation yang diimplementasikan adalah `deepseek` dan `openai`; nilai lain ditolak. `max_calls_per_run` tetap mencakup retry format. Konfigurasi tidak memuat API key; adapter membaca environment atau key provider terpilih dari `.env` sesuai aturan di atas.

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

1. **Kalibrasi `low_quality`:** baseline M2 menandai karakter pengganti Unicode (`U+FFFD`) dan kontrol rusak; batas panjang memakai `chunking.min_tokens`. Uji awal satu PDF tidak menemukan karakter pengganti, sehingga belum cukup untuk menetapkan ambang rasio simbol pada korpus penuh. Kalibrasi kuantitatif tetap terbuka dan tidak dianggap selesai oleh flag baseline ini.
2. **Jumlah paper final:** target 100–500 dari OVERVIEW; angka pastinya ditentukan setelah uji unduh M1.
3. **Provider LLM generator:** pengguna memilih `deepseek-flash` dengan thinking nonaktif; uji koneksi/format API satu pertanyaan berhasil sebelum M6. Kualitas lintas pertanyaan dan perbandingan provider belum diuji.
4. **ID model MiniCheck:** perlu diverifikasi ke Hugging Face saat M6 (`lytang/MiniCheck-Flan-T5-Large` atau varian RoBERTa yang lebih ringan). Jangan diasumsikan benar sebelum diuji.
5. **Komposisi dataset uji:** 30–50 pertanyaan dengan campuran lookup, comparison, synthesis, dan unanswerable; proporsi unanswerable (target ~10–15%) dikunci saat dataset dibuat.
