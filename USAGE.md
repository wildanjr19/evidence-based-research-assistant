# Panduan penggunaan

Perintah berlaku dari root repo. `<...>` adalah placeholder untuk berkas dari snapshot yang sesuai.
Hasil, persetujuan, biaya, dan riwayat: [TASKS-SKRIPSI.md](TASKS-SKRIPSI.md) dan [TASKS.md](TASKS.md).

## Setup

Gunakan Python `.venv` langsung agar Torch CUDA manual tetap terjaga; **jangan `uv sync`/`uv run` pada environment ini**.
Config default embedding masih CPU. Pada Linux gunakan `.venv/bin/python`; Windows memerlukan bentuk module karena launcher pytest diblokir.

```powershell
.venv/Scripts/python.exe -m pytest -q
.venv/Scripts/python.exe -m ruff check .
.venv/Scripts/python.exe -m ruff format --check .
```

Untuk melewati test GPU, tambahkan `-m "not gpu"` pada pytest. Instalasi environment **baru saja**:
`python -m pip install --user uv`, lalu `python -m uv sync --locked`; ini bukan prosedur untuk memperbaiki `.venv` CUDA saat ini.

Config YAML bertipe/tervalidasi; path relatif terhadap direktori kerja.
UI utama memakai `configs/skripsi-local.yaml`; `configs/skripsi-pilot.yaml` mempertahankan pilot lima PDF.
Model/revision, ukuran chunk, device, top-k, dan batas panggilan berasal dari config; jangan mencampur snapshot/ruang embedding.
Jika model sudah tersedia dan seluruh proses harus offline:

```powershell
$env:HF_HUB_OFFLINE = '1'
$env:TRANSFORMERS_OFFLINE = '1'
$env:TOKENIZERS_PARALLELISM = 'false'
```

### Key dan izin API

Salin `.env.example` ke `.env` jika belum ada; isi hanya provider yang digunakan. Jangan menimpa `.env` yang sudah terisi.
Environment diprioritaskan. Loader menerima assignment satu baris UTF-8, kutip, komentar `#`, dan prefix `export` opsional;
multiline, escape, dan interpolasi tidak didukung. Key tidak boleh masuk YAML, command, log, atau Git.

| Kebutuhan | Variabel |
|---|---|
| DeepSeek / OpenAI generator | `DEEPSEEK_API_KEY` / `OPENAI_API_KEY` |
| GPT judge Surplus | `SURPLUS_API_KEY`, `SURPLUS_API_URL`, `GPT_MODEL_ID` |
| JEV Surplus | `SURPLUS_API_KEY`, `SURPLUS_API_URL`, `JEV_MODEL_ID=jev-1.14` |

Endpoint Surplus dibatasi HTTPS `https://api.surplusintelligence.ai/v1`; JEV juga menerima `/v1/decisions`.
Membuat `.env` tidak mengaktifkan API. CLI generation/judge default cache-only; `--allow-api` memerlukan izin dengan batas konkret.
Batch M6/S5 sudah selesai dan bukan izin baru. Setelah crash, periksa receipt/marker/cache lalu replay tanpa API.

## Impor referensi skripsi (S1)

```powershell
.venv/Scripts/python.exe -m rag.ingestion import-bib --bib reference-skripsi.bib --output-dir data/skripsi/references
```

Impor offline membuat run baru: `entries.jsonl`, `references.jsonl`, `report.json`. Duplikat/konflik tetap tercatat;
metadata BibTeX belum merupakan bukti full text. Impor tidak menulis paper/chunk. `bibtexparser==2.1.0` sudah disetujui/dikunci.

## PDF dan penyiapan korpus (S2-S3)

Input pengguna di `data/reference-skripsi/`: 41 PDF + 3 TXT, bukan 44 PDF; 746 halaman PDF pada audit awal.
Manifest/hash sudah dicocokkan. Jalur default memverifikasi identitas/lisensi sebelum admission;
koleksi lokal penuh memakai opt-in dan label sebagaimana dijelaskan di bawah.
TXT belum memiliki pemetaan halaman PDF yang sah, sehingga belum menjadi bukti searchable.
Admission lokal default maksimal tiga PDF dengan manifest yang sudah diperiksa:

