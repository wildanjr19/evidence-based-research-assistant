# Status korpus referensi skripsi

Status produk terakhir: 2026-11-22. Dokumentasi diringkas 2026-11-22.
Tujuan: menjawab dari referensi pengguna dengan sitasi hingga halaman PDF/kutipan.
Riwayat MVP terpisah di [TASKS.md](TASKS.md); kontrak di [ARCHITECTURE.md](ARCHITECTURE.md),
perintah di [USAGE.md](USAGE.md), dan persiapan korpus di [KB-PREPARATION.md](KB-PREPARATION.md).

## Status aktif dan agenda

- KB Docling penuh: 41 PDF/746 halaman terdaftar, 40 searchable, 2.514 chunk/vektor/FTS;
  100 tabel searchable/208 ditahan. Parasuraman sudah OCR tetapi nol chunk lolos;
  tiga TXT belum berpeta halaman.
- Bibliografi Mendeley sumber: 83 entri/82 referensi kanonis. Salinan turunan KB:
  84 entri/83 referensi setelah Szeghalmy; sumber asli tidak diubah.
- UI default `configs/skripsi-local.yaml`: Tanya korpus, delapan demo KB penuh,
  sitasi/preview PDF, DeepSeek Flash non-thinking. Jawaban tampil dahulu;
  RAGAS otomatis per card, diagnostik MiniCheck opsional. Helper refinement belum produksi.
- API UI aktif otomatis/cache-first sesuai instruksi 2026-11-22, dengan batas
  dua request generator/submit dan lima evaluator/card; CLI default cache-only.
  Seluruh batch berbayar historis sudah selesai; sisa jatah bukan izin baru.
- Verifikasi kode terakhir: 598 test utama lulus/1 modul RAGAS skipped,
  15 test adapter RAGAS isolated lulus, Ruff lint/format dan diff check bersih.
  Suite parser isolated tidak diulang pada perubahan UI terakhir.

Agenda berikutnya: rapikan UI berdasarkan kebutuhan penggunaan. Masih terbuka:
OCR Parasuraman, halaman TXT, kalibrasi gate, evaluasi bahasa/pertanyaan lebih luas,
dan akurasi manusia. Audit kecil S5 sudah ditutup; anotasi manusia baru bukan
prasyarat penggunaan RAG. Tidak ada verifier/transformasi baru dipromosikan.

## Keputusan yang tetap berlaku

Grounding hanya dari chunk terambil; tiap klaim harus mempunyai sitasi valid atau
label tanpa bukti. SQL/ID/sitasi tetap. Setiap eksperimen memakai snapshot/run baru,
config/hash/model/revision/seed dan provenance; label tidak berpindah hanya karena ID sama.
PDF/full text/abstrak/indeks/cache tetap lokal di `data/`, tidak di-commit.

Instruksi 2026-11-20 mengizinkan semua PDF pengguna diproses lokal tanpa menunggu
DOI/lisensi. Manifest `user_local_collection` dan label unverified wajib; gate
kualitas tetap. Ini menggantikan pembatas admission lokal tahap awal, bukan syarat
downloader. Jangan mengunduh PDF tambahan, mereset ledger/marker atau mengulang
batch paid. Dependensi/sumber baru dan proses lama mengikuti persetujuan AGENTS.md.

## S0-S4: bibliografi, pilot dan UI, 2026-11-19

| Tahap | Hasil | Bukti lokal |
|---|---|---|
| S0 Scope | Semua entri kandidat audit; pertanyaan ID/EN; jenis BibTeX tidak sendiri menentukan kelayakan | Scope awal dan aturan kini dirangkum di OVERVIEW/AGENTS |
| S1 Impor | 83 entri menjadi 82 referensi; Rahmatia2025 duplikat dipetakan, 21 tanpa DOI, nol blok gagal/konflik | `data/skripsi/references/2026-11-19T06-25-06Z_e88eb2/`, replay `2026-11-19T06-35-57Z_826ae9/` |
| S2 Unduhan | Lima PDF/66 halaman: Yulianti2024, Koto2021, Scaria2024, Wilie2020, Lu2025 | `data/skripsi/downloads/2026-11-19T06-53-52Z_57a5ae/` |
| S3 KB PyMuPDF | 310 chunk/vektor/FTS; 394 token leksikal short-drop; maksimum BGE 384/512 | `data/skripsi/pilot-v1/`, config `configs/skripsi-pilot.yaml` |
| S4 Streamlit | Citation key/judul/halaman/kutipan, alias berhash, query pada backup DB | Source UI dan `tests/test_ui.py` |

