# ARCHITECTURE.md

Kontrak teknis aktif. Skema SQL (bagian 4), ID (5), dan sitasi (6) tetap; perubahan memerlukan persetujuan eksplisit.
Tujuan: [OVERVIEW.md](OVERVIEW.md). Operasi: [USAGE.md](USAGE.md). Aturan agent: [AGENTS.md](AGENTS.md).
Riwayat keputusan/hasil: [TASKS-SKRIPSI.md](TASKS-SKRIPSI.md) dan [TASKS.md](TASKS.md).

## 1. Prinsip

- Jawaban hanya dari chunk hasil retrieval; setiap klaim ditautkan ke bukti kanonis.
- Persiapan korpus terpisah dari query. Hash/versi/lisensi/halaman PDF asli dapat ditelusuri.
- Logika terpisah dari I/O. Parameter dari config; model/revision dan seed dicatat.
- Snapshot/laporan baru tidak menimpa hasil lama. Label tidak berpindah hanya karena string ID sama.
- Penahanan blok terjadi sebelum chunk searchable ditulis; peringatan UI saja tidak cukup.

## 2. Peta modul

| Modul | Tanggung jawab |
|---|---|
| `config.py`, `ids.py`, `files.py` | Config bertipe, kontrak ID, penulisan atomik |
| `ingestion/` | Bibliografi, metadata/lisensi, unduhan berbudget, admission snapshot |
| `parsing/`, `chunking/` | PyMuPDF aktif; adapter Docling opt-in, gate, dan chunk tabel |
| `indexing/` | Embedding/cache, LanceDB, SQLite FTS5 |
| `retrieval/` | Dense/BM25, RRF, reranker |
| `generation/`, `verification/` | JSON klaim/sitasi, cache provider, MiniCheck/judge |
| `evaluation/`, `ui/` | Evaluasi/reproduksi dan Streamlit |

Alur sumber: ingestion, parsing, chunking, indexing. Alur query: retrieval, generation, verification.
Evaluation boleh mengorkestrasi modul-modul tersebut. Storage korpus/cache di `data/`, tidak di-commit.

## 3. Data flow

Korpus referensi skripsi terpisah dari benchmark M6; koleksi lokal dapat memakai
status lisensi belum terverifikasi sesuai policy eksplisit pengguna.
Parser/UI aktif tetap PyMuPDF; generator/verifier DeepSeek Flash non-thinking + MiniCheck.
Docling adalah kandidat opt-in, JEV `jev-1.14` masih eksperimen. Status/cakupan terbaru ada di TASKS-SKRIPSI.md.

### Persiapan korpus

1. `import-bib` menyimpan entries/references/audit tanpa menulis paper/chunk. DOI identik dapat dikelompokkan;
   konflik tetap tercatat. Bibliografi bukan bukti full text.
2. Downloader memeriksa metadata Crossref, identitas PDF, dan lisensi pada sumber yang disetujui.
   HTTPS/host/redirect/ukuran/cache diverifikasi; ledger persisten menghitung request gagal/redirect sebelum transfer.
   Default tanpa jaringan, lock mencegah pemakaian budget paralel; ledger tidak direset otomatis.
3. `prepare-bib` memeriksa provenance/hash/halaman/lisensi PDF siap lalu mendaftarkan snapshot.
   DOI lowercase memakai source ID `<DOI>_sha256_<SHA-256 PDF>` dalam namespace `crossref`.
   DOI di luar alfabet ID ditolak. Alias citation key/reference ID disimpan pada laporan prepare.
4. Parsing/chunking menyimpan artefak berhash dan memperbarui `parse_status`; input/config berbeda ditolak.
5. Indexing serial memeriksa seluruh chunk, batas tokenizer nyata, metadata/vector/FTS dan jumlah yang sama.
   Tidak ada transaksi lintas LanceDB/SQLite; run parsial belum sukses sampai konsistensi lengkap.

Sitasi selalu halaman PDF 1-indexed. PDF asli tidak diubah. Folder pengguna harus diinventaris sebelum admission;
Admission opt-in `prepare-local` default maksimal tiga PDF, atau batch dengan
`--max-documents` eksplisit di bawah batas config, selalu ke database baru.
Identitas mengikat metadata bibliografi ke HTML artikel, DOI tercetak di PDF,
atau receipt snapshot terdahulu dengan hash PDF/reference ID sama. Bukti lisensi
berasal dari artikel penerbit/PDF (satu/dua halaman berurutan) atau receipt tersebut;
pernyataan lisensi dataset tidak membuktikan lisensi artikel.
DOI bibliografi yang kosong dapat dilengkapi dari artikel penerbit tanpa mengubah
bibliografi asal; DOI yang sudah ada wajib cocok. `fetched_at` merekam observasi lokal,
dibedakan eksplisit dari receipt unduhan pada laporan. Parsing/indexing tidak berjalan saat query.
Konversi dipisah menjadi batch serial maksimal tiga PDF; raw cache hanya digunakan
jika hash PDF/model/backend cocok. Build KB gabungan menyimpan origin/hash tiap
run, menghitung ulang gate/chunk, serta memeriksa indeks pada database baru.