```powershell
.venv/Scripts/python.exe -m rag.ingestion prepare-local --config <config-baru.yaml> --manifest <manifest-tertinjau.json>
```

Batch lokal yang disetujui memakai `--max-documents <batas>` eksplisit, tidak boleh
melebihi `ingestion.max_papers`. Manifest memuat hanya dokumen yang lolos; kandidat
tertahan tetap tercatat di laporan kesiapan. Snapshot verifikasi lisensi tahap 2 berisi 18 PDF/974 chunk;
config baca KB ada di `data/skripsi/kb-expansion/2026-11-20T01-33-36Z_3f61ac/kb/pipeline-config.yaml`.
Ini korpus kandidat terpisah, belum mengganti config/UI aktif.

Manifest mengikat hash bibliografi/PDF/HTML artikel penerbit, citation key, DOI, halaman,
lisensi/URL, dan waktu observasi lokal. Identitas dapat berasal dari HTML artikel,
DOI tercetak pada halaman identitas PDF, atau laporan snapshot lama dengan hash/ref sama.
Bukti lisensi harus mengikat artikel: `rel=license`, halaman copyright, pernyataan
lisensi artikel pada satu/dua halaman PDF berurutan, atau receipt snapshot yang sama.
Lisensi dataset tidak diterima sebagai lisensi artikel. DOI baru dari artikel
penerbit boleh melengkapi DOI bibliografi yang kosong; DOI lama tidak ditimpa.
Database harus baru; sumber lokal tidak diubah. `fetched_at` pada jalur ini berarti
waktu observasi lokal, bukan receipt unduhan. Contoh manifest dan bukti pilot:
`data/skripsi/local-pilot/2026-11-20T00-35-31Z_6fb4ad/admission-manifest.json`.
Jangan mengunduh PDF tambahan atau menganggap semua file layak diindeks. Contoh
manifest KB/status seluruh input ada di `data/skripsi/kb-build/2026-11-20T01-06-05Z_f81029/`.
Konversi tetap serial, maksimal tiga PDF per pemanggilan; raw terverifikasi dapat
dirangkai ke satu build KB dengan provenance tiap run. Bukan tuning retrieval/generation.

### Seluruh koleksi PDF lokal

Snapshot terbaru: **41 PDF/746 halaman terdaftar, 40 searchable, 2.514 chunk**.
Config: `data/skripsi/kb-local-all/2026-11-20T01-59-17Z_c95c3b/kb/pipeline-config.yaml`.
Receipt citation key untuk UI: `data/skripsi/kb-local-all/2026-11-20T01-59-17Z_c95c3b/admission-receipt.json`.

```powershell
.venv/Scripts/python.exe -m streamlit run src/rag/ui/app.py --server.address 127.0.0.1 -- --config data/skripsi/kb-local-all/2026-11-20T01-59-17Z_c95c3b/kb/pipeline-config.yaml --bibliography-report data/skripsi/kb-local-all/2026-11-20T01-59-17Z_c95c3b/admission-receipt.json
```

Parasuraman sudah diekstrak OCR tetapi belum memiliki chunk yang lolos kualitas;
UI menampilkan status ini. Katalog/label telah diuji AppTest tanpa generation.
Config/UI default lama tidak ditimpa. Laporan rinci pada `summary.md` snapshot.

Pengguna menyetujui pemrosesan seluruh 41 PDF lokal, tanpa menunggu DOI/lisensi.
Gunakan database/config baru serta manifest berpolicy `user_local_collection`:

```powershell
.venv/Scripts/python.exe -m rag.ingestion prepare-local --config <config-baru.yaml> --manifest <manifest-lokal.json> --max-documents 41 --local-collection
```

Flag ini tidak menonaktifkan hash/path/page/encryption checks. Dokumen tanpa bukti
penerbit diberi status `LicenseRef-UserProvided-Unverified` dan ID lokal berhash;
18 identitas terverifikasi lama dipertahankan. Tidak ada klaim bahwa seluruh PDF OA.
Mode default tanpa flag tetap memerlukan bukti penerbit/lisensi. Tiga TXT belum
memiliki halaman PDF dan tidak diperlakukan sebagai PDF.
Build tetap memakai gate kualitas; PDF tanpa chunk lolos tampil dalam katalog
sebagai belum searchable. UI menerima receipt `prepare-local` pada
`--bibliography-report`, menampilkan citation key dan label sumber/lisensi.