`bibtexparser==2.1.0` dan `pylatexenc==2.11` disetujui saat S1. Impor/replay
identik tanpa mengubah BibTeX asli. Source `.bib` SHA-256:
`744baba0ff7cf357397fbec8fa000ddc130cead2a0faa56c612de57ef3324a11`.

S2 diizinkan maksimal lima PDF/30 HTTP request termasuk redirect/gagal, tanpa API
LLM. Aktual 26/30 request dan seluruh lima slot PDF; ledger
`data/skripsi/download-budget.json` tidak boleh direset. Lisensi Yulianti CC-BY-SA-4.0,
empat lainnya CC-BY-4.0; identitas otomatis, bukan audit seluruh isi/penulis.
Status 82 referensi: 5 ready, 1 failed (Setiawan HTML penangguhan), 2 manual match
(Koto2020/Rainio host di luar allowlist), 74 belum dicoba. Belum dicoba bukan tidak tersedia.

S3 CPU nyata menghitung 310 embedding lalu replay nol encoding baru; seluruh
SQL/vektor/FTS identik. Spot visual AI satu halaman/paper menemukan tabel rata,
section/glyph/header bermasalah. Smoke 12 pertanyaan AI: target top-5 Inggris
BM25/dense 6/6; Indonesia BM25 5/6, dense 6/6. Ini bukan gold manusia atau
bukti model Inggris memadai untuk seluruh bahasa. Test penutupan S1/S2/S3:
426/459/468 lulus; Ruff bersih. Benchmark M6 dan label lama tetap.

## S5: RAGAS dan keputusan verifier, 2026-11-19

RAGAS 0.4.4 dipasang isolated (`data/skripsi/s5-ragas/.venv`, lock di `eval/`).
Draf AI: 20 pertanyaan (15 lookup/2 comparison/3 unanswerable, tanpa synthesis),
`data/skripsi/s5-ragas/drafts/2026-11-19T08-17-12Z_87a27c/`.
Dataset tetap `ai_draft_unreviewed`, bukan gold manusia.

Audit pengguna: sembilan acuan awal diterima; 018 dinilai insufficient karena
hanya abstract, lalu revisi dengan empat chunk empiris diterima. Audit kecil
ditutup pada `data/skripsi/s5-ragas/reviews/2026-11-19T09-51-25Z_b9f906/`.
Sepuluh acuan di luar sampel belum ditinjau. Revisi 018 tetap terpisah dari
dataset/acuan/skor lama; audit ini bukan label klaim generation.

| Batch berizin | Aktual request | Hasil |
|---|---|---|
| Pilot 4: maks. 8 DeepSeek/12 GPT | 4 DeepSeek, 11 GPT | Faithfulness 0,8056 (4); context recall 0,8333 (3); abstention 0/1 |
| Lanjutan 16: maks. 32 DeepSeek/46 GPT RAGAS | 16 DeepSeek, 42 GPT RAGAS | Faithfulness 0,985714 (14); recall 1,0 (14); abstention 2/2 |
| Verifier 12 pasangan: maks. 12 JEV/12 GPT | 12 JEV, 12 GPT | Coverage ketiga model 12/12 |

Gabungan 20: faithfulness 0,945679 (18/18 eligible), context recall 0,970588
(17/17), abstention 2/3; nol generation gagal. Dua jawaban kosong tidak mendapat
faithfulness; recall hanya answerable. Pilot unanswerable menolak lewat klaim
unsupported sehingga tetap gagal kontrak nol klaim; keluaran/skor tidak dinormalisasi.

