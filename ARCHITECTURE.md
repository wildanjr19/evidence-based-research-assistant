# Arsitektur dan kontrak teknis

Skema SQL (4), ID (5) dan sitasi (6) tetap; perubahan memerlukan persetujuan eksplisit.
Operasi: [USAGE.md](USAGE.md). Persiapan: [KB-PREPARATION.md](KB-PREPARATION.md).
Status/hasil: [TASKS-SKRIPSI.md](TASKS-SKRIPSI.md); MVP: [TASKS.md](TASKS.md).

## 1. Prinsip

Jawaban hanya dari chunk hasil retrieval, dengan sitasi per klaim ke bukti kanonis.
Persiapan korpus terpisah dari query; hash/versi/sumber/lisensi/halaman dapat ditelusuri.
Blok held dikeluarkan sebelum SQL/index. Eksperimen memakai snapshot/run baru dan
config/hash/model/revision/seed; label tidak berpindah karena string ID sama.
Logika terpisah dari I/O; korpus/cache tetap lokal di `data/`, tidak di-commit.

## 2. Peta modul

| Modul di `src/rag/` | Tanggung jawab |
|---|---|
| `config.py`, `ids.py`, `files.py` | Config tervalidasi, ID dan penulisan atomik |
| `ingestion/` | Bibliografi, metadata/lisensi, budget unduhan dan admission |
| `parsing/`, `chunking/` | PyMuPDF baseline; Docling, gate dan chunk narasi/tabel |
| `indexing/`, `retrieval/` | BGE/cache, LanceDB/FTS5, BM25/dense/RRF/reranker |
| `generation/`, `verification/` | Klaim/sitasi JSON, provider/cache, MiniCheck/judge |
| `evaluation/`, `ui/` | Orkestrasi evaluasi/reproduksi dan Streamlit |

## 3. Data flow

Sumber ? admission ? parsing/gate ? chunking ? indexing. Query UI ? retrieval ?
generation ? jawaban bersitasi; RAGAS dan MiniCheck dipicu terpisah setelah jawaban.
KB UI aktif hasil Docling, `configs/skripsi-local.yaml`: 41 PDF/40 searchable/2.514 chunk.
CLI PyMuPDF, pilot lima PDF dan benchmark M6 tetap tersedia terpisah. Parsing tidak
berjalan saat query. DeepSeek Flash non-thinking adalah generator; JEV masih eksperimen.

### Admission

`import-bib` menghasilkan entries/references/audit, tanpa paper/chunk. Downloader
lama memeriksa identitas/lisensi, host/HTTPS/redirect/ukuran/cache dan ledger persisten
sebelum transfer; default tanpa jaringan, lock mencegah budget paralel. `prepare-bib`
mengikat hash/provenance PDF siap ke snapshot dan alias citation key.

`prepare-local` wajib inventaris, manifest berhash dan DB baru; default maksimal tiga
PDF, batch memakai `--max-documents` eksplisit di bawah batas config. Jalur default
memerlukan identitas/lisensi artikel dari HTML, DOI tercetak, halaman PDF atau receipt
snapshot sama. DOI baru boleh melengkapi field kosong, DOI lama harus cocok.
`fetched_at` adalah observasi lokal. Lisensi dataset bukan lisensi artikel.

Instruksi pengguna 2026-11-20 mengizinkan `--local-collection` dengan manifest
`admission_policy: user_local_collection`. Hash/path/ukuran/halaman tetap diperiksa.
Identitas terverifikasi dipertahankan; sisanya `local:sha256_<hash-PDF>` dan
`LicenseRef-UserProvided-Unverified`, DOI opsional, landing URL file lokal.
Ini bukan klaim OA/izin redistribusi dan tidak melonggarkan downloader. Receipt
mengikat reference ID/citation key/hash untuk UI. PDF tanpa chunk lolos tetap
terdaftar `parse_status=held` pada koleksi lokal, bukan bukti searchable.

### Parser dan chunker

