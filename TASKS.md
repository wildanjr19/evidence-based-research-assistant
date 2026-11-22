# Riwayat MVP

M0-M7 selesai pada 2026-11-18 hingga 2026-11-19. Dokumen ini merangkum hasil
benchmark historis; pekerjaan korpus/UI terbaru ada di [TASKS-SKRIPSI.md](TASKS-SKRIPSI.md).
Kontrak: [ARCHITECTURE.md](ARCHITECTURE.md). Operasi: [USAGE.md](USAGE.md).

## Milestone selesai

| Tahap | Hasil | Verifikasi saat penutupan |
|---|---|---|
| M0 Fondasi | Config tervalidasi, ID, struktur repo, ignore secret/data | 93 test; Ruff bersih |
| M1 Ingestion | Metadata arXiv, lisensi/hash PDF, cache/idempotensi, budget kandidat | 130 test; satu PDF nyata CC-BY-4.0 |
| M2 Parsing/chunk | PyMuPDF, halaman/section, chunk deterministik dan laporan short-drop | 165 test; PDF 16 halaman/20 chunk; replay identik |
| M3 Indexing | BGE pinned, LanceDB dan SQLite FTS5, cache dan larangan truncation | 186 test; 21 chunk/vektor/FTS nyata CPU |
| M4 Retrieval | BM25, dense, RRF, reranker; Recall@k/MRR dan run terpisah | 219 test; reranker CPU nyata dan replay |
| M5 Generation | Grounding, JSON klaim, validasi sitasi, cache/budget/usage, loader `.env` | 283 test; 289 setelah mode DeepSeek non-thinking |
| M6 Evaluasi | Benchmark empat paper, metrik sitasi, anotasi dan judge sampel | 380 test; batch dan replay selesai |
| M7 UI | Streamlit, demo tersimpan, kutipan/halaman/lisensi, query pada backup DB | 397 test; 404 setelah izin API opsional; Ruff bersih |

Angka test adalah bukti historis, bukan hasil pengujian sesi dokumentasi.
Test otomatis memakai mock/fixture tanpa API berbayar. Semua tahap mencatat
config/hash/model/revision/seed, artefak baru dan batas hasil.

## M0-M5: bukti dan batas

- Metadata baru masuk SQL setelah PDF tersedia karena skema mewajibkan hash.
  Identitas arXiv pertama: `arxiv:2605.14488v1`; sumber/lisensi diperiksa.
- M2 `lexical-v1` bukan tokenizer model. M3 memakai snapshot baru 380 token
  leksikal agar maksimum BGE 491/512; chunk M2 lama 514 token tetap disimpan.
- BGE CPU awal: 21 embedding/8.758 token, 20,38 detik; replay 21 cache hit,
  nol encoding baru. CUDA tensor kemudian lulus pada RTX 3060 Ti 8 GB dengan
  Torch `2.15.0+cu132`; ini belum bukti inference embedding GPU.
- Smoke M4 satu paper/lima pertanyaan: BM25 Recall@5 0,8/MRR 0,7250;
  dense 0,8/0,5952; hybrid 1,0/0,7067. Rerank tetap Recall@5 1,0 tetapi
  MRR turun ke 0,5667. Sampel ini tidak menentukan mode terbaik umum.
- Reranker CPU menghitung 105 pasangan; replay memakai seluruh cache dengan
  ranking/skor identik. Database dan indeks sumber tetap.
- M5 mock menghasilkan klaim bersitasi dan unsupported; penyimpanan dan replay
  identik pada salinan DB. Provider nyata diuji terpisah, bukan bagian test.
- Uji DeepSeek nyata 2026-11-18: satu dari maksimal dua request, 3.921 input/
  208 output token, empat klaim/empat sitasi valid, tanpa retry. Replay nol API.
  Estimasi historis US$0,00071295 off-peak/US$0,0014259 peak, bukan tagihan.
  Ini uji integrasi satu pertanyaan, bukan benchmark semantik.

| Bukti lokal | Isi |
|---|---|
| `data/m1-smoke/`, `data/m2-smoke-v2/` | Admission/parser nyata; versi awal tetap |
| `data/m3-smoke/` | Indeks CPU dan cache replay |
| `data/m4-validation/2026-11-18T06-02-41Z_be478e/` | Lima query sintetis/30 chunk, model mock |
| `data/m4-smoke/2026-11-18T06-00-30Z_4cfc6b/` | BM25/dense/hybrid CPU |
| `data/m4-reranker-smoke/2026-11-18T07-06-30Z_b88c51/` | Model, hash, ranking dan replay CPU |
| `data/m5-smoke/2026-11-18T08-20-39Z_028e06/` | Retrieval nyata + generator fixture |
| `data/deepseek-smoke/2026-11-18T09-07-49Z_733dac/` | Request nyata, usage dan replay |

Torch CUDA dipasang manual; lock utama belum selaras. Jangan `uv sync`/`uv run`
pada environment ini. Test GPU inference memerlukan cache baru.

## M6: anotasi dan pilot verifier

Draf lama: 30 pertanyaan satu paper, 52 pasangan klaim acuan/distraktor buatan AI.
Bukan klaim generation benchmark final. Draf `eval/questions.draft-v1.jsonl`
dan semua versi label tetap dipertahankan.

Pilot JEV memakai 12 request yang diizinkan, model eksplisit `jev-1.14`
(respons `typesafe/jev-1.14-20261014`). MiniCheck menilai 10/12; input 518/526
melebihi batas 512 dan tetap unverified. Agreement antar-model 10/10 tidak
membuktikan akurasi. Replay memakai cache tanpa request baru.

