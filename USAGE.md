# Panduan penggunaan

Setup, perintah, dan batas perilaku pipeline yang sudah tersedia (M0 sampai M5). Pengantar proyek ada di [README.md](README.md); hasil verifikasi dan handoff ada di [TASKS.md](TASKS.md).

## Setup

Gunakan Python 3.11+ dan jalankan semua perintah dari root repo. Konfigurasi pipeline ada di [configs/config.yaml](configs/config.yaml); path dalam YAML relatif terhadap direktori kerja.

### Environment pengembangan saat ini

PyTorch CUDA dipasang manual, sedangkan `uv.lock` masih memakai sumber PyPI awal. `uv sync` atau `uv run` yang menyinkronkan environment dapat mengganti build CUDA. Sampai sumber/lock CUDA dirapikan, gunakan Python `.venv` langsung:

```powershell
.venv/Scripts/python.exe -m pytest -q
.venv/Scripts/python.exe -m pytest -q -m "not gpu"
.venv/Scripts/python.exe -m ruff check .
.venv/Scripts/python.exe -m ruff format --check .
```

Perintah pipeline di bawah juga memakai Python `.venv` langsung. Jika `.venv` sudah aktif, gunakan `python -m ...`; pada Linux/macOS tanpa aktivasi, gunakan `.venv/bin/python`. Pemanggilan `python -m pytest` diperlukan pada mesin pengembangan Windows karena Application Control memblokir launcher `pytest.exe`.