Pada 12 pasangan beku: MiniCheck 5 S/7 N, JEV 8 S/4 P, GPT 11 S/1 P.
Agreement JEV/GPT 9/12 (kappa 0,307692), MiniCheck/JEV 5/12 (0,192308),
MiniCheck/GPT 5/12 (0,056180). Partial tetap kelas tersendiri. Keputusan saat itu:
JEV belum menggantikan MiniCheck; agreement tidak mengukur akurasi manusia.
RAGAS dapat kehilangan pengecualian/atribusi saat dekomposisi; skor mentah dipertahankan.

Pilot memakai DeepSeek 15.414 input/1.909 output dan GPT 26.240/2.733 token.
Lanjutan: DeepSeek 59.523/6.069; GPT RAGAS 100.569/9.848; GPT pasangan
4.309/618; JEV 8.401/516. Total lanjutan 82 request, GPT 54/58 termasuk pasangan.
Biaya gateway unknown. Batas chat 2.048 output/request, prompt judge 65.536 byte,
tanpa retry jaringan/judge. Semua batch selesai dan direplay identik tanpa API.

Bukti: `data/skripsi/s5-ragas/continuation-20261119T095905Z/` memuat plan,
authorization/marker/receipt, verifier-analysis dan combined-summary. Generation
`ragas-inputs-2026-11-19T11-34-01Z_2b0890` dan score
`ragas-scores-2026-11-19T11-35-01Z_16f94a` berada di
`data/skripsi/pilot-v1/reports/evaluation/`; pilot awal juga di sana.
Verifikasi saat penutupan: 489 test utama/1 skipped dan 21 test RAGAS isolated; Ruff bersih.

## S6: Docling dan pembangunan KB, 2026-11-19 sampai 2026-11-20

Environment Docling 2.151.1 isolated dengan Heron/TableFormer accurate/EasyOCR id/en,
CUDA batch satu, model pinned. Pilot tiga halaman native + kontrol raster 200 dpi
berhasil 6/6; peak GPU keseluruhan teramati 6.718 MiB (polling, bukan jaminan peak).
Salah gabung IndoLEM/SmSA dan OCR Rest14/Rest15 menunjukkan angka benar belum
cukup bila relasi baris salah. Koreksi probe Scaria 90.10 menjadi 92.10 disimpan
sebagai `samples-v2.json`; laporan/probe v1 tetap. Ini spot AI, bukan gold manusia.
Bukti: `data/skripsi/docling-pilot/summary.md` dan runs di folder yang sama.

Adapter/gate/chunk Docling tersedia: halaman asli, pembanding native/geometri,
header/caption/konteks tabel dan batas tokenizer. Tabel/OCR ambigu ditahan sebelum
SQL/index. Tidak wajib koreksi manual seluruh paper. Kasus punctuation-only,
header bertingkat, rowspan, row-section, escape sel dan band baris diberi test.
Kebijakan lengkap ada di KB-PREPARATION/ARCHITECTURE.

| Snapshot berurutan | Hasil | Lokasi di `data/skripsi/` |
|---|---|---|
| Tiga PDF penuh awal | 41 halaman/111 chunk; 19 tabel searchable/36 held | `docling-full/2026-11-19T16-58-24Z_2de8bc/` |
| Audit adapter lanjutan | 131 chunk; 32 tabel searchable/23 held | `docling-table-review/2026-11-19T17-16-57Z_47557e/full/2026-11-19T17-24-19Z_728589/` |
| Inventaris pengguna | 41 PDF + 3 TXT/746 halaman; hash/manifest cocok, tanpa duplikat byte | `local-inventory/2026-11-20T00-23-38Z_b7dd4c/` |
| Pilot Aufar/Dewi/Koto2020 | 34 halaman/115 chunk; 9 tabel searchable/11 held | `local-pilot/2026-11-20T00-35-31Z_6fb4ad/` |
| Refinement narasi | 118 chunk; dua narasi overlength pulih, tabel tetap | `pilot-refinement/2026-11-20T00-54-04Z_721c6f/` |
| KB tahap 1 | 17 PDF/277 halaman/903 chunk; 44 tabel searchable/100 held | `kb-build/2026-11-20T01-06-05Z_f81029/` |
| KB tahap 2 | 18 PDF/293 halaman/974 chunk; 48 tabel searchable/104 held | `kb-expansion/2026-11-20T01-33-36Z_3f61ac/` |
| Koleksi lokal penuh | 41 PDF/746 halaman; 40 searchable/2.514 chunk; 100 tabel searchable/208 held | `kb-local-all/2026-11-20T01-59-17Z_c95c3b/` |