| Revisi manusia pilot | Hasil terhadap prediksi tersimpan | Batas |
|---|---|---|
| v1: semua 12 supported | JEV 4/12; MiniCheck 3/10; kappa 0 | Penilaian kelompok, hasil agregat diketahui |
| v2: 5 S/3 P/4 N | JEV 8/12, kappa 0,483871; MiniCheck 7/10, 0,523810 | Tinjauan dipilih dari konflik, rubrik partial perlu diperjelas |
| v3: 4 S/1 P/7 N | JEV 12/12; MiniCheck 10/10; kappa 1 | Empat revisi N/N/N/P setelah usulan AI terlihat |

Usulan AI tetap terpisah dari label manusia; v3 bukan validasi independen.
Empat revisi tidak menambah pasangan unik. Versi lokal ada di
`data/jev-smoke/surplus-jev-v1/`; laporan tiap versi tersedia di [indeks evaluasi](eval/README.md).

Batch 1-4 menambah 40 pasangan, sehingga total 52 (22 S/3 P/27 N); 13 alasan
kosong tetap null. Pada 40 pasangan baru MiniCheck cocok 30/35 (85,7%), kappa
0,710265, coverage 35/40. Gabungan deskriptif cocok 40/45 (88,9%), kappa 0,767322,
coverage 45/52; tujuh input panjang tetap unverified. Partial tidak digabung
menjadi supported. Seluruh cohort masih satu paper, bukan gold klaim generation baru.
Label kumulatif: `data/annotations/batches02-04-2026-11-19T00-31-04Z_673846/human-labels.jsonl`.
[Laporan cohort](eval/results/2026-11-19T00-31-04Z_673846/report.md) dan
[analisis perbedaan](eval/results/2026-11-19T00-31-04Z_673846/failure-analysis.md)
memisahkan catatan AI dari label manusia.

## M6: benchmark final, 2026-11-19

Korpus terpisah: empat paper CC-BY-4.0 (Deepchecks, Chemistry, LegalBench-RAG,
MIRAGE), 66 halaman, 236 chunk/vektor/FTS. Dataset `eval/questions.jsonl`
berisi 12 lookup, 8 comparison, 6 synthesis lintas paper dan 4 unanswerable.
Draf AI dibekukan sebelum retrieval dan disetujui pengguna setelah retrieval awal;
provenance ada di `eval/questions.reviewed-v1.manifest.json`.

Empat mode retrieval dan replay selesai; [laporan kesiapan](eval/m6-multipaper-readiness-20261119.md)
memuat skor/ID run. Mode sitasi hybrid+rerank ditetapkan sebelum hasil.

Batch diizinkan maksimum 60 DeepSeek/50 judge Surplus, output 2.048 token/request,
seed 42, sampel judge 25%, tanpa retry transport. Otorisasi/config/receipt di
`data/m6-multipaper/20261119T004114Z/`. Batch selesai; sisa jatah bukan izin baru.

| Hasil final | Nilai |
|---|---:|
| Pertanyaan/klaim/pasangan sitasi | 30 / 101 / 109 |
| MiniCheck supported / not_supported | 94 / 15 |
| Precision sitasi | 86,24% |
| Recall/faithfulness implementasi | 88,12% |
| Hallucinated citation rate | 0% |
| Abstention ketat | 3/4 |
| Agreement MiniCheck/GPT | 22/28 (78,57%), kappa 0 |

Tidak ada generation gagal, overlength atau unverified. Recall di sini adalah
proporsi klaim dengan sedikitnya satu sitasi supported, bukan seluruh fakta acuan.
`multi029` menolak lewat klaim unsupported; kontrak `claims: []` tetap gagal.
Semua 28 label GPT supported, sehingga interpretasi agreement terbatas.
Enam konflik diaudit AI tanpa mengubah label/skor.

Aktual: 30 request DeepSeek (87.561 input/5.865 output) dan 28 Surplus
(10.521/1.565), tanpa retry/usage hilang. Estimasi historis US$0,033763 memakai
harga judge pengguna dan DeepSeek peak cache-miss; bukan tagihan provider.
Durasi 262,66 detik; working set ~4,35 GiB/private commit 6,35 GiB, CPU.

[Laporan final](eval/results/2026-11-19T01-25-11Z_7492c6/m6-summary.md),
[analisis kegagalan](eval/results/2026-11-19T01-25-11Z_7492c6/failure-analysis.md), dan
[replay](eval/results/2026-11-19T01-31-11Z_75bb36/report.md) tetap utuh.
Replay memakai 30 cache generation/28 judge/109 verifier; ranking, klaim,
label/skor/rationale dan metrik identik, nol API/inference verifier baru.
Label manusia 52 pasangan tetap cohort terpisah; accuracy manusia generation baru null.

## M7 dan kelanjutan

Streamlit menyediakan demo M6 30 jawaban/101 klaim tanpa memuat model; hash korpus,
pertanyaan dan jawaban dicocokkan ke SQLite. Sitasi memakai metadata kanonis;
klaim/kutipan dirender sebagai teks. Query menulis backup DB dan run baru, API
cache-first dengan izin eksplisit per submit. Tema dan keputusan visual di [DESIGN.md](DESIGN.md).

Korpus skripsi, Docling, UI KB penuh dan RAGAS opsional kemudian dikembangkan
terpisah; seluruh status dan bukti lanjutan diringkas di [TASKS-SKRIPSI.md](TASKS-SKRIPSI.md).
Target awal 100-500 paper bukan syarat korpus pengguna. Backlog production,
GROBID, evidence map, fine-tuning dan multi-user tetap ditunda tanpa kebutuhan/izin baru.