Config default memakai `embedding.device: cpu`. Operasi tensor GPU sudah diverifikasi, tetapi embedding BGE nyata masih baru diuji pada CPU. Permintaan `device: cuda` gagal dengan pesan jelas bila CUDA tidak tersedia. Uji embedding GPU harus memakai cache/direktori eksperimen baru agar membuktikan encoding nyata. Riwayat dan handoff CUDA ada di [TASKS.md](TASKS.md#m3--indexing).

### Instalasi baru

Bagian ini untuk environment baru. Bila `uv` belum terpasang, jalankan `python -m pip install --user uv`, lalu:

```bash
python -m uv sync --locked
```

`uv.lock` mengunci versi dependensi; `uv sync` membuat `.venv` dan memasang dependensi runtime serta dev yang sudah disetujui. Bentuk `python -m uv` bisa dipakai ketika executable `uv` belum ada di `PATH`. Jika `.venv` sudah aktif, `uv` yang dipasang di Python luar tidak otomatis tersedia di dalamnya; di Windows, `py -3.11 -m uv sync --locked` memanggil Python luar.

Setup tidak mengunduh bobot model atau memanggil API LLM. Pemeriksaan test/lint menggunakan perintah pada bagian environment di atas.

## Fondasi M0

```python
from rag.config import load_config
from rag.ids import make_chunk_id, make_paper_id

config = load_config("configs/config.yaml")
paper_id = make_paper_id("arxiv", "2401.12345v1")
chunk_id = make_chunk_id(paper_id, page=7, ordinal=3)
# arxiv:2401.12345v1:p7:c03
```

Jalankan contoh melalui `.venv/Scripts/python.exe` agar package tersedia. Loader menolak kunci hilang/tidak dikenal, tipe salah, dan nilai di luar batas dengan `ConfigError`. Path di dalam YAML tetap relatif terhadap direktori kerja, bukan lokasi file config.

Validator ID memeriksa sintaks, versi arXiv, dan batas halaman/ordinal. Generation M5 memeriksa keberadaan chunk di database serta keanggotaannya dalam konteks retrieval. Run ID memakai waktu UTC dan sufiks acak; laporan hasil disimpan sebagai run baru tanpa menimpa hasil lama.

## Data dan lisensi

Hanya paper open access. PDF, teks penuh, dan indeks tidak disimpan di repo; yang disimpan hanya ID/URL, metadata lisensi, dan skrip unduh.

## Ingestion M1

Atur bagian `ingestion` di `configs/config.yaml`, lalu jalankan tahap-tahap ini secara berurutan:

```bash
.venv/Scripts/python.exe -m rag.ingestion discover --config configs/config.yaml
.venv/Scripts/python.exe -m rag.ingestion fetch --config configs/config.yaml
```

`discover` mencari metadata lewat Atom API dan memeriksa lisensi lewat OAI-PMH `arXivRaw`, lalu menyimpan kandidat yang diterima ke `data/raw/candidates.jsonl`. `max_papers` membatasi jumlah hasil pencarian yang diperiksa, termasuk kandidat yang ditolak; jumlah paper diterima bisa lebih kecil. Default 10 kandidat ditujukan untuk uji awal, bukan korpus final 100–500 paper.

Default lisensi yang diterima: `CC-BY-4.0`, `CC-BY-3.0`, dan `CC0-1.0`. Lisensi hilang/tidak dikenal/di luar daftar ditolak dengan alasan di log. OAI-PMH hanya memberikan metadata versi terbaru, sehingga versi hasil pencarian wajib sama dengan versi terbaru pada riwayat OAI; sistem tidak menebak versi atau menerapkan lisensi terbaru pada versi lama. Referensi: [metadata OAI-PMH arXiv](https://info.arxiv.org/help/oa/index.html) dan [lisensi per versi](https://info.arxiv.org/help/license/index.html).

Request berlangsung satu per satu dengan jeda minimal 3 detik, sesuai [ketentuan API arXiv](https://info.arxiv.org/help/api/tou.html). Respons metadata di-cache per hari UTC di `data/cache/arxiv/`. Jangan menjalankan beberapa proses ingestion bersamaan. Timeout, batas ukuran PDF, dan jeda request tersedia di config; tidak ada retry otomatis untuk respons HTTP gagal.

`fetch` hanya mengunduh kandidat berlisensi yang diizinkan config, memeriksa header PDF serta ukuran maksimum, lalu menghitung SHA-256 dan menyimpan metadata ke tabel `paper` pada `data/index/corpus.db`. Hash tidak pernah diisi dengan placeholder. Nama file memakai `arxiv_<source_id>.pdf`, dengan `/` pada ID lama diganti `_` agar aman di Windows; ID kanonis di database tetap memakai format arsitektur.

Pengulangan memakai PDF lokal dan mempertahankan baris SQLite serta `parse_status`. Bila hash berbeda untuk versi paper yang sama, proses gagal tanpa memperbarui metadata atau menimpa file lama. Pemeriksaan struktur PDF lengkap ditunda ke parsing M2; M1 baru memeriksa header `%PDF-`.

## Parsing dan chunking M2

Jalankan M1 dengan config yang sama lebih dulu, lalu:

```bash
.venv/Scripts/python.exe -m rag.parsing --config configs/config.yaml
.venv/Scripts/python.exe -m rag.chunking --config configs/config.yaml
```

Kedua perintah mendukung `--paper-id arxiv:2401.12345v1` untuk satu paper. Perintah berjalan lokal, tanpa jaringan, model ML, GPU, atau API LLM.

Parser memakai posisi baris dan informasi font dari [PyMuPDF](https://pymupdf.readthedocs.io/en/latest/recipes-text.html). Ia mengurutkan dua kolom sederhana, menormalkan Unicode/whitespace, membuang teks margin yang berulang lintas halaman, serta mendeteksi heading umum/bernomor. Nomor halaman PDF tetap 1-indexed. Teks dan section disimpan ke `data/parsed/<safe_paper_id>.json` bersama hash dokumen, hash PDF, versi PyMuPDF, versi normalisasi, dan config parsing. `paper.parse_status` menjadi `ok` atau `failed`; alasan kegagalan tersimpan di laporan per run pada `data/parsed/reports/`.

Chunker menjaga batas section, rentang halaman, urutan global chunk per paper, dan overlap dari config. `chunking.tokenizer: lexical-v1` menghitung kata dan tanda baca dengan regex `\w+|[^\w\s]`. Angka `n_tokens` **bukan jumlah token model embedding/LLM**; M3 memeriksa batas tokenizer model sebelum encoding. Tidak ada bobot model yang diunduh untuk M2.

`short_chunk_policy: merge` menggabungkan ekor pendek dengan chunk sebelumnya dalam section yang sama; hasil gabungan dapat melebihi `target_tokens`. Pilihan `drop` membuang token baru pada ekor pendek. Section yang seluruhnya lebih pendek dari `min_tokens` dibuang pada kedua kebijakan, karena tidak digabung melintasi section. Jumlah token unik yang dibuang dilaporkan. `quality_flag=low_quality` hanya menandai karakter pengganti Unicode atau kontrol yang rusak; belum menjadi ukuran kualitas parsing secara menyeluruh.

Pengulangan memakai hasil parsing dengan manifest yang sama dan memverifikasi kesamaan seluruh baris chunk. Bila input/config parsing atau isi chunk berbeda, proses menolak menimpa hasil lama. Gunakan `parsed_dir` dan database terpisah untuk eksperimen; penghapusan/rebuild data lama memerlukan persetujuan. Nama file tetap aman di Windows, sedangkan format ID/sitasi dan skema SQLite tidak berubah. Config M0/M1 tetap bisa dimuat; field M2 yang belum ada memakai default dan dicatat dalam config efektif laporan.

OCR belum tersedia. Tabel, rumus, layout lebih dari dua kolom, serta heading yang tidak biasa belum divalidasi pada korpus besar. Keberhasilan satu PDF tidak mengukur akurasi sitasi atau kualitas retrieval.

## Indexing M3

Setelah M2, jalankan dengan config korpus yang sama:

```bash
.venv/Scripts/python.exe -m rag.indexing --config configs/config.yaml
```

Dalam `.venv` aktif, cukup `python -m rag.indexing --config configs/config.yaml`. Tahap ini memproses seluruh tabel `chunk`, termasuk `low_quality`; penyaringan kualitas dilakukan saat retrieval M4. Jalankan satu proses indexing pada satu korpus, tanpa ingestion/chunking bersamaan.

Embedder memakai [BAAI/bge-base-en-v1.5](https://huggingface.co/BAAI/bge-base-en-v1.5) berlisensi MIT melalui sentence-transformers. `embedding.revision` mengunci commit model, default `a5beb1e3e68b9ab74eb54cfd186867f64f240e1a`; `max_tokens: 512` membatasi input termasuk special tokens. Embedding dokumen tidak memakai prefix query, memakai float32, dan dinormalisasi. Bobot diunduh ke `paths.cache_dir/models/` pada penggunaan pertama. Tidak ada API LLM berbayar yang dipanggil.

M3 menghitung token dengan tokenizer model sebelum encoding. Chunk yang melebihi batas ditolak dengan ID dan jumlah tokennya; teks tidak dipotong. Target 400 token leksikal M2 tidak menjamin muat dalam 512 token model. Bila terjadi penolakan, buat database chunk baru dengan target lebih kecil. Jangan mengganti teks atau menghapus chunk pada database lama.

Vektor dan metadata ID/paper/halaman/section/kualitas disimpan dalam tabel `chunks` di `paths.index_dir/vectors.lance/`. Manifest mengunci identitas model dan dimensi. `chunk_fts` adalah virtual table FTS5 dalam database korpus, dengan tokenizer `unicode61 remove_diacritics 2`. Tokenizer ini sudah diuji terhadap pencarian huruf beraksen. SQLite `bm25()` menghasilkan skor lebih kecil untuk hasil lebih baik. Skema inti `paper`/`chunk` dan ID sitasi tetap sama.

Cache embedding berada di `paths.cache_dir/embeddings/`, berdasarkan hash teks dan identitas model, revision, dimensi, batas token, normalisasi, serta prefix dokumen. Teks identik berbagi satu cache. Pengulangan memuat cache dan hanya menambah baris indeks yang belum ada. Cache rusak, metadata indeks berbeda, atau manifest model berubah ditolak tanpa penggantian otomatis. Run parsial dapat dilanjutkan dengan input yang sama; penulisan LanceDB dan FTS5 tidak berada dalam satu transaksi bersama.

Laporan baru di `paths.index_dir/reports/` mencatat config efektif dan hash, seed, versi library, identitas model, jumlah chunk/vektor/FTS, waktu, token model, embedding baru, dan cache hit. Token model mencakup seluruh chunk; `computed_tokens` hanya menghitung teks unik yang baru di-encode. Waktu mencakup pemuatan model dan unduhan bila diperlukan. Kegagalan juga dilaporkan. Run lama tidak ditimpa.

## Retrieval M4

Setelah indexing M3 selesai, gunakan config korpus yang sama:

```powershell
.venv/Scripts/python.exe -m rag.retrieval --config configs/config.yaml --question "How is RAG retrieval evaluated?" --mode hybrid
```

Pilihan `--mode`: `bm25`, `dense`, `hybrid`, dan `hybrid+rerank`. Tanpa `--mode`, `retrieval.use_reranker` menentukan hybrid dengan atau tanpa reranker. Hasil berisi chunk asli, ID, paper, halaman, section, rank, skor, dan jenis skor; jumlah akhir dibatasi `retrieval.final_top_k`. BM25 mengurutkan skor dari kecil ke besar; cosine, RRF, dan logit reranker dari besar ke kecil. Skor antar mode tidak dapat dibandingkan langsung.

Retrieval hanya membaca database dan indeks. Snapshot chunk diperiksa terhadap indeks yang dipakai; indeks parsial, manifest model berbeda, atau metadata/teks yang berubah ditolak. Jangan menjalankan indexing atau perubahan korpus bersamaan dengan retrieval. Chunk `low_quality` disaring sebelum pemilihan kandidat/fusion. Bila semua chunk berkualitas rendah, hasil kosong tanpa memuat model. Mode BM25 tidak memuat model embedding atau reranker.

Dense memakai cosine exact search dengan urutan ID sebagai pemecah skor seri. Prefix query BGE berasal dari `retrieval.query_prefix`, mengikuti [model card BGE](https://huggingface.co/BAAI/bge-base-en-v1.5); isi `''` untuk menonaktifkannya dalam eksperimen. Prefix tidak diterapkan ke dokumen. Panjang query, prefix, dan special tokens diperiksa sebelum encoding; input terlalu panjang ditolak. Cache query memakai mekanisme embedding M3 di `paths.cache_dir/embeddings/`.

Hybrid menggabungkan dua daftar melalui RRF dengan rank mulai 1 dan `retrieval.rrf_k`, lalu membatasi hasil ke `retrieval.rerank_candidates`. Mode `hybrid+rerank` memberi skor ulang kandidat ini memakai [BAAI/bge-reranker-base](https://huggingface.co/BAAI/bge-reranker-base), revision terkunci di config. Reranker memakai device embedding, batch `retrieval.reranker_batch_size`, dan maksimum `retrieval.reranker_max_tokens` untuk pasangan query/dokumen. Query dipertahankan utuh; bagian dokumen yang dilihat reranker dapat dipotong (`only_second`). Teks chunk dan ID sitasinya tetap utuh. Query yang tidak menyisakan ruang dokumen ditolak.

Bobot reranker diunduh ke `paths.cache_dir/models/` pada penggunaan pertama yang memerlukan inference. Skor logit pasangan query/teks di-cache di `paths.cache_dir/reranking/`, dengan identitas model/revision, batas token, kebijakan pemotongan, dan hash query/teks. Cache rusak ditolak; perubahan identitas memakai cache baru. Tidak ada panggilan API LLM.

## Evaluasi retrieval M4

Siapkan JSONL validasi dengan format pertanyaan di [ARCHITECTURE.md](ARCHITECTURE.md#4-skema-data-sqlite). `gold_paper_ids` dan `gold_chunk_ids` harus ada di korpus yang dipakai. Dataset evaluasi final `eval/questions.jsonl` belum tersedia; fixture di `tests/fixtures/retrieval_questions.jsonl` hanya cocok dengan korpus sintetis pada test.

Contoh berikut memakai file validasi yang disiapkan sendiri di `data/validation/questions.jsonl`:

```powershell
.venv/Scripts/python.exe -m rag.evaluation --config configs/config.yaml --dataset data/validation/questions.jsonl --mode all
```

`--mode all` menjalankan keempat konfigurasi, masing-masing dengan run baru. Pilihan satu mode sama dengan CLI retrieval. Tanpa `--dataset`, path mengikuti `evaluation.dataset_path`. Runner tidak membuat atau memperbaiki gold set; ID tidak valid/hilang, qid duplikat, atau pasangan paper/chunk yang tidak sesuai ditolak sebelum inference.

Evaluasi mengambil ranking sampai `max(evaluation.ks)`, bukan `final_top_k` untuk prompt. Default menghasilkan Recall@5/10/20 dan MRR dengan kedalaman 20; kapasitas kandidat tetap mengikuti config retrieval. Recall/MRR dihitung per pertanyaan lalu dirata-ratakan untuk pertanyaan dengan gold chunk. Pertanyaan `unanswerable` disimpan dengan metrik `null` dan tidak masuk penyebut; penolakan jawaban dan faithfulness baru dievaluasi pada tahap berikutnya.

Setiap run membuat direktori baru di `evaluation.output_dir/<run_id>/` berisi `metrics.json`, `per_question.jsonl`, dan `report.md`. Karakter `:` pada nama direktori diganti `-` agar aman di Windows; ID run di laporan tetap kanonis. Laporan mencatat config/hash, seed, versi model/library/SQLite, backend aktual (termasuk mock), versi tabel vektor, hash dataset/korpus, ranking/skor per pertanyaan, statistik cache, dan waktu. Run gagal juga dicatat; tabrakan nama run ditolak tanpa menimpa hasil lama.

Smoke test lokal M4 memakai satu paper dan lima pertanyaan, termasuk reranker nyata di CPU dan pengulangan offline dengan ranking identik dari cache. Hasil, waktu, dan memori proses ada di TASKS.md. Reranking mempertahankan Recall@5 tetapi menurunkan MRR pada sampel ini; jangan menganggap reranker selalu meningkatkan kualitas. Evaluasi korpus penuh dan ketepatan sitasi menunggu M6.

## Generation dan sitasi M5

Modul `rag.generation` menjalankan retrieval lalu menghasilkan JSON klaim/sitasi, menyimpan hasil, dan merender referensi dari metadata serta kutipan chunk asli. Mode retrieval mengikuti pilihan M4. Contoh tanpa mengizinkan panggilan API baru:

```powershell
.venv/Scripts/python.exe -m rag.generation --config configs/config.yaml --question "How is RAG retrieval evaluated?" --mode hybrid
```

Secara default, generation hanya memakai cache respons yang sudah ada. Cache miss menghasilkan status gagal dan pesan `--allow-api`, tanpa memanggil provider. Context kosong menghasilkan "tidak ada bukti" tanpa memuat klien LLM. Untuk panggilan berbayar, pilih model API yang tersedia, siapkan key provider, lalu tambahkan `--allow-api` secara eksplisit. Key berasal dari `DEEPSEEK_API_KEY` atau `OPENAI_API_KEY` di environment; bila variabel belum ada, adapter membaca key provider dari `.env` di direktori kerja. Jalankan dari root repo. Jangan memasukkan key ke config atau argumen CLI.

Salin `.env.example` ke `.env` bila belum ada, lalu isi `DEEPSEEK_API_KEY=...` untuk DeepSeek. Loader hanya mengambil key provider terpilih, tanpa mengubah environment proses. Format yang didukung: satu assignment per baris, kutip tunggal/ganda opsional, prefix `export` opsional, serta komentar `#` (bungkus nilai dengan kutip jika mengandung `#`). File memakai UTF-8; BOM diterima. Multiline, escape sequence, dan interpolasi variabel tidak didukung. Environment yang sudah ada tetap diprioritaskan, termasuk nilai kosong yang akan ditolak. Membuat `.env` tidak mengaktifkan panggilan API.

Provider yang diimplementasikan: `deepseek` dan `openai`, memakai SDK OpenAI yang sudah terpasang dengan endpoint masing-masing. `generation.base_url: ''` memilih endpoint standar; override menerima HTTPS tanpa credential/query/fragment. Klien memakai JSON object mode, `generation.max_output_tokens`, `timeout_seconds`, dan `max_calls_per_run`. Retry transport SDK dinonaktifkan agar tidak melewati batas panggilan. Panduan protokol: [DeepSeek JSON Output](https://api-docs.deepseek.com/guides/json_mode/) dan [OpenAI Chat Completions](https://developers.openai.com/api/reference/python/resources/chat/subresources/completions/methods/create).

Model default yang dipilih pengguna adalah `deepseek-flash`, dengan `generation.thinking: false`. Adapter mengirim `thinking.type: disabled` secara eksplisit untuk DeepSeek; `true` mengaktifkannya. Parameter ini tidak dikirim ke OpenAI. Thinking aktif secara default pada API DeepSeek dan mengabaikan temperature; pengaturannya mengikuti [dokumentasi Thinking Mode](https://api-docs.deepseek.com/guides/thinking_mode/). Cache respons membedakan mode thinking agar hasil eksperimen tidak tercampur. Config lama yang tidak menyebutkan field ini memakai `false`.

Uji API nyata satu pertanyaan sudah berhasil, termasuk pengulangan tanpa request baru dari cache lokal. Ini memvalidasi koneksi dan format, bukan benchmark kualitas atau perbandingan antar model. Token, estimasi biaya, latensi, RAM/VRAM, serta lokasi artefak tercatat di TASKS.md bagian uji API DeepSeek sebelum M6.

Prompt hanya berisi pertanyaan, instruksi format/grounding, dan chunk hasil retrieval yang cocok dengan SQLite. ID, teks, paper, halaman, section, kualitas, dan status parsing diperiksa sebelum pengiriman. Judul untuk referensi berasal dari database. Chunk lain di korpus tidak dimasukkan. Instruksi dalam question/chunk diperlakukan sebagai data tak tepercaya.

Respons harus mengikuti format klaim/sitasi di ARCHITECTURE.md. JSON nonvalid, field tambahan/duplikat, struktur klaim salah, atau output terpotong memperoleh satu retry format, tetap tunduk pada batas panggilan. Retry memakai konteks yang sama dan tidak memasukkan klaim dari respons gagal sebagai bukti. Setelah dua kegagalan, hasil dicatat sebagai gagal tanpa klaim parsial.

ID yang sintaksnya salah, hilang dari database, atau berada di luar konteks dibuang dan dicatat alasannya. Sitasi ganda dideduplikasi dengan urutan tetap. Klaim tanpa sitasi valid tetap disimpan dan diberi label "tidak ada bukti"; klaim yang sudah ditandai unsupported oleh LLM juga mempertahankan label tersebut. Sitasi valid secara ID belum berarti chunk mendukung makna klaim: rendering menyatakan "belum diverifikasi" sampai M6.

Cache di `paths.cache_dir/llm/` mencakup provider/endpoint, model, temperature, batas output, backend, dan seluruh prompt. Backend mock memakai namespace berbeda dari provider nyata. Cache menyimpan respons, model yang dilaporkan provider, token input/output, finish reason, provenance, dan checksum. Cache rusak ditolak tanpa panggilan pengganti otomatis. Cache hit tidak memakai jatah panggilan dan mencatat nol token baru; usage asli tetap tersedia pada attempt. Usage hilang/tidak valid membuat run gagal dan ditandai unknown, bukan dianggap gratis.

M5 membuat tabel `run`, `answer`, dan `claim` sesuai skema yang sudah ditetapkan di ARCHITECTURE.md. Hanya tabel hasil ini yang ditulis; paper, chunk, FTS, dan vektor dipertahankan. Tabel lama yang nama kolomnya tidak cocok ditolak tanpa penggantian. Gunakan salinan database/index untuk smoke test atau eksperimen yang perlu memisahkan riwayat.

Laporan baru di `paths.index_dir/reports/generation-<run_id>.json` memuat config/hash, seed, code version, konteks ID/hash, backend, respons setiap attempt, usage/token baru, cache hit, format failure, sitasi yang ditolak, klaim, referensi, dan status verifikasi. `answer.raw_response` menyimpan respons terakhir; respons sebelumnya tetap ada di laporan/cache. Run gagal juga disimpan, termasuk raw response yang gagal format. Output gagal memakai exit code 1. Tidak ada penggantian run/report lama.

Test dan smoke test M5 memakai LLM mock, tanpa API berbayar. Pengukuran RAM/VRAM proses dengan embedding/reranker CPU nyata serta keterbatasannya dicatat di TASKS.md. Verifikasi semantik dan metrik sitasi baru dikerjakan pada M6.