Audit adapter memulihkan 17 tabel tetapi menahan empat prompt Scaria karena glyph
apostrophe native rusak. Uji enam halaman `do_cell_matching`: true lolos 16/21,
false 0/21; default true dipertahankan tanpa voting/per-table switching. Serialisasi
Pydantic diperbaiki agar opsi subclass lengkap, laporan lama tetap.

Pilot native Indonesia diuji terbatas. Gate baris diperketat setelah tabel Cleaning
Aufar salah gabung; dua panel Koto ikut ditahan konservatif. Enam smoke AI/empat
mode: BM25 5/6, dense 6/6, hybrid 6/6, rerank 4/6 target top-8. Reranker menurunkan
target; default hybrid dibekukan khusus snapshot refinement, tanpa mengubah gold.

Tahap 1 menambah Szeghalmy pada bibliografi turunan; DOI Dewi memakai bukti penerbit,
bukan menimpa sumber. Tahap 2 menambah Devlin2019. Instruksi koleksi penuh kemudian
mengganti pembatas DOI/lisensi lokal: 18 identitas terverifikasi tetap, 23 memakai
ID lokal berhash/label unverified. Downloader tetap ketat. Rencana downloader batch
kedua lima PDF/40 request tidak dijalankan; pengguna menyediakan file sendiri.

KB penuh memakai 18 raw lama terverifikasi + 23 konversi dalam delapan batch serial,
tanpa gagal ekstraksi. 2.513 teks unik/2.514 chunk, maksimum embedding 512/512;
7.232 token leksikal short-drop dan span 670/746 halaman dilaporkan, bukan cakupan teks.
Seluruh 974 chunk tahap 2 identik. Build/index/retrieval replay identik, nol encoding
baru; sumber dan snapshot lama tetap. Verifikasi tahap ini: 567 test utama/1 skipped,
35 parser isolated; Ruff bersih. Katalog/label diuji AppTest, belum generation saat itu.

## Retrieval KB penuh dan refinement, 2026-11-20

Baseline: `data/skripsi/retrieval-local-all/2026-11-20T03-14-42Z_956cb9/`.
36 acuan AI dibekukan sebelum ranking: 16 unit dari 11 paper, pertanyaan ID/EN
(32 answerable) + empat kontrol; delapan unit narasi/delapan tabel. Seluruh KB
bersaing, tetapi sampel bukan evaluasi seluruh paper atau gold manusia.

| Mode | Target top-8 | ID / EN | Recall@20 | MRR/20 |
|---|---:|---|---:|---:|
| BM25 | 25/32 | 10/16 / 15/16 | 0,8438 | 0,5640 |
| Dense | 22/32 | 8/16 / 14/16 | 0,8125 | 0,4065 |
| Hybrid | 25/32 | 10/16 / 15/16 | 0,8750 | 0,6230 |
| Hybrid+rerank | 28/32 | 14/16 / 14/16 | 0,9062 | 0,6203 |
| Kandidat rerank 100 | 28/32 | 13/16 / 15/16 | 0,9375 | 0,6163 |

Kandidat 100 memulihkan satu target dan meregresikan satu: gagal gate tanpa regresi,
tidak dipromosikan. QLoRA memiliki bukti alternatif di luar exact target. Sumber
Dewi berkonflik: tabel PDF 8 F1 82,38, abstract PDF 1 82,39; tidak direlabel.
Kontrol masih mendapat hit karena retriever tidak mempunyai ambang abstention.

Refinement `data/skripsi/retrieval-refinement/2026-11-20T06-24-43Z_092865/`
menambah kandidat token teknis, alias sumber/citation key dan prioritas nomor tabel.
Policy/kode dibekukan sebelum validasi baru 8 unit/8 paper (16 answerable + 4 kontrol).
Development reranker/helper 28/32 menjadi 32/32; validasi keduanya 16/16. Replay
identik. Helper hanya kandidat pilot terkontrol, belum mode produksi/UI; lowercase
tanpa petunjuk, nama ambigu, comparison multi-paper dan salah nomor tabel belum teruji.

