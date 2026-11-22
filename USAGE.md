# Panduan penggunaan

Jalankan dari root repo. `<...>` adalah placeholder untuk snapshot yang sesuai.
Status/bukti eksperimen: [TASKS-SKRIPSI.md](TASKS-SKRIPSI.md) dan [TASKS.md](TASKS.md).
Kontrak data/metrik: [ARCHITECTURE.md](ARCHITECTURE.md).

## Menjalankan UI

Dengan environment dan data lokal yang sudah tersedia:

```powershell
.venv/Scripts/python.exe -m streamlit run src/rag/ui/app.py --server.address 127.0.0.1
```

Buka [localhost:8501](http://127.0.0.1:8501). Default **Referensi skripsi lengkap
(41 PDF)** dan **Tanya korpus**, memakai `configs/skripsi-local.yaml`:
40 searchable/2.514 chunk. Parasuraman terdaftar tanpa chunk lolos kualitas;
tiga TXT belum berpeta halaman. Pemilih korpus menyediakan pilot lima PDF dan
benchmark historis dengan config/receipt/demo yang cocok.

1. Tulis pertanyaan dan pilih BM25, dense, hybrid (default), atau hybrid+rerank.
2. Klik **Cari bukti**. API generator aktif otomatis saat cache kosong, maksimal
   dua request/submit termasuk koreksi format, atau batas config yang lebih kecil.
3. RAGAS otomatis mengevaluasi setiap card, tanpa tombol atau checkbox izin.
4. Buka sitasi, **Lihat halaman PDF asli**, lalu **Unduh PDF sumber** bila diperlukan.
   Path/hash PDF diperiksa terhadap sumber kanonis; tidak mengunduh paper dari internet.
5. Buka **Penggunaan token** untuk rincian input/output generator, evaluator dan
   total tercatat. **Diagnostik MiniCheck** tetap lokal dan opsional.

**Demo tersimpan** membuka delapan jawaban pilot tanpa generator baru; evaluasi
RAGAS tetap otomatis dan dapat memakai API jika cache skor kosong.
Konteks demo adalah refinement eksperimental yang dibekukan saat pilot, bukan
retrieval ulang form. Helper refinement belum menjadi mode produksi.

Query/diagnostik menulis salinan database tersendiri, bukan sumber. Perubahan
jawaban/korpus mereset hasil evaluasi sesi. Receipt bibliografi/demo wajib
cocok dengan hash seluruh snapshot; jangan memasangkan laporan S3 dengan subset Docling.
DB UI dan manifest lokal ada di `data/skripsi/ui-local/2026-11-21T08-16-45Z_07d296/`;
indeks/PDF berasal dari KB penuh. Clone repo tidak menyertakan artefak lokal ini.

### Evaluasi dan arti status

Setiap card berisi satu klaim dan metrik Faithfulness/Response Relevancy. Evaluasi
berjalan otomatis sekali per card dalam sesi jawaban yang sama, termasuk pada
demo. Membuka PDF/sitasi atau rerun biasa tidak mengulang evaluasi, termasuk hasil
gagal/partial. Submit baru atau berganti jawaban/korpus memulai sesi hasil baru;
cache provider tetap dipakai. Catatan evaluasi dibuka dari **Catatan jawaban**.

API evaluasi aktif otomatis, cache-first, maksimal lima request per card/1.024
output token per request, tanpa retry jaringan. Menilai banyak card menambah
batas biaya total: maksimum request evaluasi adalah lima kali jumlah card. Pertanyaan,
klaim card dan seluruh konteks dikirim ke judge. RAGAS berjalan di environment S5 isolated;
embedding pertanyaan lokal/pinned/offline melalui environment utama.

**Penggunaan token** memisahkan generator, RAGAS dan total input/output tercatat;
request API/cache hit ditampilkan sebagai ringkasan. Cache hit tidak menambah
token API baru. Usage gagal/hilang tidak dianggap lengkap; demo tidak menghitung
token generation historis sebagai pemakaian baru. Rincian metrik ada di
**Tentang skor RAGAS**, agar card tetap ringkas.

Laporan baru `paths.cache_dir/answer-quality/` mengikat jawaban kanonis, seluruh
konteks generation termasuk tak disitasi, claim ID, hash, config/model/seed/traces/usage.
Folder memuat teks korpus dan tidak untuk dibagikan/di-commit. Kegagalan/cache miss
menjadi **Belum tersedia** (null), bukan nol; jawaban tetap terbaca.

Faithfulness menilai klaim card terhadap seluruh konteks. Response Relevancy memakai
cosine (-1 sampai 1) pertanyaan asli vs pertanyaan hasil judge dari klaim card.
Ini relevansi potongan jawaban; satu card belum tentu menjawab seluruh pertanyaan.
Skor jawaban utuh tidak disalin ke tiap card. Keduanya estimasi AI, bukan jaminan fakta
atau ketepatan tiap sitasi. Context Recall hanya batch dengan jawaban acuan.

| Label MiniCheck | Arti |
|---|---|
| Didukung MiniCheck | Seluruh sitasi klaim diterima model |
| Perlu diperiksa | Ada sitasi ditolak/partial, meski sitasi lain belum dinilai |
| Belum diverifikasi | Hasil belum lengkap/error tanpa penolakan/partial |
| Tidak ada bukti | Klaim unsupported atau tanpa sitasi valid; bukan bukti seluruh korpus kosong |

Judge/audit sumber tidak mengganti label MiniCheck; audit AI bukan label manusia.
UI membutuhkan semua sitasi supported, sedangkan metrik citation recall/faithfulness
memakai sedikitnya satu per klaim. Lihat [kebijakan verifier](ARCHITECTURE.md#kebijakan-pelaporan-verifier).

## Setup

Gunakan Python `.venv` langsung. **Jangan `uv sync`/`uv run` pada environment CUDA
saat ini**: Torch dipasang manual dan belum selaras dengan lock. Default embedding CPU.
Linux memakai `.venv/bin/python`; launcher pytest Windows diblokir, gunakan module.

```powershell
.venv/Scripts/python.exe -m pytest -q
.venv/Scripts/python.exe -m ruff check .
.venv/Scripts/python.exe -m ruff format --check .
```

Tambahkan `-m "not gpu"` untuk melewati GPU. Instalasi environment baru saja:
`python -m pip install --user uv`, lalu `python -m uv sync --locked`.
Path config relatif terhadap direktori kerja; model/revision/device/batas dari YAML
tervalidasi. Jangan mencampur snapshot atau ruang embedding.

Jika model sudah tersedia dan proses harus offline:

```powershell
$env:HF_HUB_OFFLINE = '1'
$env:TRANSFORMERS_OFFLINE = '1'
$env:TOKENIZERS_PARALLELISM = 'false'
```

### Key dan izin API

Salin `.env.example` ke `.env` hanya jika belum ada; isi provider yang dipakai.
Environment diprioritaskan. Loader mendukung assignment UTF-8 satu baris, kutip,
komentar `#` dan prefix `export`; tanpa multiline, escape atau interpolasi.
Jangan menaruh key dalam YAML, command, log atau Git.

| Kebutuhan | Variabel |
|---|---|
| DeepSeek / OpenAI generator | `DEEPSEEK_API_KEY` / `OPENAI_API_KEY` |
| GPT judge Surplus | `SURPLUS_API_KEY`, `SURPLUS_API_URL`, `GPT_MODEL_ID` |
| JEV Surplus | `SURPLUS_API_KEY`, `SURPLUS_API_URL`, `JEV_MODEL_ID=jev-1.14` |

Surplus memakai HTTPS `https://api.surplusintelligence.ai/v1`; JEV juga menerima
`/v1/decisions`. CLI default cache-only meski `.env` tersedia; UI memakai API otomatis.
`--allow-api` membutuhkan izin dan batas konkret. Setelah crash, inspeksi
receipt/marker/journal/cache lalu replay tanpa API. Batch lama M6/S5/pilot sudah
selesai; jangan mengulang paid, mereset marker atau memakai sisa jatah.

## Impor dan admission PDF

```powershell
.venv/Scripts/python.exe -m rag.ingestion import-bib --bib reference-skripsi.bib --output-dir data/skripsi/references
.venv/Scripts/python.exe -m rag.ingestion prepare-local --config <config-baru.yaml> --manifest <manifest-tertinjau.json>
```

Impor offline membuat `entries.jsonl`, `references.jsonl`, `report.json` pada run
baru, tanpa menulis paper/chunk. Metadata bibliografi bukan bukti full text.
Input pengguna `data/reference-skripsi/` berisi 41 PDF + 3 TXT, bukan 44 PDF.
Inventaris/hash/manifest harus cocok sebelum admission. TXT tanpa halaman belum searchable.

`prepare-local` default maksimal tiga PDF; batch memakai `--max-documents <batas>`
di bawah `ingestion.max_papers`. Database harus baru. Jalur default mengikat
bibliografi/PDF/HTML/DOI/halaman/lisensi/waktu observasi dengan bukti artikel atau
receipt snapshot yang sama. Lisensi dataset tidak diterima sebagai lisensi artikel;
DOI baru boleh melengkapi field kosong, DOI lama tidak ditimpa. `fetched_at`
berarti observasi lokal, bukan receipt unduhan. Contoh:
`data/skripsi/local-pilot/2026-11-20T00-35-31Z_6fb4ad/admission-manifest.json`.

Koleksi pengguna boleh berlabel DOI/lisensi belum terverifikasi sesuai izin
2026-11-20. Gunakan manifest `admission_policy: user_local_collection`:

```powershell
.venv/Scripts/python.exe -m rag.ingestion prepare-local --config <config-baru.yaml> --manifest <manifest-lokal.json> --max-documents 41 --local-collection
```

Hash/path/halaman/enkripsi tetap diperiksa. Identitas terverifikasi dipertahankan;
sisanya memakai ID lokal berhash dan `LicenseRef-UserProvided-Unverified`, bukan
klaim OA. PDF tanpa chunk lolos gate tetap terdaftar sebagai held. UI menerima
receipt pada `--bibliography-report`. Kontrak lengkap di [KB-PREPARATION.md](KB-PREPARATION.md).

KB penuh: `data/skripsi/kb-local-all/2026-11-20T01-59-17Z_c95c3b/`, config
`kb/pipeline-config.yaml`, receipt `admission-receipt.json`. Tahap 1/2 dan
pilot lama adalah snapshot historis; default UI sudah KB penuh.

### Jalur historis downloader/PyMuPDF

Jangan mengunduh PDF tambahan. Replay downloader tanpa jaringan dan admission
laporan siap menggunakan jalur lama:

```powershell
.venv/Scripts/python.exe -m rag.ingestion download-bib --download-config configs/skripsi-download.yaml
.venv/Scripts/python.exe -m rag.ingestion prepare-bib --config configs/skripsi-pilot.yaml --download-report data/skripsi/downloads/2026-11-19T06-53-52Z_57a5ae/report.json
.venv/Scripts/python.exe -m rag.parsing --config configs/skripsi-pilot.yaml
.venv/Scripts/python.exe -m rag.chunking --config configs/skripsi-pilot.yaml
.venv/Scripts/python.exe -m rag.indexing --config configs/skripsi-pilot.yaml
```

Ledger lama 26/30 HTTP request dan semua lima slot PDF terpakai; sisa bukan izin
PDF baru. `--allow-network`, `discover`/`fetch` tidak diperlukan untuk koleksi pengguna.
Parse/chunk mendukung `--paper-id`. PyMuPDF tanpa OCR memakai section/urutan
heuristik dan tabel dapat rata. Token leksikal bukan token model; `drop` dilaporkan,
`merge` dapat melebihi target. Perubahan input/config/chunk memakai snapshot baru.

### Docling dan environment isolated

Docling 2.151.1/Heron/TableFormer accurate/EasyOCR id/en CUDA, batch satu,
model pinned/offline. Extract maksimal tiga PDF terdaftar per pemanggilan;
seluruh halaman asli diproses. Contoh memakai pilot historis:

```powershell
data/skripsi/docling-pilot/.venv/Scripts/python.exe -m rag.parsing.docling_pipeline extract --source-config configs/skripsi-pilot.yaml --docling-config configs/docling-pilot.yaml --samples data/skripsi/docling-pilot/samples-v2.json
.venv/Scripts/python.exe -m rag.parsing.docling_pipeline build --run <run>
.venv/Scripts/python.exe -m rag.indexing --config <run>/pipeline-config.yaml
```

Build Python utama menghitung ulang gate dari PDF; jangan memakai chunker PyMuPDF
pada artefak Docling. Raw dapat dipakai ulang jika hash/model/backend cocok;
SQL/index/label tetap terpisah. Header/caption/catatan/halaman dipertahankan,
struktur/OCR ambigu atau baris overlength ditahan tanpa truncation. Narasi memakai
jendela tokenizer; unit tunggal overlength tetap held. Policy 0,8/0,25 masih
heuristik; `do_cell_matching=True` tetap default. Artefak JSON/Markdown/HTML/native
comparison dan seluruh keputusan disimpan pada run baru.

Eksperimen halaman `rag.evaluation.docling --config configs/docling-pilot.yaml --offline`
memakai environment Docling dan tidak membangun korpus. Scan raster buatan bukan scan asli.

Jangan membuat ulang environment yang tersedia atau memasang lock isolated ke `.venv`
utama. Untuk instalasi baru saja:

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

## CLI retrieval, generation dan evaluasi

```powershell
.venv/Scripts/python.exe -m rag.retrieval --config configs/skripsi-local.yaml --question "Apa tugas dalam IndoNLU?" --mode hybrid
.venv/Scripts/python.exe -m rag.generation --config configs/skripsi-local.yaml --question "Apa tugas dalam IndoNLU?" --mode hybrid
.venv/Scripts/python.exe -m rag.evaluation --config <config-benchmark.yaml> --dataset <questions.jsonl> --mode all
.venv/Scripts/python.exe -m rag.evaluation --stage citations --config <config-benchmark.yaml> --mode hybrid+rerank
.venv/Scripts/python.exe -m rag.evaluation --stage agreement --config <config-benchmark.yaml> --annotations <labels.jsonl>
```

Retrieval membaca sumber; CLI generation menulis run/answer/claim ke DB config.
Gunakan salinan DB/config baru untuk eksperimen. Generator DeepSeek Flash non-thinking,
cache-only; batas panggilan mencakup koreksi format, retry transport nol. Cache miss
bukan abstention. MiniCheck lokal tidak membuktikan fakta hanya dari validitas ID.

Dataset wajib cocok dengan ID/hash snapshot. `eval/questions.jsonl` adalah benchmark
M6 empat paper, jangan dijalankan pada KB skripsi. `--with-judge` tidak mengizinkan
API tanpa `--allow-api`; budget berlaku lintas batch/mode. Laporan selalu run baru,
unknown/overlength/gagal bukan skor nol. Abstention sah `{"claims": []}`;
klaim penolakan unsupported tetap gagal. Definisi: [protokol evaluasi](ARCHITECTURE.md#9-protokol-evaluasi).

### Eksperimen retrieval KB penuh

Dataset AI sementara 32 answerable + 4 kontrol dan runner ada di
`data/skripsi/retrieval-local-all/2026-11-20T03-14-42Z_956cb9/`.
Freeze mengikat target/halaman/probe sebelum ranking; `prepare`, `baseline`,
`replay`, `analyze` menolak overwrite. Eksperimen baru memerlukan direktori baru;
kontrol dapat mendapat hit karena retriever tanpa ambang abstention.

Refinement/helper dan pilot generation selesai di
`data/skripsi/retrieval-refinement/2026-11-20T06-24-43Z_092865/`.
`generation-plan/plan.json` tetap proposal asal; authorization/marker/receipt
mencatat izin dan 7/14 request terpakai. **Jangan menjalankan paid lagi.**
`pilot.py replay` cache-only memakai DB baru; `verify --directory <run>` MiniCheck
lokal tidak menimpa verification yang sudah ada. Lihat summary/results/source-review.
Diagnosis 86 probe terpisah di
`data/skripsi/verifier-diagnosis/2026-11-20T12-46-00Z_5b9a21/`;
tidak ada transformasi/threshold/view terbaik yang dipromosikan.

### RAGAS batch S5

```powershell
.venv/Scripts/python.exe -m rag.evaluation.ragas prepare --config <config-skripsi.yaml> --dataset <questions.jsonl> --offset 0 --limit 4 --max-generation-calls 8
data/skripsi/s5-ragas/.venv/Scripts/python.exe -m rag.evaluation.ragas score --inputs <direktori-ragas-inputs> --max-judge-calls 12 --max-prompt-bytes 65536
```

Default cache-only; offset/limit tetap mengikat hash dataset utuh. Faithfulness
terhadap konteks dan context recall terhadap acuan AI bukan precision sitasi atau
gold manusia. Telemetri mati, tanpa retry judge/jaringan, run baru untuk replay.
Seluruh batch paid S5 sudah selesai; hasil/otorisasi di TASKS-SKRIPSI.

### Anotasi independen dan alternatif AI

Paket manusia opsional tetap null di
`data/skripsi/verifier-independent/2026-11-21T07-18-43Z_6b031a/`.
Baca `reviewer/README.txt`, salin `annotations.csv` menjadi `annotations-filled.csv`,
isi hanya label/annotator/notes. Label S/P/N lengkap, nilai seluruh klaim terhadap
satu chunk, tanpa pengetahuan luar. Ambigu: catat dan biarkan kosong sampai ditinjau;
import menolak label kosong. Jangan membuka maintainer/specs/prediksi sebelum menilai.

```powershell
$annotationRun = 'data/skripsi/verifier-independent/2026-11-21T07-18-43Z_6b031a'
.venv/Scripts/python.exe "$annotationRun/prepare.py" check
.venv/Scripts/python.exe "$annotationRun/prepare.py" import --csv "$annotationRun/reviewer/annotations-filled.csv"
```

Import membutuhkan 48 label/annotator, hash sumber tetap; output `human-labels-<timestamp>`
baru, tanpa scoring/API. Sampel hanya 12 unit berkorelasi dengan evidence Inggris.

Atas instruksi pengguna, evaluasi seluruhnya AI sudah selesai di
`data/skripsi/verifier-ai-evaluation/2026-11-21T07-34-32Z_0e9735/`:
48 GPT + 12 audit GPT, seluruh 60 request habis, MiniCheck lokal 48. Ini bukan
label manusia dan tidak mengubah paket manusia. Replay ke hasil baru:

```powershell
.venv/Scripts/python.exe data/skripsi/verifier-ai-evaluation/2026-11-21T07-34-32Z_0e9735/run.py replay
```

Cache lengkap dan `GPT_MODEL_ID` harus cocok dengan freeze. Jangan mengaktifkan API
untuk mengatasi cache miss atau mereset marker. Agreement bukan akurasi manusia.

## Troubleshooting

| Kondisi | Tindakan |
|---|---|
| `No module named uv` | Pakai Python `.venv` langsung; jangan sync CUDA |
| Model/cache offline belum ada | Periksa model/revision; cache miss bukan keluaran model |
| Hash/config/indeks berbeda | Gunakan snapshot baru; jangan hapus/rebuild sumber otomatis |
| Input overlength | Chunk lebih kecil pada snapshot baru atau tetap held/unverified; tanpa truncation |
| Cache LLM miss | UI otomatis memakai API berbatas; CLI tetap memerlukan `--allow-api`/izin batch |
| CUDA/OOM/konversi parsial | Catat kegagalan dan pertahankan artefak; partial bukan build sukses |
| Bibliografi/demo UI tidak cocok | Gunakan config/receipt/demo dari snapshot yang sama |
| `unexpected keyword argument 'claim_id'` setelah update | Restart proses Streamlit, lalu refresh browser; proses lama dapat menyimpan modul evaluator sebelum update |