### Koleksi lokal pengguna

Instruksi pengguna 2026-11-20 mengizinkan seluruh PDF yang disediakan diproses lokal
meski DOI/lisensi belum terverifikasi. `prepare-local --local-collection` memerlukan
`admission_policy: user_local_collection` dalam manifest; mode default tetap ketat.
Hash PDF, halaman, batas ukuran/path, bibliografi dan database baru tetap diperiksa.
Rekaman yang sudah terverifikasi memakai identitas lama. Rekaman belum terverifikasi
memakai namespace `local` dengan source ID `sha256_<hash-PDF>`, mengikuti format
`<source>:<source_id>` yang sama; DOI opsional, tidak dibuat-buat. Skema SQL/sitasi tetap.
Lisensi disimpan sebagai `LicenseRef-UserProvided-Unverified`, landing URL menunjuk
file asli lokal; ini bukan lisensi publik atau izin redistribusi. Pernyataan lisensi
yang baru diduga tetap di manifest, tidak dipromosikan sebagai verifikasi.
Config snapshot lokal secara eksplisit menerima penanda tersebut; downloader/default
tidak berubah. Receipt admission mengikat citation key/reference ID/hash untuk UI.
Kualitas parsing tetap diperiksa sebelum indexing. Pada build koleksi lokal saja,
PDF tanpa chunk lolos tetap terdaftar dengan `parse_status=held`; bukan bukti searchable.
UI menampilkan lisensi belum diverifikasi, sumber lokal tanpa tautan daring, dan
paper yang belum memiliki chunk. Ketiadaan tautan bukan pengujian paywall/HTTP.

### Parser dan chunker

PyMuPDF mengurutkan baris/dua kolom, menormalkan Unicode, membuang margin berulang, dan mendeteksi section secara heuristik.
Artefak `ParsedPaper`/`TextBlock` mencatat halaman/section dan manifest PDF/parser/config/hash dokumen.
Chunker narasi menjaga section/ordinal global; `lexical-v1` bukan tokenizer embedding.
Ekor pendek mengikuti `merge`/`drop`, jumlah yang dibuang dilaporkan. Flag baseline `low_quality` menandai karakter rusak.

Docling memasok callback batas tokenizer pada jendela narasi: ujung jendela dipendekkan
di batas token leksikal sampai muat; overlap dibatasi agar selalu maju. Merge ekor
tidak boleh melampaui batas model. Unit tunggal yang tidak muat tetap dilaporkan held.
Tanpa callback, perilaku chunker PyMuPDF lama tetap. Anggaran baris/header tabel tidak berubah.

Docling terisolasi memakai Heron/TableFormer accurate/EasyOCR id/en CUDA, batch satu, model lokal pinned,
OCR selektif, tanpa remote services. `parsing.docling_pipeline extract/build` dibatasi tiga PDF lengkap terdaftar.
JSON/Markdown/HTML/native comparison dan keputusan blok disimpan dalam run baru; build memakai Python utama dan menghitung ulang gate.

- Blok membutuhkan halaman PDF asli eksplisit. Rumus/gambar/kode dan tipe yang belum didukung tidak menjadi bukti.
- Narasi diperiksa terhadap region native; teks overlap tabel tidak boleh melewati gate sebagai tabel rata.
- Tabel membutuhkan caption, header tiap kolom, label baris, grid body lengkap, serta token native cocok berurutan.
  Minus/desimal/tanda baca dipertahankan; `-` identik bukan mismatch.
- Header bertingkat menjadi `parent / child`; rowspan label hanya kolom pertama dengan flag eksplisit.
  Row-section harus satu baris penuh. Span tumpang tindih, body berlubang, header ambigu, dan sel melintasi baris tak dideklarasikan ditahan.
- Caption/header/catatan/halaman diulang per chunk; konteks kelompok diulang per baris.
  Pipe/newline/quote di-escape sebagai string JSON dalam sel. Baris utuh beserta konteks yang tidak muat menahan seluruh tabel.
- `QualityPolicy`: `native_word_coverage=0.8`, `header_center_tolerance=0.25` (proporsi pitch subheader terkecil).
  Keduanya heuristik awal, bukan kalibrasi manusia; header tak terpusat bisa ikut ditahan.
  OCR tanpa pembanding native dan native rusak belum dibuka otomatis. Tidak wajib mengoreksi seluruh paper manual.

Band vertikal sel satu baris tidak boleh bertumpang tindih dengan band baris berikutnya,
termasuk antar kolom. Kecocokan teks native saja dapat meloloskan crop yang sudah salah
gabung baris; tabel demikian ditahan. Pemeriksaan ini konservatif, termasuk untuk panel sejajar.

`do_cell_matching` boolean dari config backend, default true; tidak ada voting/per-table switching otomatis.
Opsi efektif menyertakan subclass Pydantic lengkap. Eksperimen halaman lama `evaluation.docling` terpisah dari build penuh.

### Indexing dan query