## Pilot generation dan diagnosis verifier, 2026-11-20

Izin pengguna `boleh` mengikat rencana delapan pertanyaan (6 berbukti/2 kontrol),
maksimal 14 DeepSeek Flash, 2.048 output/request, total output 28.672, pesan
65.536 byte/request, tanpa JEV/judge. Plan/authorization/marker/journal/results ada
pada `retrieval-refinement/2026-11-20T06-24-43Z_092865/generation-plan/`.
Paid `paid-2026-11-20T12-27-50Z_04b780`, replay `replay-2026-11-20T12-28-41Z_053927`.

Aktual tujuh request, 22.943 input/1.371 output, tanpa retry/usage hilang; biaya
unknown. Enam jawaban: 15 klaim/16 sitasi, nol ID ditolak/generation gagal.
Dewi mengutip tabel 82,38. Kontrol privat ditolak provider `claims: []`; Parasuraman
nol konteks/nol API. Abstention sistem 2/2 hanya mencakup satu penolakan provider.

MiniCheck 16/16: 6 S/10 N, precision 0,375, recall/faithfulness implementasi 0,4.
Audit sumber AI menemukan kandidat false negative LoRA/Transformer/Dewi; bukan
label manusia dan tidak mengganti keluaran. Generation/verifier replay identik,
nol API/inference baru, pada salinan DB. Sisa tujuh request bukan izin baru.

Diagnosis lokal: `data/skripsi/verifier-diagnosis/2026-11-20T12-46-00Z_5b9a21/`.
86 probe = 43 view + 43 kontrol AI, dibuat setelah melihat kegagalan; bukan holdout.
Baseline 6 S/10 N tereproduksi, kontrol kanonis 0/16 diterima. Terjemahan Inggris
memulihkan empat LoRA; atribusi lebih lemah memulihkan Transformer tanpa memvalidasi
klaim asli. Varian tabel juga menerima angka salah 1.103 alih-alih 1.102. F1 Dewi
tetap ditolak. Input 38-371/512, tanpa truncation; spasi EOS token identik 86/86.
Replay 86 cache hit/nol inference. Tidak ada transformasi/threshold dipromosikan;
jangan memilih skor view tertinggi atau mengubah label kanonis.

## Uji verifier independen dan evaluasi AI, 2026-11-21

Kebijakan status mesin dikunci di ARCHITECTURE; enam regresi status ditambahkan,
573 test utama/1 skipped dan Ruff lulus. Rancangan baru 12 unit/12 paper,
6 narasi/6 tabel, klaim ID/EN + kontrol (48 pasangan). Semua 19 paper target
development/refinement/diagnosis dikeluarkan; bukan jaminan tak pernah menjadi distractor.
Sampel purposif, seed 42 mengacak urutan; empat pasangan/unit berkorelasi.
Bukti semuanya Inggris, sehingga tidak menguji evidence native Indonesia.

Paket manusia tetap utuh/null:
`data/skripsi/verifier-independent/2026-11-21T07-18-43Z_6b031a/`.
Hash klaim/evidence/PDF/config/halaman/model/threshold dibekukan. Folder reviewer
tanpa skor/niat kontrol; maintainer menyimpan exclusions/specs. Import memerlukan
label/annotator lengkap, identitas sumber tetap, dan output versi baru.

Pengguna lalu meminta seluruh penilaian oleh AI dan mengizinkan maksimal 60 request
GPT Surplus/1.024 output per request, tanpa retry. Run
`data/skripsi/verifier-ai-evaluation/2026-11-21T07-34-32Z_0e9735/`:
48 penilaian GPT + 12 audit konflik dengan model sama; MiniCheck 48 pasangan lokal.
Paket manusia tidak berubah menjadi gold AI. Model/prompt/plan dibekukan sebelum scoring.

