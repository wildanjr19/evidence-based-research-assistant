# TASKS.md

Milestone pengerjaan. Aturan: satu milestone selesai sebelum lanjut, dan "selesai" berarti acceptance criteria terpenuhi **dan** `pytest -q` + `ruff check .` bersih (AGENTS.md §12).

Spesifikasi teknis tiap milestone ada di `ARCHITECTURE.md`; jangan mengubah skema data atau format ID/sitasi selama implementasi tanpa memperbarui dokumen itu lebih dulu.

---

## M0 — Fondasi repo

**Deliverable:** `pyproject.toml`, `.gitignore`, `.env.example`, `configs/config.yaml`, `src/rag/__init__.py`, `src/rag/config.py`, `src/rag/ids.py`, `tests/test_ids.py`.

**Acceptance criteria:**

- [x] `uv sync` berhasil dari repo bersih.
- [x] `pytest -q` dan `ruff check .` lulus.
- [x] `config.py` memuat YAML dan memvalidasi kunci wajib; config yang cacat menimbulkan error jelas, bukan `KeyError`.
- [x] `ids.py` membuat dan memvalidasi ID sesuai regex di `ARCHITECTURE.md` §5, dengan test untuk ID valid dan tidak valid.
- [x] `data/`, `.env`, dan cache tidak akan ter-commit (pola diverifikasi dengan `git check-ignore`; pipeline belum tersedia).

**Verifikasi M0 (2026-11-18):** Python 3.11.0 / Windows; `python -m uv sync` berhasil membuat environment baru, `python -m uv sync --locked` berhasil; 93 test lulus pada jalur penuh dan `not gpu`; Ruff lint dan pemeriksaan format bersih. Perintah lengkap ada di [USAGE.md](USAGE.md). CUDA, unduhan model, dan API LLM belum diuji pada tahap M0.

**Dependensi (sudah disetujui):** runtime — `pyyaml`, `pymupdf`, `httpx`, `lancedb`, `sentence-transformers`, `torch`, `openai`, `streamlit`; dev — `pytest`, `ruff`.

Catatan: `torch` dari PyPI di Windows terpasang sebagai build CPU. Konfigurasi `embedding.device: cuda` baru bisa dipakai setelah build CUDA dipasang; sampai itu diverifikasi, jalankan dengan `device: cpu`. Dependensi lain di luar daftar ini tetap butuh konfirmasi (AGENTS.md §8).

---

## M1 — Ingestion metadata

**Deliverable:** klien sumber (arXiv untuk v1), penyimpanan metadata + lisensi ke tabel `paper`.

**Acceptance criteria:**

- [x] Bisa mengunduh metadata N paper untuk satu query domain, dengan batas jumlah dari config.
- [x] Setiap paper punya `license` terisi; paper tanpa lisensi jelas ditolak dengan log alasan.
- [x] Penulisan ulang paper yang sama bersifat idempoten.
- [x] Test memakai fixture respons API, tanpa jaringan.

**Verifikasi M1 (2026-11-18):** 130 test lulus pada jalur penuh dan `not gpu`; Ruff lint/format bersih. Fixture mencakup pagination, penolakan lisensi, ketidakcocokan versi, cache/jeda request, HTTP gagal, ukuran/header PDF, validasi kandidat, hash, dan idempotensi. Uji nyata satu kandidat pada query domain v1 berhasil melalui Discover + Fetch: `arxiv:2605.14488v1`, `CC-BY-4.0`. Data lokal berada di `data/m1-smoke/` dan diabaikan Git; korpus final belum dikumpulkan.

Karena skema mewajibkan hash PDF, metadata masuk JSONL dahulu dan baru disimpan ke `paper` setelah Fetch. Tidak ada perubahan skema. `max_papers` membatasi kandidat yang diperiksa, termasuk yang ditolak. Perintah CLI dan batas perilaku ada di [USAGE.md](USAGE.md).

---

## M2 — Parsing dan chunking

**Deliverable:** parser PyMuPDF, section-aware chunker, tabel `chunk` terisi.

**Acceptance criteria:**

- [x] Setiap chunk punya `page_start`, `page_end`, `section` (bila terdeteksi), `n_tokens`.
- [x] Chunk di bawah `min_tokens` digabung atau dibuang, sesuai aturan di config.
- [x] Chunking deterministik: input sama → ID dan isi sama.
- [x] Test unit: chunking teks sintetis, termasuk teks dua kolom dan header/footer berulang.
- [x] Dilaporkan berapa paper gagal di-parse dan alasannya (`parse_status`).

**Verifikasi M2 (2026-11-18):** 165 test lulus pada jalur penuh dan `not gpu`; Ruff lint/format bersih. Uji lokal satu PDF nyata 16 halaman menghasilkan 20 chunk, 0 token leksikal terbuang, dan baris yang identik saat diulang. Artefak terverifikasi ada di `data/m2-smoke-v2/`; percobaan awal tetap disimpan, tanpa penghapusan data M1 atau chunk lama.

Test memakai PDF sintetis di direktori sementara, termasuk dua kolom, header/footer berulang, inline bold pada daftar bernomor, file rusak, dan halaman tanpa teks. PDF nyata yang diuji adalah `arxiv:2605.14488v1`; config, database salinan metadata M1, teks parsed, dan laporan ada di `data/m2-smoke-v2/`. Percobaan versi normalisasi awal tetap tersimpan di `data/m2-smoke/`.

Default `lexical-v1` tidak mengklaim jumlah token model. `merge` hanya menggabungkan ekor dalam section yang sama dan dapat melebihi target; section pendek yang tidak dapat digabung dibuang. Jumlah token terbuang dicatat. M3 wajib memeriksa batas model embedding. OCR, layout kompleks, dan kalibrasi kualitas pada korpus penuh belum dilakukan.

---

## M3 — Indexing

**Deliverable:** embedding `bge-base-en-v1.5` ke vector store, indeks BM25/FTS5, embedding cache.

**Acceptance criteria:**

- [x] Seluruh chunk terindeks; jumlah di vector store = jumlah di tabel `chunk`.
- [x] Cache embedding mencegah perhitungan ulang saat run diulang.
- [x] Waktu indexing dan jumlah token/embedding dicatat.
- [x] Test yang butuh GPU diberi marker `gpu`; jalur default tetap lulus tanpa GPU.