Embedding dokumen BGE float32 ternormalisasi, revision pinned, tanpa prefix. Tokenizer termasuk special tokens diperiksa tanpa truncation.
Cache teks membedakan model/revision/dimensi/batas/normalisasi/prefix; file rusak ditolak. LanceDB menyimpan hash/metadata chunk.
FTS5 memakai `chunk_fts(chunk_id UNINDEXED, text)`, tokenizer `unicode61 remove_diacritics 2`.
Retrieval membaca SQLite/index tanpa menulis sumber. Generation hanya menulis run/answer/claim; verification menyimpan dukungan.
Model tidak dimuat bila retrieval kosong/semua low-quality. UI query memakai backup SQLite baru; demo baca-saja.
Alias bibliografi wajib cocok dengan hash sumber/seluruh korpus. Perubahan identitas/config mereset jawaban/izin; judge tidak dipanggil UI.

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

Prompt berisi grounding, pertanyaan, serta chunk yang cocok dengan SQL; isi pengguna/chunk adalah data tak tepercaya.
Provider generator `deepseek`/`openai`; DeepSeek Flash non-thinking dipilih untuk runtime. Cache membedakan thinking/backend/provider,
endpoint/model/parameter/prompt/checksum. Mock memakai identitas lain. Respons/model/finish reason/usage dicatat; unknown bukan nol.
Default cache-only; `--allow-api` dan batas batch diperlukan untuk request baru. Retry transport nol; satu retry format generation
memakai konteks sama dan ikut jatah. Respons salah setelah itu gagal tanpa klaim parsial; kegagalan/cache miss bukan abstention.
Endpoint generation kustom wajib HTTPS tanpa credential/query/fragment. Key dari environment/`.env` provider terpilih, tidak dimutasi/log.

MiniCheck `lytang/MiniCheck-Flan-T5-Large` menilai pasangan utuh dan probabilitas supported dengan threshold config.
Input overlength tetap unverified tanpa truncation. Error/unknown tidak menjadi supported; klaim tetap disimpan.
Cache verifier mengikat klaim/evidence, model/revision/adapter/device/batas/threshold/backend; baris hasil append-only.

Judge generatif memakai keluarga berbeda dari generator dan seed untuk sampel klaim bersitasi. Label/alasan divalidasi.
`surplus-chat`: `SURPLUS_API_KEY`, `SURPLUS_API_URL`, `GPT_MODEL_ID`, endpoint HTTPS Surplus `/v1` dengan host/model tervalidasi.
`surplus`: JEV native `/v1/decisions`, model eksplisit `jev-1.14`, tanpa retry/redirect otomatis atau alias rolling.
JEV menyimpan probabilitas, model aktual, confidence/usage/latensi; rationale null. Confidence bukan ambang terkalibrasi.
Pasangan pembandingan memakai teks/hash sama. Judge/agreement terpisah dari metrik utama MiniCheck.

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

Simpan snapshot/config/hash byte dataset/PDF/chunk, model/revision/library, seed, code version, waktu, backend, cache hit, dan token.
Laporan selalu run baru; jangan menimpa hasil atau mengekspor full text korpus ke laporan publik `eval/`.
Budget request/token keras, kegagalan dihitung, SDK tanpa retry transport. Ledger downloader dan marker/receipt berbayar
bertahan lintas crash; replay cache tidak mengizinkan batch baru. Biaya mata uang unknown tidak dianggap gratis.

## 11. Konfigurasi

`config.py` memvalidasi ingestion, parsing, chunking, embedding, retrieval, generation, verification, evaluation, dan paths.
Field tidak dikenal/null/nilai tidak valid ditolak; default kompatibilitas masuk config efektif.
Contoh lengkap: [configs/skripsi-pilot.yaml](configs/skripsi-pilot.yaml). CLI Docling memakai config backend terpisah.
Model embedding/reranker/MiniCheck memakai revision commit pinned; model baru tidak boleh memakai ruang vektor lama.
Device CPU/CUDA eksplisit, tanpa fallback diam-diam. Torch CUDA manual belum selaras dengan lock utama; jangan sync environment ini.

## 12. Keputusan aktif dan batas

Storage SQLite + LanceDB/FTS5; UI Streamlit. Parser aktif PyMuPDF, kandidat Docling opt-in; runtime DeepSeek/MiniCheck.
Arah korpus referensi skripsi open access; target lama arXiv saja/100-500 paper sudah digantikan. Agreement saja tidak mempromosikan JEV.
Input lokal `data/reference-skripsi/` berisi 41 PDF + 3 TXT; audit awal 746 halaman tersedia.
Admission/lisensi batch, uji scan asli, kalibrasi gate, dan validasi manusia masih terbuka.
Native Indonesia sudah diuji pada pilot lokal terbatas; enam smoke query bukan evaluasi bahasa yang disetujui.
Tidak wajib koreksi manual seluruh paper. Tabel tertahan tidak menjadi bukti searchable; narasi valid tetap boleh dipakai.
Riwayat/keputusan yang sudah digantikan ada pada kedua file TASKS, bukan instruksi aktif di sini.