GPT: 30 S/4 P/14 N; MiniCheck: 19 S/29 N; coverage 48/48 keduanya.
Agreement 29/48 (60,42%), kappa 0,3133; matriks GPT S/P/N vs MiniCheck S/N
`[[17,13],[0,4],[2,12]]`. Precision relatif GPT 17/19 (0,8947), recall 17/30
(0,5667), bukan akurasi manusia. ID agreement 11/24, EN 18/24; narasi 15/24,
tabel 14/24. Perbedaan label bilingual: MiniCheck 9/24 kelompok, GPT 2/24.

19 konflik, 12 diaudit, label 12/12 tidak berubah. Audit model sama bukan pemeriksa
independen; tujuh konflik tidak mendapat audit tambahan. Audit sumber AI menemukan
shared error kontrol item-020/item-030; agreement dapat menyembunyikan kesalahan.
Seluruh 60/60 request dipakai, 17.358 input/3.178 output, tanpa retry/gagal/usage
hilang, biaya unknown. Replay 48+12 GPT dan 48 MiniCheck cache, nol request/inference.
573 test utama + 8 guard lokal lulus, Ruff bersih. GPT/JEV tidak dipromosikan;
human accuracy tetap null dan set yang sudah dilihat kini bahan diagnosis.

## Integrasi UI dan evaluasi opsional, 2026-11-21

`configs/skripsi-local.yaml` memilih KB penuh dan Tanya korpus. Snapshot UI
`data/skripsi/ui-local/2026-11-21T08-16-45Z_07d296/` menyalin DB pilot generation,
memuat delapan jawaban, dengan chunk/FTS/vektor tetap KB penuh. Manifest mengikat
asal/hash. Pilihan pilot/benchmark memakai config/receipt/demo masing-masing.
Perubahan identitas korpus mereset jawaban dan izin API.

Saat generation cache miss, kutipan retrieval tetap tampil sebagai bukti pencarian.
Jawaban baru memakai izin generator maksimal dua request/submit. Preview/unduh PDF
memeriksa nama kanonis, path dan hash SQL serta halaman PDF asli. Demo memakai
konteks refinement beku, bukan retrieval ulang form. Label mesin asli dipertahankan.

AppTest KB nyata menguji katalog/held, BM25/cache miss, delapan demo, preview/unduh,
pergantian korpus dan izin. Hybrid nyata mengambil delapan chunk tanpa API; sumber
identik. Server health lokal lulus. Browser headless ditolak kebijakan alat;
interaksi memakai AppTest, bukan bukti visual browser/mobile.

Jawaban kini tampil sebelum RAGAS; MiniCheck diagnostik opsional pada DB terpisah.
Evaluasi kualitas mengikat jawaban kanonis/seluruh konteks (termasuk tak disitasi),
hash input/source/config, model/seed/traces/usage pada run baru di
`paths.cache_dir/answer-quality/`. Izin terpisah default mati, maks. 5 request/
1.024 output per request. Cache miss/error null, bukan nol; jawaban tetap terbaca.
Embedding pertanyaan lokal/offline pinned melalui environment utama; RAGAS isolated.
Context Recall tetap batch beracuan; skor AI bukan ketepatan tiap sitasi/akurasi manusia.

Verifikasi terakhir 590 utama/1 skipped + 13 adapter RAGAS isolated, Ruff bersih.
Provider test mock; worker asli cache-only dan embedding 768 dimensi nyata diuji.
Smoke `quality-smoke.json` di folder UI mencatat sumber identik dan preview PDF.
Evaluasi fitur UI dengan API berbayar nyata serta visual browser/mobile belum diuji.
Parser isolated tidak diulang karena parser tidak berubah.

## Cleanup yang sudah disetujui, 2026-11-21

Audit statis tidak menemukan definisi top-level tanpa referensi; bukan bukti seluruh
kode diperlukan. Logger tak terpakai di evaluator dihapus; modul historis tetap.