Downloader lama dapat direplay tanpa jaringan:

```powershell
.venv/Scripts/python.exe -m rag.ingestion download-bib --download-config configs/skripsi-download.yaml
```

Ledger lama memakai 26/30 request dan lima slot PDF. Jangan mereset ledger atau memakai `--allow-network` tanpa izin baru.
Jalur arXiv lama `rag.ingestion discover` lalu `fetch --config <config>` melakukan request jaringan; tidak diperlukan untuk folder pengguna.

Daftarkan **laporan unduhan siap** ke korpus terpisah:

```powershell
.venv/Scripts/python.exe -m rag.ingestion prepare-bib --config configs/skripsi-pilot.yaml --download-report data/skripsi/downloads/2026-11-19T06-53-52Z_57a5ae/report.json
```

Hash/identitas/lisensi diperiksa. `crossref:<DOI>_sha256_<hash-PDF>` mengikat snapshot;
lookup citation key ada pada laporan prepare di `index/reports/`. Label lama tidak disalin.

### Parsing PyMuPDF dan indexing

Pada korpus terdaftar, jalankan serial dengan config yang sama:

```powershell
.venv/Scripts/python.exe -m rag.parsing --config configs/skripsi-pilot.yaml
.venv/Scripts/python.exe -m rag.chunking --config configs/skripsi-pilot.yaml
.venv/Scripts/python.exe -m rag.indexing --config configs/skripsi-pilot.yaml
```

Parse/chunk mendukung `--paper-id`. Parser aktif memakai PyMuPDF tanpa OCR; section/urutan baca heuristik dan tabel dapat rata.
`n_tokens` chunk adalah token leksikal. Embedding memeriksa tokenizer model termasuk special tokens tanpa truncation.
`short_chunk_policy=drop` membuang ekor/section pendek dan melaporkannya; `merge` dapat melewati target leksikal.
Input/config/chunk berbeda ditolak tanpa penghapusan otomatis: gunakan raw/parsed/database/index baru untuk eksperimen.

Chunk narasi Docling kini memeriksa batas tokenizer saat memilih jendela leksikal;
halaman/teks asli tetap dijaga, tanpa truncation. Unit leksikal tunggal yang masih
terlalu panjang tetap ditahan. Anggaran tabel dan jalur PyMuPDF lama tetap.
Config pilot native tiga PDF dibekukan di
`data/skripsi/pilot-refinement/2026-11-20T00-54-04Z_721c6f/frozen-config.yaml`:
default hybrid tanpa reranker pada snapshot tersebut. Ini bukan config batch penuh
atau pergantian config/UI aktif. Perbandingan empat mode tetap dicatat di TASKS-SKRIPSI.md.

### Adapter Docling: snapshot terpisah

Docling 2.151.1 memakai environment/model lokal terkunci: Heron, TableFormer accurate, EasyOCR id/en, CUDA batch satu.
Parser/UI aktif belum diganti. Maksimal tiga PDF pilot terdaftar/berlisensi; seluruh halaman asli diproses, OCR selektif.

```powershell
data/skripsi/docling-pilot/.venv/Scripts/python.exe -m rag.parsing.docling_pipeline extract --source-config configs/skripsi-pilot.yaml --docling-config configs/docling-pilot.yaml --samples data/skripsi/docling-pilot/samples-v2.json
.venv/Scripts/python.exe -m rag.parsing.docling_pipeline build --run <run>
.venv/Scripts/python.exe -m rag.indexing --config <run>/pipeline-config.yaml
```

`extract` mencetak run baru di `data/skripsi/docling-full/`; `build` memakai Python utama. Keduanya memaksa offline.
Jangan memakai chunker PyMuPDF pada artefak Docling. Raw PDF/cache boleh dibaca bersama; SQL/index/label tetap terpisah.
JSON/Markdown/HTML/native comparison, gate blok, model/config/hash, dan laporan build menyimpan hasil yang ditahan.