PyMuPDF menata baris/dua kolom, Unicode, margin berulang dan section heuristik.
`ParsedPaper`/`TextBlock` mengikat halaman/section dan manifest PDF/parser/config/hash.
Chunk narasi memakai ordinal global; `lexical-v1` bukan tokenizer model. Ekor
`merge`/`drop` dilaporkan, `low_quality` menandai karakter rusak baseline.

Docling isolated memakai Heron/TableFormer accurate/EasyOCR id/en CUDA, batch satu,
model pinned/offline, OCR selektif, `do_cell_matching=True`. Extract maksimal tiga
PDF lengkap terdaftar; opsi subclass Pydantic diserialisasi lengkap. JSON/Markdown/
HTML/native comparison disimpan. Build Python utama memeriksa hash sumber dan
menghitung ulang gate; ekstraksi gagal tidak boleh menjadi subset sukses diam-diam.
Raw hanya dipakai ulang jika hash PDF/model/backend cocok; build gabungan mencatat asal.

- Halaman asli eksplisit; gambar/rumus/kode dan tipe belum didukung bukan bukti.
- Narasi dicek terhadap region native; overlap tabel tidak lolos sebagai teks rata.
- Tabel wajib caption/header/label baris/grid utuh, token native berurutan dan geometri
  benar. Minus/desimal/tanda baca dipertahankan; `-` identik bukan mismatch.
- Header bertingkat `parent / child`, rowspan label hanya kolom pertama dengan flag
  eksplisit; row-section satu baris penuh. Span tumpang tindih, body berlubang,
  header ambigu, sel lintas baris tak dideklarasikan dan band baris overlap ditahan.
- Caption/header/catatan/halaman dan konteks kelompok diulang; pipe/newline/quote
  di-escape sebagai string JSON. Baris+konteks overlength menahan seluruh tabel.
- Narasi Docling memakai callback tokenizer: jendela leksikal dipendekkan agar muat,
  overlap selalu maju dan merge ekor tetap berbatas; unit tunggal overlength held.
  Tanpa callback, chunker PyMuPDF lama tetap. Jangan mencampur artefak kedua chunker.
- `native_word_coverage=0.8`, `header_center_tolerance=0.25` (pitch subheader terkecil)
  masih heuristik, bukan kalibrasi manusia. OCR tanpa pembanding/native rusak tetap held.
  Tidak wajib koreksi manual seluruh paper; tidak ada voting/per-table switching otomatis.

### Indexing dan UI

Embedding BGE float32 ternormalisasi/revision pinned, dokumen tanpa prefix; tokenizer
termasuk special tokens dicek tanpa truncation. Cache membedakan model/revision/
dimensi/batas/normalisasi/prefix dan menolak file rusak. LanceDB mengikat hash/metadata;
FTS5 `chunk_fts(chunk_id UNINDEXED, text)` memakai `unicode61 remove_diacritics 2`.
SQL/vektor/FTS harus konsisten; tidak ada transaksi lintas store, run parsial belum sukses.

Retrieval membaca sumber/index; generation menulis run/answer/claim, verification
menulis dukungan. Model tidak dimuat pada retrieval kosong/semua low-quality.
Query UI memakai backup DB baru; demo baca-saja terikat hash seluruh chunk dan
jawaban SQL. Alias bibliografi wajib cocok dengan sumber/seluruh korpus. Pergantian
identitas/config mereset jawaban/izin. Snapshot DB UI menyalin delapan jawaban pilot
KB penuh; manifest mengikat asal/hash, indeks/chunk tetap KB penuh.

Retrieval UI tetap empat mode produksi, default hybrid; helper refinement belum
dipromosikan. Cache miss generation tetap memperlihatkan bukti pencarian, bukan
klaim jawaban. Preview/unduh PDF hanya dari raw/pdf dengan nama kanonis, path aman,
hash SQL cocok dan halaman asli. Sumber lokal/unverified/held diberi label eksplisit.

## 4. Skema data (SQLite)

Database mengikuti `paths.db_path` (default `data/index/corpus.db`); setiap snapshot eksperimen memakai lokasi terpisah.
Vektor di LanceDB dirujuk dengan `chunk_id`. Definisi tabel inti berikut dipertahankan:

```sql
-- Metadata paper. Satu baris per versi paper yang diindeks.
CREATE TABLE paper (
    paper_id      TEXT PRIMARY KEY,      -- "arxiv:2401.12345v1"
    source        TEXT NOT NULL,         -- arxiv | openalex | pmc | crossref | local
    source_id     TEXT NOT NULL,         -- ID sumber, termasuk identitas snapshot bila diperlukan
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
    parse_status  TEXT NOT NULL DEFAULT 'pending'  -- pending|ok|failed|held
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

`verification` mendukung beberapa verifier pada pasangan sama; partial tetap kelas tersendiri.
`claim.citations` adalah JSON array berurutan. Lisensi tidak boleh kosong. FTS/vector store adalah indeks turunan.

## 5. Format ID

- Paper: `<source>:<source_id>`; arXiv wajib versi positif, misalnya `arxiv:2401.12345v1`.
- Snapshot DOI: `crossref:<DOI lowercase>_sha256_<SHA-256 PDF>`; hash bukan versi publikasi rekaan.
- Koleksi lokal belum terverifikasi: `local:sha256_<SHA-256 PDF>`; bukan identitas DOI palsu.
- Chunk: `<paper_id>:p<page>:c<ordinal>`; halaman awal PDF 1-9999, ordinal global per paper 1-9999, minimal dua digit.
- Run: `YYYY-MM-DDTHH:MM:SSZ_<6 hex>`, UTC. Nama berkas mengganti colon jika diperlukan Windows.

Regex chunk tetap, divalidasi bersama versi paper dan nilai positif oleh `ids.py`:

```text
^[a-z]+:[A-Za-z0-9._\-/]+:p[0-9]{1,4}:c[0-9]{2,4}$
```

Contoh: `arxiv:2401.12345v1:p7:c03`. Section tidak masuk ID. Nama berkas aman (`paper_file_stem`) bukan ID baru.
Ordinal deterministik; strategi chunk/parser berubah memerlukan snapshot/index baru dan peninjauan label yang sesuai.

## 6. Format sitasi

Contoh format, bukan keluaran eksperimen:

```json
{"claims": [{"text": "Klaim dari konteks.", "citations": ["arxiv:2401.12345v1:p7:c03"]}]}
```

Parser menolak struktur/field/JSON duplikat yang salah. ID wajib lolos regex, ada di SQL, dan berada dalam konteks yang dikirim.
ID invalid/di luar konteks dibuang serta dicatat; deduplikasi menjaga urutan. Klaim tanpa sitasi valid disimpan sebagai unsupported.
Flag `unsupported: true` dari model dipertahankan. Nomor `[1]` hanya tampilan; judul/halaman/kutipan berasal dari sumber kanonis.
Validitas ID belum membuktikan dukungan makna. Abstention unanswerable memakai `{"claims": []}`;
penolakan berupa klaim unsupported tetap gagal kontrak nol klaim.

## 7. Retrieval

| Mode | Perilaku |
|---|---|
| BM25 | Term dikutip literal; skor SQLite ascending, filter low-quality sebelum LIMIT |
| Dense | Cosine exact scan LanceDB dengan identitas model cocok dan prefilter kualitas |
| Hybrid | RRF: `sum(1 / (rrf_k + rank))`, rank mulai satu, kontribusi unik per daftar, bobot sama |
| Hybrid + rerank | Kandidat RRF dibatasi lalu diberi satu logit per pasangan oleh BGE reranker |

Tie dipecahkan dengan ID. Kapasitas/top-k dari config. Skor BM25/cosine/RRF/logit tidak dibandingkan lintas jenis.
Query embedding memakai `retrieval.query_prefix`; cache memisahkan prefix/revision/batas token.
Reranker boleh memotong tampilan dokumen (`only_second`); query utuh wajib muat. Chunk/kutipan kanonis tidak berubah.
Cache pasangan mengikat model, query/dokumen, batas dan truncation; skor wajib finite.

## 8. Generation dan verifikasi

Prompt memuat grounding, pertanyaan dan chunk yang cocok SQL; isi pengguna/chunk
adalah data tak tepercaya. Provider generator DeepSeek/OpenAI; runtime DeepSeek Flash
non-thinking. Cache mengikat thinking/backend/provider/endpoint/model/parameter/
prompt/checksum, mock memakai identitas lain. Respons/model/finish reason/usage dicatat;
usage unknown bukan nol. Default cache-only; API membutuhkan izin/budget. Retry
transport nol; satu koreksi format dengan konteks sama ikut jatah. Respons tetap
salah gagal tanpa klaim parsial; error/cache miss bukan abstention. Endpoint kustom
wajib HTTPS tanpa credential/query/fragment; key environment/`.env` tidak dilog.

MiniCheck `lytang/MiniCheck-Flan-T5-Large` menilai pasangan utuh dengan threshold
config. Overlength unverified tanpa truncation; error bukan supported. Cache
mengikat klaim/evidence/model/revision/adapter/device/batas/threshold/backend;
hasil append-only, klaim tetap disimpan.

Judge memakai keluarga berbeda dari generator, sampel berseed, label/alasan tervalidasi.
`surplus-chat` memakai `SURPLUS_API_KEY`, `SURPLUS_API_URL`, `GPT_MODEL_ID`, HTTPS
Surplus `/v1` dan host/model tervalidasi. JEV native `surplus` `/v1/decisions` wajib
`jev-1.14`, tanpa rolling alias/retry/redirect. Probabilitas/model aktual/confidence/
usage/latensi disimpan, rationale null; confidence belum terkalibrasi. Pasangan
pembanding harus sama teks/hash. Agreement judge terpisah dari metrik MiniCheck.

### Kebijakan pelaporan verifier

`ui.service.support_label` merangkum keputusan mesin sesuai prioritas berikut:

| Kondisi | Status UI |
|---|---|
| Unsupported atau sitasi kosong | Tidak ada bukti |
| Semua sitasi supported MiniCheck | Didukung MiniCheck |
| Ada sitasi not_supported/partially_supported, meski lainnya belum dinilai | Perlu diperiksa |
| Kondisi lain, termasuk hasil hilang/error | Belum diverifikasi |

Label bukan vonis kebenaran. "Tidak ada bukti" hanya kontrak klaim/konteks, bukan
seluruh korpus. Penolakan model bukan bukti fakta salah; hasil hilang bukan penolakan.
Judge/manual/klaim lain tidak menimpa ringkasan MiniCheck. Audit sumber terpisah
mencatat AI/manusia, chunk/halaman/hash/alasan/batas. Audit AI bukan label manusia.
Konflik angka dicatat tanpa memilih angka agar skor membaik; label/probabilitas asli
tetap. Terjemahan, pelemahan atribusi, serialisasi atau view berskor tertinggi belum
boleh mengganti hasil kanonis.

UI memerlukan semua sitasi supported; citation recall/faithfulness implementasi
memerlukan sedikitnya satu per klaim (bagian 9). Denominator harus dibedakan.
Nol klaim tanpa konteks dan penolakan provider berkonteks dilaporkan terpisah;
cache miss/error generation adalah kegagalan.

### Evaluasi kualitas jawaban di UI

`evaluation/answer_quality.py` membekukan jawaban kanonis dan seluruh konteks
generation termasuk tak disitasi, memeriksa hash DB/laporan/konteks/input/config
serta kesamaan jawaban tampilan. Tiap evaluasi menghasilkan run baru di
`paths.cache_dir/answer-quality/`, tanpa mengubah SQL/ID/sitasi/label/sumber.

Worker RAGAS isolated S5 memakai CachedLLM/Judge: cache-first, izin API terpisah,
maksimal lima request/1.024 output token per request, tanpa retry jaringan.
Relevancy memakai embedding lokal pinned/offline melalui subprocess environment
utama. Strictness tiga memakai cache prompt sama, bukan tiga sampel independen.
Laporan mencatat config/model/backend/revision/library/kode/seed/traces/usage/hash
dan status evaluated/partial/failed; kegagalan null, bukan nol.

Faithfulness menilai dukungan seluruh konteks, bukan per sitasi. Response Relevancy
adalah cosine (-1 sampai 1) pertanyaan asli vs pertanyaan hasil judge, bukan
kebenaran fakta. Context Recall tetap batch beracuan. MiniCheck opsional pada
snapshot DB baru dan tidak menahan jawaban. Skor AI bukan akurasi manusia.

## 9. Protokol evaluasi

Dataset JSONL: `qid`, `question`, `qtype`, `gold_paper_ids`, `gold_chunk_ids`, `reference_answer` opsional.
Tipe: lookup, comparison, synthesis, unanswerable. Loader memeriksa ID/keanggotaan snapshot dan tidak memperbaiki gold otomatis.
M6: 30 pertanyaan empat paper yang disetujui pengguna, manifest `eval/questions.reviewed-v1.manifest.json`.
Label manusia satu paper dilaporkan terpisah; jangan pindahkan ke klaim generation atau chunk baru.

| Metrik | Kontrak implementasi |
|---|---|
| Recall@k / MRR | Gold chunk dalam ranking, depth `max(evaluation.ks)`; unanswerable tidak masuk rerata retrieval |
| Citation precision | Pasangan supported MiniCheck pada answerable / seluruh pasangan dinilai; partial bukan supported |
| Citation recall / faithfulness | Klaim non-unsupported dengan setidaknya satu sitasi supported / seluruh klaim |
| Hallucinated citation rate | ID ditolak / (ID valid + ditolak), unik per klaim setelah deduplikasi |
| Abstention | Proporsi unanswerable dengan generation berhasil dan nol klaim |
| Agreement/kappa | Label berpasangan pada sampel berhasil; coverage/distribusi terpisah |

Generation gagal/pasangan unverified membuat agregat dukungan utama null; denominator nol tetap null.
Semua klaim pada unanswerable gagal dukungan. Kappa dapat null bila tidak terdefinisi; agreement bukan accuracy manusia.
Definisi executable: `evaluation/metrics.py`; provenance/hash/config/model/seed/backend dan failure dicatat per run baru.

RAGAS 0.4.4 terisolasi menilai faithfulness terhadap konteks dan context recall terhadap acuan AI, bukan mengganti verifier sitasi.
20 draf skripsi tetap `ai_draft_unreviewed` walau field `gold_*`. Audit acuan bukan label klaim generation.
Revisi acuan 018 diterima terpisah dari versi lama/dataset/skor. Format/verdict/statements/usage invalid ditolak;
skor subset dan coverage dipisahkan. Batas byte/token/panggilan keras, tanpa retry judge/jaringan; telemetri mati.

## 10. Reproducibility dan biaya

Simpan hash byte dataset/PDF/chunk, snapshot/config, model/revision/library, seed,
code version, waktu/backend/cache hit/token. Laporan selalu run baru; jangan
mengekspor full text korpus ke laporan publik `eval/`. Budget request/token keras;
gagal/retry ikut jatah, SDK tanpa retry transport. Ledger/marker/receipt bertahan
lintas crash; replay cache bukan izin batch baru. Biaya unknown bukan gratis.

## 11. Konfigurasi

`config.py` memvalidasi seluruh tahap dan paths; field unknown/null/invalid ditolak,
default kompatibilitas masuk config efektif. Config UI: `configs/skripsi-local.yaml`,
pilot: `configs/skripsi-pilot.yaml`, backend Docling terpisah. Model baru tidak
memakai ruang vektor lama. Device CPU/CUDA eksplisit tanpa fallback diam-diam.
Torch CUDA manual belum selaras lock; jangan sync environment utama. Docling/RAGAS isolated.

## 12. Keputusan aktif dan batas

KB penuh Docling/Streamlit, DeepSeek Flash, RAGAS dan MiniCheck opsional tersedia.
PyMuPDF baseline tetap. JEV belum dipromosikan. Korpus pengguna bukan seluruhnya OA;
status lisensi adalah label pada jalur lokal berpolicy eksplisit.
Parasuraman OCR belum searchable, tiga TXT belum berpeta halaman; gate/akurasi manusia
belum dikalibrasi, bahasa Indonesia baru diuji terbatas. Tabel held bukan bukti,
narasi valid tetap boleh dipakai. Riwayat dan hasil rinci ada di kedua TASKS.