Daftar konkret dan receipt di `data/cleanup-audit/2026-11-21T09-56-21Z/`:
148 file cache/bytecode (2.036.731 byte), lalu 23 script lokal (150.098 byte) dihapus
setelah persetujuan, validasi path/ukuran dan penghapusan nonrekursif. Script meliputi
15 salinan inspeksi RAGAS, enam QA UI pilot, `quality-smoke.py` dan launcher lama.
Script runtime/KB/replay dan laporan tetap; QA lama tak dapat diulang persis dengan
script yang sudah dihapus. Setelahnya 590+13 test/Ruff lulus tanpa cache/bytecode.
Tidak ada korpus, cache model/API, environment atau secret dalam daftar.

## Perapian dokumentasi, 2026-11-22

Dokumen utama dipadatkan menurut peran: kontrak, operasi, persiapan, riwayat MVP,
dan status skripsi. Checklist selesai, handoff usang dan riwayat ganda diganti
ringkasan hasil/keputusan serta indeks artefak. Status parser/UI diselaraskan ke
kode/config aktif. Laporan evaluasi asli, data, source code, config dan DESIGN
tetap. Agenda UI belum dikerjakan; tidak ada API, inference atau parsing baru.

Validasi sesi dokumentasi: tautan lokal dan anchor Markdown diperiksa, code fence
seimbang, `git diff --check` bersih. Bagian SQL/ID/sitasi pada ARCHITECTURE identik
dengan versi sebelumnya. Delapan file yang berubah hanya Markdown; pytest tidak
diulang karena tidak ada perubahan kode. Angka test di atas tetap bukti sesi sebelumnya.

## RAGAS per card klaim, 2026-11-22

Atas permintaan pengguna, setiap klaim kini tampil dalam card dengan Faithfulness,
Response Relevancy, izin API dan tombol evaluasi sendiri. Evaluator menerima claim
ID milik jawaban kanonis; hanya teks klaim itu dinilai terhadap pertanyaan/seluruh
konteks generation asli. Input/hasil mengikat claim ID dan hash; protokol
`claim-quality-v1`, sedangkan evaluasi jawaban utuh tetap tersedia lewat fungsi lama.
Tidak menyalin skor jawaban utuh atau merata-ratakan skor card. Relevancy card
tidak mengukur kelengkapan seluruh jawaban; Context Recall tetap batch beracuan.

Izin default mati, cache-first, maksimal lima request/1.024 output token per klik
card. Beberapa card dapat menambah biaya; tidak ada evaluasi/API otomatis saat
render. Skor/izin terpisah dan direset saat jawaban/korpus berubah. Cache miss/error
tetap null/belum tersedia; klaim, sitasi, label dan sumber tidak diubah.

596 test utama lulus/1 modul RAGAS skipped; 15 test adapter RAGAS isolated lulus;
Ruff lint/format dan diff check bersih. Test mencakup response/context per claim,
penolakan claim asing/hasil card lain, input tampering, cache replay, dua skor card
berbeda, pemisahan izin dan reset. Provider test mock, tanpa API berbayar baru.
Smoke KB nyata membuka delapan demo (3/4/2/3/1/2/0/0 card), mengevaluasi satu card
melalui worker asli cache-only: nol request, skor null, card lain belum dievaluasi,
reset berhasil dan hash DB sumber identik. Bukti:
`data/ui-card-review/20261122T061518Z/smoke.json`.

Delivery Gate antislop DURING (cakupan perubahan ini):

- Hard Gate PASS untuk perilaku yang diuji: kontrol native berlabel, state awal/
  loading/gagal, AppTest klik card/reset dan worker nyata; tanpa aset/dependensi baru.
- Purpose PASS: bingkai mengikat klaim dan metriknya; arah/dial 1/2/1 di DESIGN.
- Liveliness PASS: penomoran klaim/sitasi dan kutipan sumber tetap identitas meja baca;
  palet/typografi/CSS tetap, tidak menambah dekorasi.
- Craftsmanship PASS pada test/provenance: 596+15 test, Ruff, input/source binding,
  score null bukan nol, dan source DB tetap. Kontras navy/putih 17,85:1 serta fokus
  slate/putih 4,76:1 dihitung dengan checker skill. Antislop-code: tanpa komentar baru.

Pemeriksaan otomatis menolak Edge headless (`blocked by policy`); tidak dicoba bypass.
Visual browser/mobile, keyboard/zoom aktual dan API evaluasi berbayar belum diuji
pada sesi ini. Interaksi diverifikasi AppTest; bukan klaim validasi visual penuh.
Suite parser isolated tidak diulang karena parser tidak berubah.