Header bertingkat, rowspan label eksplisit, row-section penuh, dan pipe/multiline didukung bila teks/geometri cocok.
Caption/header/catatan/halaman serta konteks kelompok dipertahankan. Span ambigu, body berlubang, mismatch native,
OCR tanpa pembanding, atau satu baris beserta konteks terlalu panjang ditahan sebelum SQL/index; tidak ada truncation.
Policy `native_word_coverage=0.8` dan `header_center_tolerance=0.25` masih heuristik, bukan akurasi manusia.
`do_cell_matching` pada config backend adalah boolean, default true; uji false belum mendukung penggantian.

Eksperimen halaman lama: `rag.evaluation.docling --config configs/docling-pilot.yaml --offline` pada environment Docling.
Ia tidak membangun korpus. Sampel scan buatan bukan scan asli atau bukti dukungan penuh bahasa Indonesia.

### Environment khusus: hanya untuk instalasi baru

Jangan membuat ulang environment yang sudah tersedia. Lock berikut tidak dipasang ke `.venv` utama:

```powershell
py -3.11 -m uv venv --python 3.11 data/skripsi/docling-pilot/.venv
py -3.11 -m uv pip install --python data/skripsi/docling-pilot/.venv/Scripts/python.exe --require-hashes --index-strategy unsafe-best-match -r eval/docling-requirements.lock
py -3.11 -m uv pip install --python data/skripsi/docling-pilot/.venv/Scripts/python.exe --no-deps --editable .
py -3.11 -m uv venv --python 3.11 data/skripsi/s5-ragas/.venv
py -3.11 -m uv pip install --python data/skripsi/s5-ragas/.venv/Scripts/python.exe --require-hashes -r eval/ragas-requirements.lock
py -3.11 -m uv pip install --python data/skripsi/s5-ragas/.venv/Scripts/python.exe --no-deps --editable .
```

Test isolated:

```powershell
data/skripsi/docling-pilot/.venv/Scripts/python.exe -m pytest -q tests/test_docling.py tests/test_docling_adapter.py
data/skripsi/s5-ragas/.venv/Scripts/python.exe -m pytest -q tests/test_ragas.py tests/test_ragas_adapter.py
```

## Retrieval dan generation

```powershell
.venv/Scripts/python.exe -m rag.retrieval --config configs/skripsi-pilot.yaml --question "Apa tugas dalam IndoNLU?" --mode hybrid
.venv/Scripts/python.exe -m rag.generation --config configs/skripsi-pilot.yaml --question "Apa tugas dalam IndoNLU?" --mode hybrid
```

Mode: `bm25`, `dense`, `hybrid`, `hybrid+rerank`. Retrieval hanya membaca sumber/index; generation menyimpan run/answer/claim.
Default generator `deepseek-flash`, `thinking: false`; cache miss tanpa izin API adalah kegagalan, bukan abstention.
`generation.max_calls_per_run` mencakup retry format; retry transport SDK nol. Batas output/timeout mengikuti config.
MiniCheck adalah verifier lokal; validitas ID tidak membuktikan dukungan makna. Jev belum menjadi verifier utama.

## Tanya korpus skripsi di Streamlit (S4)

Jalankan UI utama dari root repo:

```powershell
.venv/Scripts/python.exe -m streamlit run src/rag/ui/app.py --server.address 127.0.0.1
```

Buka `http://127.0.0.1:8501`. Pilihan awal adalah **Referensi skripsi lengkap
(41 PDF)**, langsung pada **Tanya korpus**: 40 searchable/2.514 chunk; Parasuraman
tetap terdaftar tanpa chunk. Pemilih korpus juga menyediakan pilot lima PDF dan
benchmark historis dengan config/database/demo masing-masing. Izin API dan jawaban
direset ketika korpus berubah.

**Cari bukti** memakai hybrid sesuai config KB penuh; BM25/dense/rerank juga dapat
dipilih. Tanpa izin API, pertanyaan baru tetap menampilkan kutipan hasil retrieval
meski jawaban belum ada di cache. Untuk menyusun jawaban baru, centang izin API
berbayar sebelum submit (maksimal dua request, termasuk koreksi format). Pengujian
integrasi ini tidak membuat request berbayar baru.