**Verifikasi awal M3 (2026-11-18):** 185 test lulus, satu test GPU dilewati karena PyTorch CPU; Ruff lint/format bersih. Test memakai embedder mock dan LanceDB/FTS5 nyata, mencakup cache, deduplikasi/batch, special tokens, penolakan truncation, cache rusak, kelanjutan indeks parsial, konflik metadata/model, dan laporan run unik. Uji BGE nyata pada CPU menghasilkan 21 baris SQLite = 21 vektor = 21 FTS5 pada database baru `data/m3-smoke/`. Run pertama: 21 embedding, 8.758 token model, 20,38 detik termasuk pemuatan model/unduhan. Pengulangan offline: 21 cache hit, nol embedding/token baru, 6,00 detik. Target eksperimen diturunkan menjadi 380 token leksikal; maksimum input 491 token model. Data M2 dipertahankan, termasuk chunk lama 514 token yang melebihi batas BGE 512. Korpus penuh dan kualitas retrieval belum dievaluasi.

**Penutupan M3 (2026-11-18):** seluruh acceptance criteria terpenuhi. Pengguna memasang PyTorch `2.15.0+cu132`; CUDA aktif pada RTX 3060 Ti 8 GB. Verifikasi ulang: 186 test lulus, termasuk operasi tensor GPU; Ruff lint/format bersih. Embedding BGE nyata masih baru diuji pada CPU. Config default tetap CPU dan `uv.lock` belum mengunci varian CUDA yang dipasang manual.

PyTorch dan LanceDB berhasil diimpor setelah blokir Windows ditangani manual. Keberhasilan uji satu paper belum menjadi benchmark korpus penuh atau ukuran kualitas retrieval/sitasi.

**Handoff sesi berikutnya:** baca AGENTS.md, README, [USAGE.md](USAGE.md), ARCHITECTURE, dan bagian M4 di bawah. Perubahan M3 masih ada di working tree, belum di-commit saat penutupan. Gunakan `.venv/Scripts/python.exe` langsung; hindari sinkronisasi environment sebelum memutuskan sumber/lock CUDA karena dapat mengganti build GPU. Jika ingin memakai GPU, rapikan konfigurasi/lock dan lakukan uji embedding nyata ke direktori eksperimen baru; cache CPU tidak membuktikan encoding GPU. Setelah itu lanjut M4: dense, BM25, RRF, reranker, dan Recall@k/MRR pada set validasi kecil. Jangan mengubah data M2/M3 atau dataset evaluasi untuk memperbaiki hasil. Pada penutupan M3, implementasi M4–M7 belum tersedia; status terkini ada pada bagian milestone masing-masing.

---

## M4 — Retrieval

**Deliverable:** dense, BM25, RRF, reranker, orkestrasi dengan knob dari config.

**Acceptance criteria:**

- [x] Empat konfigurasi bisa dijalankan: BM25, dense, hybrid, hybrid+rerank.
- [x] RRF punya test unit dengan nilai yang sudah dihitung manual.
- [x] Recall@5/10/20 dan MRR dihitung terhadap gold chunk pada set validasi kecil.
- [x] Hasil per konfigurasi tersimpan per `run_id`, tidak saling menimpa.

**Verifikasi M4 (2026-11-18):** 219 test lulus; Ruff lint dan format bersih. Test memakai LanceDB/FTS5 nyata, embedding/reranker mock, serta fixture lokal tanpa jaringan/API berbayar. Cakupan meliputi RRF dan metrik dengan hitungan manual, empat mode, filter kualitas sebelum cutoff, ID/teks chunk kanonis, cache query/pasangan, batas token, indeks parsial/berbeda, skor tidak valid, validasi gold set, laporan gagal, tabrakan run ID, dan dispatch/error CLI. Wrapper reranker diperiksa dengan model/tokenizer mock, termasuk revision, raw logit, dan truncation dokumen saja.

Validasi sintetis terpisah memakai 30 chunk (satu `low_quality`) dan lima pertanyaan, termasuk comparison, synthesis, dan unanswerable. Keempat mode berhasil menghasilkan run terpisah di `data/m4-validation/2026-11-18T06-02-41Z_be478e/results/`; backend mock dicatat di manifest. Ini verifikasi logika/alur, bukan ukuran kualitas model. Fixture berada di `tests/fixtures/retrieval_questions.jsonl`; gold set final `eval/` belum dibuat atau diubah.

**Smoke test CPU awal (tanpa reranker):** BGE dari cache offline dipakai pada indeks M3 berisi 21 chunk dari satu paper, dengan lima pertanyaan lookup dan gold chunk yang dipilih sebelum retrieval. Config, dataset validasi lokal, dan laporan ada di `data/m4-smoke/2026-11-18T06-00-30Z_4cfc6b/`. Hash database sebelum/sesudah sama; tabel vektor tetap versi 1. Pengulangan memakai cache query tanpa encoding baru.

| Mode | Recall@5 | Recall@10 | Recall@20 | MRR (kedalaman 20) |
|---|---|---|---|---|
| BM25 | 0.8 | 1.0 | 1.0 | 0.7250 |
| Dense | 0.8 | 1.0 | 1.0 | 0.5952 |
| Hybrid | 1.0 | 1.0 | 1.0 | 0.7067 |

Run CPU dengan manifest akhir: BM25 `2026-11-18T06:02:44Z_972e53`, dense `2026-11-18T06:02:44Z_000659`, hybrid `2026-11-18T06:02:50Z_2c6f0e`. Angka satu paper/lima pertanyaan ini belum membuktikan keunggulan hybrid pada korpus penuh atau ketepatan sitasi.

**Verifikasi reranker nyata CPU (2026-11-18):** `BAAI/bge-reranker-base` revision `2cfc18c9415c912f9d8155881c133215df768a70` berhasil dimuat melalui wrapper produksi, tanpa mock. Enam file model/tokenizer (1.134.374.819 byte) diunduh ke cache model; persiapan termasuk hash file selesai dalam 15,71 detik. Setelah itu, inference pertama dan pengulangan dijalankan offline dengan dataset lima pertanyaan yang sama, tanpa perubahan gold.

Run pertama menghitung 105 pasangan (21 kandidat per pertanyaan), dengan nol cache hit reranker. Semua ranking evaluasi berisi 20 ID unik dengan skor finite yang terurut menurun. Top-1 berubah pada kelima pertanyaan. Pengulangan di proses baru menghitung nol pasangan/embedding query baru, memakai 105 cache hit, dan menghasilkan ranking serta skor identik. Backend reranker tidak dimuat pada pengulangan karena semua skor tersedia di cache. Hash database dan seluruh file indeks vektor sebelum/sesudah sama.