## API otomatis dan ringkasan token UI, 2026-11-22

Instruksi pengguna menggantikan izin per klik: generator UI otomatis memakai API
saat cache kosong (maksimal 2 request/submit), lalu seluruh card dievaluasi otomatis
(maksimal 5 request/card, 1.024 output token/request). Berlaku juga ketika membuka
demo; CLI/fungsi dasar tetap cache-only. Tidak menambah dependensi atau mengubah
SQL/ID/sitasi/model/label. Tombol/checkbox evaluasi dihapus, penjelasan panjang
dipindah ke expander setelah card. MiniCheck tetap lokal/opsional.

Hasil/marker percobaan disimpan sebelum worker mulai. Rerun/PDF tidak mengulang
evaluasi dalam sesi jawaban yang sama, termasuk gagal/partial. Submit baru atau
pergantian jawaban/korpus memulai hasil sesi baru, tetap memakai cache provider.
Expander Penggunaan token memisahkan generator/RAGAS/total input-output tercatat,
request dan cache hit. Usage unknown ditandai; token generation demo historis
tidak dihitung sebagai pemakaian baru. Batas biaya total mengikuti jumlah card.

598 test utama lulus/1 modul skipped, 15 adapter RAGAS isolated lulus, Ruff dan
diff check bersih. Provider unit/integrasi test dimock; regresi menguji API UI
otomatis, dua card dengan skor terpisah, rerun/PDF tanpa panggilan ulang, gagal
tanpa auto-retry, total token/cache dan generator demo yang tidak tercatat.

Smoke AppTest `from_file` salah mengasumsikan monkeypatch evaluator berlaku;
script app mendefinisikan ulang fungsi, sehingga 3 card demo benar-benar memanggil
GPT-4o-mini. Ini kesalahan harness pengujian, telah diberitahukan kepada pengguna.
Tiga card selesai: 9 request dari maksimum 15, 10.810 input/703 output token,
6 cache hit, tanpa generation baru; biaya mata uang unknown. Receipt diperiksa
tanpa mengulang paid, hash DB sumber identik. Bukti:
`data/ui-card-review/20261122T063510Z/auto-api-receipts.json` dan run answer-quality
yang dirujuk di dalamnya. Selanjutnya harness memakai import `main` dan worker
cache-only eksplisit untuk pemeriksaan ulang tanpa API.

Replay tiga card: skor identik, 15 cache hit/nol request API baru; marker card
mencegah pengulangan saat rerun/PDF, source DB identik. Panel token menunjukkan
nol token API baru (usage generator demo belum tersedia). Bukti:
`data/ui-card-review/20261122T063631Z/auto-cache-replay.json`.

Delivery Gate antislop DURING, cakupan perubahan ini:

- Hard Gate PASS untuk kontrol/state yang diuji: AppTest submit, automatic scoring,
  PDF rerun, failure dan token panel; kontrol izin/evaluasi tambahan dihapus.
- Purpose PASS: skor tetap di card; penjelasan/token dalam expander agar klaim mudah dibaca.
- Liveliness PASS: dial 1/2/1, card bernomor dan sitasi tetap; palet/CSS/aset tidak berubah.
- Craftsmanship PASS: 598+15 test/Ruff, source hash tetap, usage missing tidak dianggap lengkap.

Visual browser/mobile tidak diulang karena peluncuran headless sebelumnya ditolak
kebijakan alat; interaksi diverifikasi AppTest. Suite parser isolated tidak diulang.

Perbaikan operasional berikutnya: UI pengguna mendapat `unexpected keyword argument
'claim_id'` karena proses Streamlit lama masih memuat evaluator sebelum update.
Signature pada disk/fresh process sudah benar; proses server lama direstart,
health 200. AppTest fresh process menerima tiga claim ID dan menampilkan enam metrik,
rerun tidak mengulang evaluasi (evaluator mock, nol API baru). Tidak mengubah kode
atau meregenerasi jawaban; pytest penuh tidak diulang untuk restart/dokumentasi.