Pilih **Demo tersimpan** untuk membuka delapan jawaban pilot KB penuh tanpa API
atau model inference. Jawaban itu menggunakan konteks refinement eksperimental
yang sudah dibekukan saat pilot; bukan hasil retrieval ulang dari form saat ini.
Sumber/halaman/kutipan tetap cocok dengan KB penuh, label mesin tetap apa adanya.
Buka sitasi lalu centang **Lihat halaman PDF asli** untuk membaca halaman asli
dan **Unduh PDF sumber**. Hash PDF diperiksa terhadap metadata korpus sebelum
halaman/byte file ditampilkan. PDF disajikan lokal; tidak mengunduh paper baru.

`configs/skripsi-local.yaml` mengikat database UI baru
`data/skripsi/ui-local/2026-11-21T08-16-45Z_07d296/corpus.db`, indeks KB penuh,
receipt admission lokal yang sama dan delapan jawaban pilot tersalin. Asal/hash
tercatat di manifest folder tersebut; query tetap menulis backup/run baru di cache.
Folder data bersifat lokal dan tidak di-commit. Kontrak SQL/ID/sitasi tetap.

Perintah eksplisit untuk pilot lima PDF (opsional):

```powershell
.venv/Scripts/python.exe -m streamlit run src/rag/ui/app.py --server.address 127.0.0.1 -- --config configs/skripsi-pilot.yaml --bibliography-report data/skripsi/pilot-v1/index/reports/prepare-2026-11-19T07-11-50Z_3aa5f1.json
```

Laporan bibliografi harus cocok dengan seluruh snapshot: UI memeriksa hash/provenance/alias.
Jangan memasangkan laporan S3 dengan subset Docling atau demo M6 dengan korpus skripsi.
UI membedakan referensi terdaftar dari paper searchable; sitasi membuka judul, halaman PDF, kutipan, dan lisensi asli.
Setiap submit memakai backup SQLite baru di cache; jawaban dan izin API direset bila identitas korpus berubah.
Checkbox API hanya berlaku pada submit tersebut, maksimal dua percobaan termasuk koreksi format atau batas config yang lebih kecil.
Jawaban tampil sebelum evaluasi. MiniCheck tidak berjalan otomatis; buka
**Diagnostik MiniCheck (opsional)** lalu **Jalankan MiniCheck lokal** bila diperlukan.
Hasil lama tetap dapat dibaca. Diagnostik baru memakai salinan database tersendiri.

Klik **Evaluasi kualitas** untuk menghitung **Faithfulness** dan **Response Relevancy**
pada jawaban yang sedang dibaca. Izin API evaluasi terpisah dari izin generator dan
default mati. Cache diperiksa dahulu; aktifkan checkbox evaluasi bila mengizinkan
pengiriman pertanyaan/jawaban/konteks ke provider judge. Batas per klik: lima request,
1.024 token output/request, tanpa retry jaringan. Kegagalan dan cache miss menjadi
**Belum tersedia**, bukan skor nol; jawaban tetap dapat dibaca.

Evaluator memakai RAGAS di `data/skripsi/s5-ragas/.venv`; embedding pertanyaan memakai
model lokal pinned dari environment utama, hanya cache model offline. Tidak perlu
memasang RAGAS ke environment CUDA. Laporan baru di `paths.cache_dir/answer-quality/`
menyimpan jawaban, seluruh konteks asli termasuk yang tidak disitasi, hash, config,
model, seed, traces, dan usage. Jangan membagikan folder ini karena berisi teks korpus.
Faithfulness memakai seluruh konteks terambil; Response Relevancy memakai cosine
pertanyaan asli dan pertanyaan hasil judge (rentang -1 sampai 1). Keduanya estimasi AI,
bukan jaminan kebenaran atau akurasi setiap sitasi. Context Recall tetap evaluasi batch
yang memerlukan jawaban acuan. Pergantian jawaban/korpus mereset hasil dan izin evaluasi.