| Run CPU | Recall@5/10/20 | MRR (kedalaman 20) | Waktu run |
|---|---|---|---|
| Hybrid pembanding | 1.0 / 1.0 / 1.0 | 0.7067 | 6,09 detik |
| Hybrid+rerank, 105 pasangan baru | 1.0 / 1.0 / 1.0 | 0.5667 | 21,91 detik |
| Hybrid+rerank, cache offline | 1.0 / 1.0 / 1.0 | 0.5667 | 6,35 detik |

Waktu hybrid mencakup pemuatan embedding; run reranker pertama mencakup pemuatan reranker, dengan embedding sudah dimuat. Pengulangan memakai proses baru dan tetap memuat embedding untuk memeriksa identitas indeks. Angka ini bukan benchmark latensi yang memisahkan waktu model dari startup.

Puncak working set proses pengujian pertama adalah 3,07 GiB; puncak private commit 5,15 GiB. Proses pengulangan mencapai 1,26 GiB working set. Pengukuran memakai [Windows process memory counters](https://learn.microsoft.com/en-us/windows/win32/api/psapi/ns-psapi-process_memory_counters_ex), mencakup runtime, embedding, dan reranker; bukan RAM reranker saja atau VRAM.

Peringkat gold untuk lima pertanyaan berubah dari `[1, 3, 1, 1, 5]` menjadi `[2, 1, 3, 2, 2]`. MRR turun, meskipun semua gold tetap ditemukan dalam top-5. Dataset dan label tidak diubah untuk meningkatkan skor. Sampel satu paper ini belum cukup untuk memilih konfigurasi terbaik; perbandingan kualitas tetap menjadi pekerjaan M6.

Artefak baru ada di `data/m4-reranker-smoke/2026-11-18T07-06-30Z_b88c51/`: config, salinan dataset dengan hash sama, skrip `smoke.py`, `download-evidence.json`, `first-evidence.json`, `repeat-evidence.json`, dan laporan per run. Run hybrid: `2026-11-18T07:08:31Z_072b8f`; reranker pertama: `2026-11-18T07:08:37Z_122a4b`; cache offline: `2026-11-18T07:09:22Z_3084e3`. Semua artefak/model berada di `data/` yang diabaikan Git. Verifikasi repo: 219 test lulus, Ruff lint/format bersih.

**Batas verifikasi:** embedding query/reranker GPU dan benchmark korpus penuh belum diuji. Tidak ada dependensi baru, perubahan skema SQLite/ID/sitasi, sinkronisasi environment CUDA, atau panggilan LLM. Smoke test CPU reranker nyata sudah selesai.

**Handoff M5:** panduan CLI retrieval/evaluasi ada di [USAGE.md](USAGE.md). Implementasikan grounding prompt, klien LLM modular, validasi JSON klaim/sitasi, serta test LLM mock sesuai bagian M5. Gunakan `.venv/Scripts/python.exe` langsung; sumber/lock CUDA masih perlu dirapikan bila GPU akan dipakai. Bobot reranker CPU sudah tersedia di cache. Untuk menguji GPU, gunakan cache eksperimen baru agar membuktikan inference nyata, lalu simpan hasil sebagai run baru. Korpus M2/M3 dan hasil M4 tetap dipertahankan.

---

## M5 — Generation dan sitasi

**Deliverable:** prompt grounding, klien LLM modular, validasi JSON klaim, render sitasi.

**Status: ditutup (2026-11-18).** Seluruh acceptance criteria terpenuhi; verifikasi pada penutupan setelah penambahan loader `.env`: 283 test lulus, Ruff lint/format bersih. Penutupan mencakup implementasi dan pengujian dengan LLM mock/transport HTTP lokal. Hasil uji DeepSeek API nyata setelah penutupan dicatat terpisah di bawah sebagai persiapan M6.

**Acceptance criteria:**

- [x] Prompt hanya berisi chunk terambil; ada test yang memastikan tidak ada teks luar yang bocor ke prompt.
- [x] Output LLM non-JSON atau ID tidak valid ditangani tanpa crash, dan dicatat sebagai kegagalan.
- [x] Klaim tanpa sitasi valid dirender sebagai "tidak ada bukti", bukan dihapus.
- [x] Test penuh memakai LLM mock; tidak ada panggilan API berbayar di test.
- [x] Token in/out tiap panggilan tercatat.

**Verifikasi M5 (2026-11-18):** 268 test lulus; Ruff lint/format bersih. Test mencakup prompt tanpa teks chunk di luar retrieval, JSON/schema/Unicode invalid, sintaks/keberadaan/keanggotaan ID, deduplikasi sitasi, klaim unsupported, rendering metadata kanonis, cache/provenance, satu retry format, batas panggilan, respons terpotong, usage hilang/invalid, error tanpa bocor key, konflik skema, kegagalan SQLite, run collision, integrasi FTS, dan CLI. SDK OpenAI nyata diuji dengan transport HTTP mock untuk DeepSeek/OpenAI; request/token usage diperiksa, termasuk HTTP 500 tanpa retry SDK. Tidak ada jaringan/provider berbayar pada test.

**Smoke test M5:** salinan database dan indeks M3 dibuat di `data/m5-smoke/2026-11-18T08-20-39Z_028e06/`. Retrieval memakai embedding dan reranker CPU nyata dari cache offline; generator memakai `FixtureLLM`, bukan provider API. Pertanyaan baru mengambil delapan chunk; satu klaim fixture bersitasi ke `arxiv:2605.14488v1:p7:c11`, satu klaim fixture tanpa bukti mempertahankan label unsupported. Kutipan/judul/halaman berasal dari database. Panggilan backend API nyata diblokir pada skrip smoke.

Run pertama `2026-11-18T08:21:57Z_58718c` menyimpan satu run, satu answer, dan dua claim pada tabel sesuai arsitektur. Pengulangan proses baru `2026-11-18T08:22:54Z_07f2d8` memakai satu cache hit LLM, nol panggilan backend baru, serta menghasilkan Markdown/referensi identik; total menjadi dua run, dua answer, empat claim. Foreign key check bersih. Hash database/seluruh file indeks M3 asli tetap sama; baris paper/chunk/FTS pada salinan eksperimen juga tetap sama. Token dari mock adalah fixture nol, bukan pengukuran tokenizer/usage layanan nyata. Jumlah panggilan API berbayar: nol.

| Proses smoke M5 | Waktu seluruh alur | Puncak working set | Puncak private commit | Puncak VRAM PyTorch |
|---|---|---|---|---|
| Retrieval/reranker CPU nyata + LLM mock | 12,55 detik | 3,03 GiB | 5,04 GiB | 0 byte |
| Pengulangan dengan cache | 6,28 detik | 1,26 GiB | 3,07 GiB | 0 byte |

RAM diukur dengan Windows process memory counters dan mencakup runtime, embedding, reranker, serta pipeline. VRAM adalah alokasi allocator PyTorch proses ini; CUDA tidak diinisialisasi. Angka nol bukan pengukuran pemakaian seluruh GPU oleh Windows/proses lain. Waktu mencakup retrieval/pemuatan model dan penyimpanan; belum mencakup latensi API LLM nyata. `generation.elapsed_seconds` hanya mengukur tahap generation setelah retrieval; tabel di atas memakai pengukuran seluruh alur pada skrip smoke.

Config, salinan data, skrip `smoke.py`, `first-evidence.json`, `repeat-evidence.json`, dan laporan generation tersimpan di direktori smoke tersebut, diabaikan Git. Tidak ada dependensi baru, sinkronisasi CUDA, perubahan format sitasi, atau perubahan baris korpus/dataset evaluasi.

**Batas verifikasi pada penutupan M5:** LLM/provider API nyata, biaya/token aktual provider, dukungan semantik klaim, GPU, dan korpus penuh belum diuji. Config saat itu masih `deepseek-chat`; pemilihan dan uji model penggantinya dicatat pada bagian persiapan M6 di bawah.

**Persiapan API — `.env`:** adapter kini membaca key provider terpilih dari `.env` di direktori kerja bila variabel environment belum ada. Environment tetap diprioritaskan; tidak ada ekspansi/eksekusi nilai, pemuatan variabel lain, dependensi baru, atau panggilan API otomatis. Test memakai key fixture dan transport HTTP mock, termasuk precedence, BOM/kutip/komentar, serta error tanpa bocor nilai. Format dan batas loader ada di USAGE.md.

Verifikasi loader: 283 test lulus; Ruff lint/format bersih. Pemeriksaan lokal menemukan `.env` dan berhasil memuat key efektif tanpa mencetak nilainya; autentikasi provider belum diuji. Puncak working set proses pemeriksaan loader 23,68 MiB (runtime Python + impor modul, bukan seluruh pipeline). Tidak ada model GPU yang dimuat; VRAM tidak diukur. Tidak ada panggilan API berbayar.

### Uji API DeepSeek sebelum M6 (2026-11-18)

Pengguna memilih `deepseek-flash`. Config default diperbarui dengan `generation.thinking: false`; adapter mengirim mode ini secara eksplisit mengikuti [Thinking Mode DeepSeek](https://api-docs.deepseek.com/guides/thinking_mode/). Field boolean tervalidasi dan ikut identitas cache agar hasil thinking/non-thinking terpisah. Tidak ada dependensi baru. Verifikasi repo: 289 test lulus; Ruff lint/format bersih, termasuk test SDK transport mock untuk kedua mode serta pemisahan cache. Test otomatis tidak memakai API berbayar.

Uji nyata dibatasi satu pertanyaan dan maksimal dua request, tanpa retry transport SDK. Pertanyaan: "Which three evaluation properties does the Deepchecks paper identify for a RAG system?" Retrieval/reranker CPU nyata mengambil delapan chunk dari salinan korpus satu paper. Satu request API berhasil (HTTP 200, finish reason `stop`), tanpa retry format: 3.921 input token, 208 output token; input provider cache hit 0 dan miss 3.921. Respons JSON memuat empat klaim, semuanya bersitasi ke `arxiv:2605.14488v1:p7:c11`; tidak ada ID ditolak atau usage hilang. Server melaporkan model `deepseek-flash` tanpa identitas snapshot yang lebih spesifik.

Latensi HTTP termasuk pembacaan respons adalah 1,61 detik. Waktu alur pertama termasuk retrieval/pemuatan model dan pemeriksaan hasil: 24,79 detik. Berdasarkan [tarif resmi yang diperiksa](https://api-docs.deepseek.com/quick_start/pricing/), estimasi biaya request adalah US$0,00071295 pada tarif off-peak atau US$0,0014259 pada tarif peak. Kedua tarif disimpan untuk transparansi; ini estimasi dari token usage, bukan pembacaan tagihan/saldo akun.

Pengulangan pada proses baru memakai satu cache hit lokal, nol request API dan nol token baru, menghasilkan Markdown/referensi identik dalam 5,02 detik. Run pertama `2026-11-18T09:09:00Z_d70d6d`, pengulangan `2026-11-18T09:09:29Z_65bf06`; database eksperimen menyimpan dua run, dua answer, delapan claim dengan foreign key check bersih. Hash database/seluruh file indeks M3 asli serta baris paper/chunk/FTS salinan eksperimen tetap sama.

| Proses uji API | Puncak working set | Puncak private commit | Puncak VRAM PyTorch |
|---|---|---|---|
| Retrieval/reranker CPU + DeepSeek API | 3,05 GiB | 5,05 GiB | 0 byte |
| Pengulangan dengan cache | 1,27 GiB | 3,08 GiB | 0 byte |

RAM mencakup proses Python lokal, bukan RAM model LLM di server. CUDA tidak diinisialisasi; angka VRAM berasal dari allocator PyTorch proses ini, bukan pemakaian GPU seluruh sistem. Artefak di `data/deepseek-smoke/2026-11-18T09-07-49Z_733dac/`: manifest/config, `smoke.py`, `first-evidence.json`, `repeat-evidence.json`, salinan database/indeks, dan laporan generation. Artefak diabaikan Git dan tidak menyimpan key API. Satu pertanyaan ini memvalidasi integrasi/format/cache; belum menjadi benchmark kualitas, abstention, faithfulness, perbandingan model, GPU, atau korpus penuh.

**Handoff M6:** koneksi DeepSeek Flash dan cache sudah diuji. Implementasikan verifier lokal, runner evaluasi sitasi, dataset/gold set versi pertama sesuai protokol, dan laporan metrik. Pertahankan dataset yang sudah diberi label; jangan mengubah label untuk menaikkan skor. Validasi ID M5 bukan verifikasi bahwa teks chunk mendukung klaim. Untuk GPU, rapikan sumber/lock CUDA dan gunakan cache eksperimen baru agar membuktikan inference nyata.

---

## M6 — Verifikasi dan evaluasi

**Deliverable:** MiniCheck lokal, LLM-judge sampel, dataset 30–50 pertanyaan, skrip evaluasi, laporan run pertama.

**Status: berjalan (2026-11-18).** Sesuai arahan pengguna, sesi ini menyiapkan
jalur evaluasi dan bahan anotasi karena korpus beberapa paper serta label manusia
belum tersedia. M6 belum ditutup. Implementasi/test dan smoke test nyata tersedia;
gold set final, judge API nyata, dan kesepakatan terhadap manusia tetap menunggu.

**Verifikasi repo sebelum Jev:** 328 test lulus melalui `.venv/Scripts/python.exe -m pytest -q`;
Ruff lint/format dan `git diff --check` bersih. Sebanyak 39 test baru mencakup
adapter model, cache/checksum, token limit, validasi/persistensi, schema conflict,
judge JSON/sampling, batas batch, abstention, metrik/kappa, anotasi/hash CRLF,
run collision, kegagalan disk/persistensi, serta dispatch CLI. Semua test memakai
fixture/mock untuk model dan LLM, tanpa request API berbayar. Pemeriksaan hasil
publik menemukan nol salinan chunk penuh; seluruh direktori `eval/` sekitar 49 KB.
Tidak ada secret, bobot, isi data, dependensi, atau lockfile yang ditambahkan ke
Git; belum ada commit pada sesi ini.

Antislop-code PASS: dua komentar baru menjelaskan kontrak token upstream dan
batas identifikasi keluarga model; tidak ada komentar dekoratif, narasi langkah,
atau cleanup di luar lingkup M6. Gate visual tidak berlaku karena UI tidak diubah.

**Acceptance criteria:**

- [ ] Dataset uji punya gold paper + gold chunk, dan tidak diubah setelah run pertama tanpa dicatat sebagai versi baru.
- [ ] Dataset memuat campuran lookup, comparison, synthesis, dan unanswerable (~10–15%), dengan jumlah per tipe dilaporkan.
- [ ] Pertanyaan unanswerable dinilai benar bila sistem menolak menjawab; klaim yang tetap muncul dihitung gagal.
- [x] ID model MiniCheck diverifikasi ke Hugging Face sebelum dipakai, bukan diasumsikan dari nama di config.
- [x] Metrik di `ARCHITECTURE.md` §9 dihitung otomatis dan ditulis ke `eval/results/<run_id>/` (agreement manusia null sampai label tersedia; perhitungannya diuji dengan fixture).
- [x] Laporan mencantumkan `run_id`, `config_hash`, versi model, seed, jumlah pertanyaan.
- [ ] Label manual 50–100 pasangan klaim-chunk tersedia dan Cohen's kappa dihitung.

**Implementasi awal M6:** verifier lokal memakai Transformers/PyTorch yang sudah
terpasang, tanpa dependensi baru atau perubahan lockfile/CUDA. ID
`lytang/MiniCheck-Flan-T5-Large` diperiksa langsung melalui API Hugging Face,
revision `96eafd01cee2d16cf81aaa2fb226b14f422a37b3`, metadata lisensi MIT.
Bobot sekitar 3,13 GB diunduh ke cache model. Adapter mengikuti format input dan
dua token label upstream, tetapi memeriksa pasangan utuh tanpa segmentasi atau
truncation. Batas default 512 token, CPU, threshold 0,5. Contoh upstream positif
dan negatif diuji nyata: skor 0,98059237 dan 0,00712132.

Runner `--stage citations` menghubungkan empat mode retrieval, generation, cache,
MiniCheck, serta sampel judge opsional. Batas generation dibagi ke seluruh
pertanyaan/mode, termasuk retry; judge memiliki batas batch sendiri. Tanpa
`--allow-api`, cache miss dicatat sebagai gagal tanpa request berbayar. Sampling
judge memakai qid/ordinal dan seed; keluarga provider berbeda diperiksa. Skema
`verification` yang sudah ditentukan di arsitektur diimplementasikan tanpa
mengubah kontrak. Hasil dan run lama tidak ditimpa. Klaim tanpa bukti dan klaim
unanswerable tetap dihitung; generation gagal tidak dianggap abstention. Dukungan
yang belum lengkap membuat metrik agregat null, dengan jumlah kegagalan eksplisit.

`--stage agreement --annotations <file>` menilai pasangan yang telah dilabeli
manusia, memvalidasi hash sumber/duplikasi/identitas anotator, dan menghitung
Cohen's kappa tanpa bobot. Tiga label dipertahankan; MiniCheck hanya menghasilkan
dua kelas. Tidak ada label manusia yang dibuat atau diisi oleh agent. Kappa
fixture pada test bukan hasil anotasi manusia nyata.

**Draf dan bahan anotasi:** `eval/questions.draft-v1.jsonl` berisi 30 kandidat
pertanyaan: 15 lookup, 7 comparison, 4 synthesis, dan 4 unanswerable (13,3%).
Gold ID/reference answer ditulis AI berdasarkan pembacaan chunk, belum ditinjau
manusia. SHA-256 `a6fc480fc37dd1e2d101030575f1a728f0e3b149b3e53f47b94dd3fda8f0c820`.
Seluruh ID divalidasi terhadap 21 chunk M3 dari satu paper, tanpa retrieval atau
generation untuk menyetel label draf. Synthesis hanya antarbagian satu paper,
sehingga kebutuhan lintas paper belum terpenuhi. Dataset final
`eval/questions.jsonl`/`gold_labels.jsonl` tidak dibuat atau diklaim tersedia.

Panduan ada di `eval/README.md`. File
`data/m6-smoke/local-verifier-v1/reference-annotations.jsonl` memuat 52 pasangan
tanpa label/prediksi verifier: 26 jawaban referensi draf, masing-masing dengan
chunk kandidat relevan dan distraktor. Ini bahan anotasi calon klaim, bukan
keluaran benchmark generation. Metadata/hash ada di `preparation.json` dalam
direktori yang sama. Pasangan dari keluaran sistem nyata juga diekspor oleh
runner ke `data/annotations/`; smoke test menghasilkan empat pasangan unik.
Pengulangan empat pasangan itu bukan anotasi independen baru. Kutipan penuh
disimpan hanya di `data/` yang diabaikan Git; hasil evaluasi publik tidak menyalin
Markdown/kutipan yang memuat chunk.

**Smoke test MiniCheck nyata pada respons DeepSeek yang sudah di-cache:** salinan
SQLite/indeks dari uji API M5 dibuat di `data/m6-smoke/local-verifier-v1/`.
Satu pertanyaan yang sama mengambil konteks melalui embedding CPU nyata dan
skor reranker yang sudah di-cache. Generator membaca respons DeepSeek Flash
yang benar-benar berasal dari API pada M5; nol request API baru, tanpa judge.
Keempat pasangan klaim–chunk mendapat label supported dari MiniCheck lokal.
Input T5 termasuk klaim/evidence berjumlah 500, 488, 501, dan 482 token, semuanya
di bawah batas 512. Ini hasil verifier, belum persetujuan manusia atas klaim.

| Run | Precision / recall / faithfulness MiniCheck | Recall@5/10/20 | MRR | Waktu alur |
|---|---|---|---|---|
| `2026-11-18T10:26:20Z_a8dbda` | 1,0 / 1,0 / 1,0 | 1,0 / 1,0 / 1,0 | 0,5 | 17,49 detik |
| `2026-11-18T10:27:40Z_6a576e` | 1,0 / 1,0 / 1,0 | 1,0 / 1,0 / 1,0 | 0,5 | 8,42 detik |

Run pertama menghitung empat pasangan baru; pengulangan pada proses baru memakai
empat cache hit verifier, nol pasangan baru, dan metrik identik. Kedua run memakai
satu cache hit LLM, nol token/request baru. Hallucinated citation rate 0,0;
abstention accuracy, agreement judge, dan kappa manusia null karena tidak ada
kontrol unanswerable/judge/label manusia pada smoke ini. Skor satu pertanyaan
tidak membuktikan kualitas benchmark 30 pertanyaan atau korpus penuh.

| Proses smoke M6 | Puncak working set | Puncak private commit | Puncak VRAM PyTorch |
|---|---|---|---|
| Retrieval CPU + LLM cache + empat inference MiniCheck baru | 4,35 GiB | 6,29 GiB | 0 byte |
| Pengulangan dengan cache verifier | 1,25 GiB | 3,07 GiB | 0 byte |

RAM memakai Windows process memory counters untuk seluruh umur proses Python,
termasuk pemuatan embedding/MiniCheck, bukan RAM model verifier saja. Skor
reranker sudah di-cache sehingga bobot reranker tidak dimuat pada smoke ini.
VRAM berasal dari allocator PyTorch; CUDA tidak diinisialisasi, bukan pengukuran
pemakaian GPU seluruh Windows. Waktu mencakup startup/model/retrieval, bukan
benchmark inference terisolasi. Tidak ada uji GPU atau perubahan sumber CUDA.

Laporan ada di `eval/results/<run_id>/`; config, skrip, hash, dan
`first-evidence.json`/`repeat-evidence.json` ada dalam direktori smoke. Hash
database/seluruh file indeks M3 dan uji API M5 tetap sama. Baris paper/chunk/FTS
pada salinan juga tetap sama; foreign key check bersih. Salinan mewarisi dua run,
dua answer, dan delapan claim M5. Setelah dua smoke M6: enam run (dua eval baru
dan dua generation baru), empat answer, 16 claim, delapan verification.

**Handoff berikutnya:** tinjau draf pertanyaan/ID/expected answer dan kontrol
unanswerable; perluas sumber arXiv berizin untuk sintesis lintas paper, memakai
database/index baru agar ID lama tetap utuh. Simpan perubahan gold sebagai versi
baru sebelum benchmark. Manusia perlu melabeli 50–100 pasangan sesuai panduan,
lalu jalankan agreement lokal. Setelah dataset disetujui, siapkan batch generation
DeepSeek dan sampel judge keluarga berbeda dengan batas request konkret sebelum
meminta izin run berbayar. Judge OpenAI belum diuji dan key tidak diperiksa pada
sesi ini. Gunakan Python `.venv` langsung; hindari `uv sync/run`.

### Pilot Jev melalui Surplus (2026-11-18)

Pengguna mengizinkan percobaan model keputusan untuk portofolio dan menyediakan
`SURPLUS_API_KEY`, `SURPLUS_API_URL`, serta `JEV_MODEL_ID` di `.env`. Pembahasan
awal menyebut Jev 1.13, tetapi nilai yang dipilih pengguna adalah `jev-1.14`;
eksperimen mengikuti `.env`, bukan mengganti model diam-diam. Catalog Surplus
melalui GET `/v1/models` berhasil diperiksa sebelum inference: model tersedia,
berfitur decisions/native_schema, dengan harga katalog input US$0,000000042 per
token dan output nol. Snapshot metadata tersimpan dalam artefak eksperimen.

**Implementasi:** adapter native `/v1/decisions` mengirim pasangan claim/evidence
sebagai state dan satu pertanyaan Choice tiga label. Cache/checksum, token usage,
model/endpoint/backend provenance, batas batch keras, serta `--allow-api` memakai
client cache M5. Backend jaringan yang diinjeksikan tetap wajib mempunyai izin
API; default cache-only tidak dapat dilewati. Tidak ada retry transport/format,
follow redirect, SDK/dependensi baru, atau perubahan default generator DeepSeek.
Endpoint dan bentuk probabilitas/confidence/model/usage divalidasi. Tidak ada
key di config, laporan, atau log.

Jev dapat dipilih sebagai judge opsional pada runner sitasi lewat
`verification.judge_provider: surplus`. Rationale tetap NULL karena Jev tidak
menghasilkan alasan naratif; score adalah probabilitas supported. Kolom ini
sudah nullable pada skema lama. Tiga label, distribusi probabilitas, confidence,
model versi lengkap, dan HTTP latency dipertahankan pada laporan. Tidak ada
perubahan skema SQLite atau format sitasi. Judge generatif default dan gold
manusia tetap bagian protokol M6; pilot Jev tidak menutup milestone itu.

**Sampel dibekukan sebelum inference:** seed 42 memilih 12 dari 52 pasangan
referensi draf. Nomor baris sumber: `[41, 8, 2, 48, 18, 16, 15, 9, 7, 35, 6, 38]`.
Selection, hash input/korpus/config, code version, versi library, dan identitas
kedua model ada dalam manifest run. Label manusia/target tidak dipakai untuk
memilih sampel atau menghitung hasil. Pasangan berasal dari jawaban referensi
draf AI, bukan jawaban generation benchmark. Database, seluruh file indeks
M3/M5/M6, draf pertanyaan, dan berkas kandidat 52 pasangan tetap ber-hash sama.

| Run | Jev selesai | MiniCheck selesai | Agreement pada pasangan comparable | Request Jev baru | Waktu tahap comparison |
|---|---|---|---|---|---|
| `2026-11-18T11:50:46Z_ad072b` | 12/12 | 10/12 | 10/10 | 12 | 19,98 detik |
| `2026-11-18T11:52:32Z_764cf8` | 12/12 | 10/12 | 10/10 | 0 | 4,39 detik |

Server melaporkan `typesafe/jev-1.14-20261014` pada semua request. Jev memberi
empat label supported, tujuh not_supported, dan satu partially_supported.
MiniCheck memberi tiga supported dan tujuh not_supported; dua pasangan tersisa
ditolak karena panjang T5 518 dan 526 token, di atas batas 512, tanpa truncation.
Kedua run berstatus **incomplete** untuk perbandingan penuh karena cakupan
MiniCheck 10/12. Agreement/kappa antar-model adalah 1,0 pada 10 pasangan comparable;
accuracy/kappa terhadap manusia belum tersedia. Tujuh pasangan negatif memakai
chunk abstrak yang sama, sehingga sampel belum mencerminkan keragaman kasus sulit.
Tidak ada ambang confidence yang dikalibrasi atau klaim Jev lebih akurat.

Run pertama tepat 12 POST, tanpa retry, usage diketahui untuk seluruhnya:
9.864 input token dan 514 output token yang dilaporkan provider. Median waktu
HTTP 0,677 detik per request, termasuk jaringan/pembacaan respons; bukan latency
inference model terisolasi. Estimasi input berdasarkan snapshot harga katalog
adalah US$0,000414288; output berharga nol menurut katalog. Ini bukan pembacaan
tagihan/saldo atau bukti harga seller aktual setelah routing. Tidak ada request
generation DeepSeek atau judge generatif OpenAI pada pilot ini.

Pengulangan pada proses baru memakai 12 cache hit Jev, nol request/token baru,
10 cache hit MiniCheck, serta menghasilkan selection, label, probabilitas, dan
metrik yang sama. Dua input terlalu panjang diperiksa ulang dan ditolak sebelum
forward pass; wrapper tetap memuat tokenizer/model untuk pemeriksaan batas.
Memori cache bukan bukti bahwa model tidak dimuat. Waktu comparison mencakup
HTTP/model lokal/cache, tetapi tidak seluruh startup impor/config CLI.

| Proses pilot Jev | Puncak working set | Puncak private commit | Puncak VRAM PyTorch |
|---|---|---|---|
| 12 request Jev + MiniCheck CPU | 3,79 GiB | 5,90 GiB | 0 byte |
| Pengulangan cache, dua input ditolak ulang | 0,86 GiB | 5,50 GiB | 0 byte |

RAM adalah Windows process memory counters untuk umur proses Python lokal,
bukan RAM Jev di server. Working set dan private commit mengukur hal berbeda;
pada pengulangan, bobot model dimuat tetapi tidak dipakai forward pada dua
input panjang. VRAM adalah allocator PyTorch proses ini, CUDA tidak diinisialisasi;
bukan pemakaian GPU seluruh Windows. Tidak ada uji GPU atau sinkronisasi CUDA.

Laporan publik berada di `eval/results/<run_id>/`, termasuk selection JSONL,
metrics, per-pair, dan report. Artefak lokal di
`data/jev-smoke/surplus-jev-v1/`: script/config, catalog, first/repeat evidence,
diagnostik panjang input, serta `human-review.md`/`human-review.jsonl` tanpa
prediksi model. Lembar review menampilkan lima chunk unik sekali per kelompok
untuk 12 pasangan; label manusia masih kosong. Pemeriksaan artefak menemukan
nol key Surplus dan nol salinan chunk lengkap pada hasil publik. Tidak ada hasil
lama yang ditimpa atau dataset/gold yang dimodifikasi untuk memperbaiki skor.

**Verifikasi repo setelah Jev:** 369 test lulus melalui Python `.venv` langsung;
Ruff lint/format bersih. Sebanyak 41 test baru Jev memakai mock/HTTP MockTransport:
request native, parsing tiga label/probabilitas/confidence, key tanpa bocor,
penolakan redirect/error tanpa retry, batas batch, cache/offline replay, model
version, factory/persistensi skema lama, selection deterministik, coverage
input panjang, dan penghentian eksperimen pada kegagalan provider. Test otomatis
tidak melakukan request API berbayar. Antislop-code PASS: tidak ada komentar
dekoratif atau cleanup di luar lingkup. Belum ada commit pada sesi ini.

**Handoff Jev:** gunakan panduan CLI di USAGE.md dan bahan review di
`data/jev-smoke/surplus-jev-v1/human-review.md` untuk memperoleh label manusia
asli. Periksa kasus partial dan bukti yang tidak memadai sebagai bagian sampel
yang dibekukan, tanpa mengganti label agar cocok dengan Jev/MiniCheck. Jangan
menyamakan agreement dua model dengan accuracy. Perluasan korpus lintas paper,
gold set manual 30–50 pertanyaan, 50–100 label manusia, dan benchmark final M6
tetap menunggu. Batch berbayar tambahan memerlukan lingkup/batas baru yang jelas;
jangan mengulang 12 request hanya untuk mengejar hasil lebih baik.

---

### Label manusia pilot Jev (2026-11-18)

Pengguna mengoreksi lima penilaian kelompok dari P menjadi S, lalu secara
eksplisit mengonfirmasi bahwa S berlaku untuk seluruh 12 pasangan klaim–chunk.
Label disimpan sebagai versi baru pada
`data/jev-smoke/surplus-jev-v1/human-labels-v1.jsonl`, anotator `chat-user`.
Alasan asli per kelompok, koreksi, konfirmasi cakupan, dan hash sumber
dipertahankan. Bahan review awal tetap null; feedback, prediksi, dan database
tidak ditimpa. Label ini merupakan anotasi manusia pilot yang menunggu
adjudikasi, belum dipromosikan menjadi gold final.

Perbandingan lokal menggunakan hasil tersimpan, tanpa API atau inference baru:
`eval/results/2026-11-18T12-25-28Z_4cf0c3/`. Jev cocok dengan manusia pada 4/12
pasangan (33,3%; coverage 12/12). MiniCheck cocok pada 3/10 pasangan yang
berhasil dinilai (30%; coverage 10/12); dua input panjang tetap unverified.
Kappa tanpa bobot keduanya 0,0 karena seluruh label manusia supported dan
agreement teramati sama dengan agreement peluang pada distribusi satu kelas.
Nilai ini tidak cukup untuk menilai kualitas umum atau specificity model.

Delapan pasangan berbeda dengan Jev, termasuk tujuh pasangan dengan chunk
abstrak yang sama. Siapkan tinjauan per klaim, tanpa mengganti label manusia
agar mengikuti model. Anotasi berasal dari satu orang, lima kelompok chunk,
dan satu paper; hasil agregat model telah diketahui sebelum konfirmasi, sehingga
bukan studi sepenuhnya blind. Target 50–100 label dan benchmark M6 tetap belum
terpenuhi. Lembar adjudikasi lokal: `human-adjudication-v1.md` dalam direktori
pilot, hanya memuat pasangan yang berbeda, tanpa menentukan label penggantinya.

Skrip lokal `score-human-v1.py` memvalidasi 12 label terhadap hash chunk kanonis,
kesamaan pasangan dengan run sumber, hitungan agreement/kappa, dan keutuhan
berkas sumber. RAM puncak proses scoring 25,52 MiB working set / 17,07 MiB
private commit; VRAM allocator PyTorch 0 byte, CUDA tidak diinisialisasi.
Ini memori scoring hasil tersimpan, bukan pemuatan model atau memori server Jev.

### Tinjauan individual pilot Jev (2026-11-18)

Pengguna mengisi delapan item pada `human-adjudication-v1.md`, mengubah tujuh
label. Revisi dan alasan disimpan apa adanya pada `human-labels-v2.jsonl` dalam
direktori pilot; v1, lembar yang diisi, prediksi, dan database tetap utuh.
Distribusi 12 pasangan sekarang lima supported, tiga partially_supported,
empat not_supported. Tidak ada label yang diubah agent agar cocok dengan model.

Run lokal `eval/results/2026-11-18T12-38-58Z_a86400/` memakai prediksi lama:
Jev cocok 8/12 (66,7%; kappa 0,483871), MiniCheck 7/10 (70%; kappa 0,523810),
dua input MiniCheck tetap unverified. Ini statistik provisional terhadap label
yang dimasukkan pengguna, bukan validasi independen: item tinjauan dipilih dari
ketidaksepakatan model, dan hasil agregat telah diungkap sebelum revisi.

Tiga label P (`jev-pilot-row-08`, `jev-pilot-row-02`, `jev-pilot-row-18`) masih
memerlukan penjelasan bagian klaim mana yang didukung chunk. Alasan pengguna
membahas panjang jawaban atau kebutuhan konteks tambahan; hal itu tidak sendiri
menentukan dukungan faktual. Posisi teks sebagai abstrak atau ketiadaan hasil
empiris juga tidak sendiri menentukan label. Label tetap dipertahankan dan
ditandai `protocol_review_required`; tidak dipromosikan ke gold final. Perjelas
rubrik dengan satu contoh per klaim sebelum memperbesar batch anotasi.

Skrip lokal `score-human-v2.py` memvalidasi label/hash dengan loader proyek,
jumlah revisi, hasil agreement/kappa, serta keutuhan input. Tidak ada API atau
inference baru. RAM scoring puncak 25,88 MiB working set / 17,46 MiB private
commit; VRAM allocator PyTorch 0 byte, CUDA tidak diinisialisasi. Target manual
50–100 pasangan dan benchmark M6 tetap belum terpenuhi.

### Koreksi rubrik oleh AI (2026-11-18)

Pengguna meminta agent memperbaiki anotasi yang masih bermasalah. Agent meninjau
delapan pasangan dalam lembar adjudikasi berdasarkan teks chunk kanonis.
Hasil disimpan terpisah sebagai `ai-adjudication-v1.jsonl` dan
`ai-adjudication-v1.md` dalam direktori pilot lokal; manifest mencatat hash
input/output dan penggunaan resource. Label manusia v1/v2, lembar yang diisi,
prediksi model, dan database tetap ber-hash sama.

Empat usulan berbeda dari label manusia v2: row-08, row-02, row-18 dari P
menjadi N karena detail klaim tidak tersedia dalam chunk abstrak; row-35 dari S
menjadi P karena hanya klausa reference-based yang didukung. Klausa
reference-free tanpa gold answer tidak dijelaskan dalam chunk itu. Empat
pasangan lainnya tetap N dengan alasan yang diperjelas. Ini penilaian dukungan
klaim terhadap satu chunk, bukan penilaian panjang atau kualitas jawaban umum.

Artefak memakai `suggested_label` dan `reviewer_type: ai`, tanpa field label
manual/annotator yang dapat langsung diterima loader manusia. Jumlah label
manusia baru nol; tidak ada promosi ke gold atau perhitungan ulang agreement
manusia menggunakan koreksi AI. Prediksi sebelumnya telah terlihat sehingga
tinjauan ini tidak blind. Target manual M6 tetap terbuka.

Tidak ada API tambahan atau inference model lokal; penilaian AI dilakukan oleh
Codex dalam percakapan ini. RAM proses penyimpanan/validasi puncak 17,27 MiB
working set / 9,00 MiB private commit; VRAM allocator PyTorch 0 byte, CUDA tidak
diinisialisasi. Ini resource skrip penyimpanan, bukan memori inference Codex.

## M7 — UI dan dokumentasi

**Deliverable:** Streamlit app, README final, demo.

**Acceptance criteria:**

- [ ] UI menampilkan jawaban per klaim, kutipan chunk, nomor halaman, dan penanda klaim tanpa bukti.
- [ ] Tema UI mengikuti `DESIGN.md` (token yang tidak masuk akal diperbaiki dan dicatat di sana).
- [ ] README memperkenalkan proyek dan menautkan panduan penggunaan, arsitektur/keputusan desain, serta laporan evaluasi dan analisis kegagalan di `eval/results/<run_id>/`.
- [ ] Tidak ada secret, PDF, atau isi `data/` di repo.

---

## Backlog (v2, jangan dikerjakan sebelum M7)

- Tabel perbandingan metode antar paper.
- Evidence map.
- Dukungan multibahasa (`bge-m3`).
- GROBID sebagai parser utama untuk referensi dan section yang lebih akurat.