Arti label mengikuti [kebijakan pelaporan verifier](ARCHITECTURE.md#kebijakan-pelaporan-verifier):

- **Didukung MiniCheck:** model menerima semua sitasi klaim; tetap periksa kutipan dan PDF asli.
- **Perlu diperiksa:** sedikitnya satu sitasi ditolak/partial, termasuk bila hasil sitasi lain belum tersedia.
  Ini bukan keputusan bahwa klaim salah; diagnosis lokal menemukan sensitivitas bahasa, atribusi, dan tabel.
- **Belum diverifikasi:** hasil belum lengkap atau error, tanpa penolakan/partial yang tercatat.
- **Tidak ada bukti:** klaim ditandai unsupported atau tidak memiliki sitasi valid;
  ini tidak membuktikan seluruh korpus tidak memuat bukti.

Hasil judge dan audit sumber dibaca terpisah; keduanya tidak menimpa label MiniCheck.
Audit AI bukan verifikasi manusia. Jangan mengubah threshold atau memilih terjemahan/view
berdasarkan skor tertinggi. UI memerlukan semua sitasi supported; metrik citation
recall/faithfulness memakai sedikitnya satu sitasi supported per klaim.

## UI Streamlit dan demo lokal

Demo historis M6 memakai config/korpus yang sesuai:

```powershell
.venv/Scripts/python.exe -m streamlit run src/rag/ui/app.py --server.address 127.0.0.1 -- --config data/m6-multipaper/20261119T004114Z/config-citations-surplus-gpt-authorized-v1.yaml
```

`--demo-dir <laporan-M6>` dapat diberikan eksplisit; hash korpus wajib cocok. Demo membaca SQLite tanpa menulis sumber.
Tanpa laporan bibliografi, UI menyediakan demo M6; form query lokal tetap memakai cache/izin di atas.

## Evaluasi retrieval, sitasi, dan agreement

Dataset harus cocok dengan ID/hash snapshot. `eval/questions.jsonl` berisi 30 pertanyaan M6 yang ditinjau pengguna;
jangan menjalankannya pada korpus skripsi. Format dataset/metrik: [ARCHITECTURE.md](ARCHITECTURE.md#9-protokol-evaluasi).

```powershell
.venv/Scripts/python.exe -m rag.evaluation --config <config-benchmark.yaml> --dataset <questions.jsonl> --mode all
.venv/Scripts/python.exe -m rag.evaluation --stage citations --config <config-benchmark.yaml> --mode hybrid+rerank
.venv/Scripts/python.exe -m rag.evaluation --stage agreement --config <config-benchmark.yaml> --annotations <labels.jsonl>
```

`--with-judge` menilai sampel, tetapi tidak mengizinkan API tanpa `--allow-api`. Batas generation/judge berlaku untuk seluruh batch/mode.
Laporan baru ada di `evaluation.output_dir`. Unknown/gagal/overlength tidak dianggap nol atau sukses; cek coverage dan denominator.
Abstention yang benar memakai `{"claims": []}`. Klaim penolakan unsupported tetap gagal kontrak nol klaim.

### Retrieval offline KB lokal lengkap

Dataset khusus snapshot 41 PDF berada di
`data/skripsi/retrieval-local-all/2026-11-20T03-14-42Z_956cb9/questions.jsonl`.
Statusnya acuan AI sementara, bukan gold manusia: 32 pertanyaan berbukti dari
16 pasangan Indonesia/Inggris, ditambah empat kontrol tanpa bukti. Target chunk,
halaman PDF, dan probe sumber dibekukan dalam `dataset-freeze.json` sebelum ranking.
`source-audit.json` menyimpan kutipan dan teks halaman asli; jangan commit isinya.

Gunakan evaluator retrieval lama dengan config snapshot penuh dan output **baru**.
`experiment.py` pada direktori dataset memakai config tersebut tanpa mengubahnya,
mengalihkan output ke `baseline/` atau `replay/`, lalu memeriksa hash/replay.
Tahap `prepare`, `baseline`, `replay`, dan `analyze` menolak menimpa artefak yang ada.
Untuk percobaan lain, gunakan direktori run baru; jangan menjalankan `prepare` ulang
pada dataset beku atau memakai dataset M6/S5 sebagai penggantinya.

Retrieval top-8 sesuai batas konteks runtime dilaporkan terpisah dari Recall@5/10/20.
Kontrol tanpa bukti dapat tetap mendapat hit: retrieval ini tidak mempunyai ambang
abstention. Ketiadaan klaim/jawaban belum diuji sebelum tahap generation tersendiri.

Refinement eksperimental berada di
`data/skripsi/retrieval-refinement/2026-11-20T06-24-43Z_092865/summary.md`.
Helper `hinted.py` menambah kandidat dari token teknis, memakai alias receipt yang
divalidasi, dan mengutamakan nomor tabel pada paper eksplisit. Ini bukan mode CLI/UI
produksi; model/config/indeks lama tetap. `policy.json` dan `freeze.json` mengikat
aturan serta 20 pertanyaan validasi baru sebelum ranking. `run.py` menyimpan hasil
dan replay baru; marker menolak eksekusi ulang di direktori yang sama.
Dataset validasi, source audit, kutipan dan rencana generation tetap di `data/`.

`generation-plan/plan.json` berstatus `proposed_not_authorized`: 8 pertanyaan,
maksimum 14 request DeepSeek Flash non-thinking termasuk kegagalan/retry format,
2048 output token/request, total maksimum 28672 output token; pesan maksimum
65536 byte/request. MiniCheck lokal, tanpa JEV/judge. `review.md` dan `contexts.json`
memuat pertanyaan serta bukti yang dikirim pada pilot yang kini selesai.
Proposal `plan.json` tidak diubah; izin pengguna `boleh` terikat hash rencana pada
`authorization.json`. Fase berbayar sudah memakai 7/14 request dan marker
`paid-phase-started.json` tetap. **Jangan menjalankan fase paid lagi** atau memakai sisa
jatah untuk batch baru. Setelah crash, periksa receipt/request-journal/cache, lalu
replay tanpa API dahulu. `pilot.py replay` selalu cache-only dan memakai database baru.
Fase `verify --directory <run>` hanya MiniCheck lokal; pasangan utuh/overlength tetap
unverified. Run yang sudah mempunyai verification tidak ditimpa; gunakan replay baru.
Hasil dan batas: `generation-plan/summary.md`, `results.json`, dan `source-review.md`.
Generation/verification replay identik, nol API baru; UI/default produksi tetap.

Diagnosis verifier offline tersimpan terpisah pada
`data/skripsi/verifier-diagnosis/2026-11-20T12-46-00Z_5b9a21/summary.md`.
86 probe/replay lokal menunjukkan sensitivitas bahasa LoRA dan atribusi Transformer;
varian tabel tertentu menerima angka salah. Jangan mengganti label pilot atau memilih
skor tertinggi dari beberapa view. Script `diagnose.py replay` hanya cache verifier
lokal yang sudah lengkap; jangan mengulang `prepare`/`run` pada folder hasil ini.
Tidak ada transformasi atau model baru dipromosikan dari diagnosis AI tersebut.

GPT judge: `verification.judge_provider: surplus-chat`, keluarga model berbeda dari generator.
Jev: `judge_provider: surplus`, `JEV_MODEL_ID=jev-1.14`; keputusan/probabilitas tanpa rationale generatif.
Perbandingan pasangan cache-only tanpa generation:

```powershell
.venv/Scripts/python.exe -m rag.evaluation.decisions --config <config-pasangan.yaml> --pairs <pasangan.jsonl> --limit 12
```

Input pasangan memuat `claim`, `chunk_id`, `text_sha256`; evidence dibaca dari SQL. Partial tetap kelas tersendiri;
MiniCheck overlength tetap unverified, tidak dipotong. Agreement antarmodel bukan akurasi manusia.

## Evaluasi skripsi dengan RAGAS (S5)

RAGAS 0.4.4 hanya pada environment isolated. Dataset 20 acuan AI tetap `ai_draft_unreviewed` meski memakai field `gold_*`;
audit acuan bukan label klaim generation. Revisi acuan 018 yang diterima tidak mengganti acuan/skor lama secara retroaktif.
Batch pilot dan lanjutan sudah selesai; periksa receipt/marker di TASKS-SKRIPSI.md sebelum replay.

```powershell
.venv/Scripts/python.exe -m rag.evaluation.ragas prepare --config <config-skripsi.yaml> --dataset <questions.jsonl> --offset 0 --limit 4 --max-generation-calls 8
data/skripsi/s5-ragas/.venv/Scripts/python.exe -m rag.evaluation.ragas score --inputs <direktori-ragas-inputs> --max-judge-calls 12 --max-prompt-bytes 65536
```

Default cache-only. `--offset`/`--limit` memilih subset; manifest tetap mengikat dataset utuh.
Faithfulness terhadap konteks terambil dan context recall terhadap acuan AI bukan precision sitasi atau gold manusia.
Batas batch/token/prompt tetap keras, tanpa retry jaringan/judge. Telemetri RAGAS mati; laporan/replay selalu run baru.

## Anotasi verifier independen

Paket yang disetujui 2026-11-21 berada di
`data/skripsi/verifier-independent/2026-11-21T07-18-43Z_6b031a/`.
Baca `reviewer/README.txt`, lalu salin `reviewer/annotations.csv` menjadi
`reviewer/annotations-filled.csv`. Isi hanya `label`, `annotator`, dan `notes`.
Label: `supported`, `partially_supported`, atau `not_supported`; bila ambigu,
biarkan kosong dan catat alasan untuk ditinjau, jangan menebak. `evidence.md`
menyajikan seluruh chunk. Jangan membuka maintainer/specs atau prediksi model
sebelum penilaian selesai. File asli dibekukan dan tidak diedit.

Periksa paket atau import salinan CSV lengkap dari root repo:

```powershell
$annotationRun = 'data/skripsi/verifier-independent/2026-11-21T07-18-43Z_6b031a'
.venv/Scripts/python.exe "$annotationRun/prepare.py" check
.venv/Scripts/python.exe "$annotationRun/prepare.py" import --csv "$annotationRun/reviewer/annotations-filled.csv"
```

Import memerlukan 48 label manusia dan annotator terisi; konten sumber wajib
identik. Hasil menjadi folder `human-labels-<timestamp>` baru, bukan penimpaan
file beku. Notes disimpan pada receipt. Import tidak menjalankan scoring/model/API.
Scoring baseline lokal dilanjutkan setelah label selesai, pada run baru.
Sampel 48 pasangan berasal dari 12 unit berkorelasi; bukti semuanya Inggris.
Hasil belum mengukur retrieval/generation atau akurasi seluruh korpus.

### Alternatif seluruhnya AI, selesai 2026-11-21

Atas instruksi pengguna, paket yang sama telah dinilai otomatis pada
`data/skripsi/verifier-ai-evaluation/2026-11-21T07-34-32Z_0e9735/`.
Jalur ini tidak memerlukan label manusia, tetapi hanya melaporkan evaluasi AI.
48 penilaian gpt-4o-mini, 48 MiniCheck lokal dan 12 audit GPT selesai; seluruh
60 request yang diizinkan telah digunakan. Jangan mengulang fase paid, mereset
marker/journal atau menganggap replay memberi izin request baru.

Laporan: `summary.md`, `results.json`, `per-pair.json`, `source-review.md`.
Replay tanpa API/inference baru, ke folder hasil baru:

```powershell
.venv/Scripts/python.exe data/skripsi/verifier-ai-evaluation/2026-11-21T07-34-32Z_0e9735/run.py replay
```

Replay membutuhkan cache lengkap dan environment GPT_MODEL_ID yang sama dengan
rencana beku; cache miss tidak boleh diatasi dengan mengaktifkan API otomatis.
Agreement bukan akurasi manusia; audit model sama tidak menimpa label awal.
Paket anotasi manusia tetap tersedia terpisah, seluruh labelnya masih kosong.

## Troubleshooting

| Kondisi | Tindakan |
|---|---|
| `No module named uv` di `.venv` | Gunakan Python `.venv` langsung; jangan sinkronkan environment CUDA |
| Model/cache belum ada saat offline | Pastikan model/revision tersedia; jangan menganggap cache miss sebagai hasil model |
| Parsed/chunk/index/hash berbeda | Pakai direktori/database/run baru; jangan menghapus atau rebuild data lama otomatis |
| Input melewati batas embedding/verifier | Chunk lebih kecil pada snapshot baru atau tetap unverified/held; jangan truncation |
| LLM cache miss | Periksa model/config/backend; tanpa izin/budget baru jangan mengaktifkan API |
| CUDA/OOM/konversi parsial | Catat kegagalan, pertahankan artefak; jangan menganggap partial sebagai build sukses |
| UI bibliografi/demo tidak cocok | Pilih config dan laporan dari snapshot yang sama |
