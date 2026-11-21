# Task pengembangan korpus skripsi

Tanggal mulai: 2026-11-19. Status: S0–S1 serta S3–S4 pilot selesai; S2 memiliki 5 PDF siap.
Cakupan PDF berbahasa Indonesia dan pengumpulan sisa korpus masih terbuka.
S5 berjalan: evaluasi otomatis 20 draf dan perbandingan eksploratif verifier selesai;
audit kecil ditutup (9 acuan awal + 1 revisi diterima). Runtime tetap DeepSeek/MiniCheck;
validasi akurasi verifier dan cakupan full text Indonesia masih terbuka.

Tujuan: menjawab pertanyaan tentang referensi skripsi pengguna dengan bukti
yang dapat ditelusuri sampai ke paper, halaman, dan kutipan asli.
Input awal: [reference-skripsi.bib](reference-skripsi.bib), ekspor Mendeley.
Riwayat MVP M0–M7 dan hasil benchmark tetap di [TASKS.md](TASKS.md).

Dokumen ini mencatat pekerjaan lanjutan. Kontrak teknis tetap mengikuti
[ARCHITECTURE.md](ARCHITECTURE.md) dan aturan [AGENTS.md](AGENTS.md).
Scope S0 dan kontrak impor S1 sudah dicatat pada dokumen proyek. Konfigurasi
runtime, skema SQL, serta peran model belum diubah.

## Pemeriksaan awal

- [x] Baca berkas BibTeX tanpa mengubah sumber.
- [x] Hitung secara leksikal: 83 entri, 82 citation key berbeda.
- [x] Temukan key `Rahmatia2025` dua kali dengan DOI `10.4102/HSAG.v30i0.3055`.
- [x] Hitung 62 field DOI, 61 nilai DOI berbeda, 13 field URL, dan nol field `file`.
- [x] Identifikasi referensi dengan teks berbahasa Indonesia dan Inggris;
  bahasa full text belum diperiksa.

Hitungan ini bukan hasil parser BibTeX lengkap, verifikasi bibliografi, atau
bukti ketersediaan PDF. Jumlah paper unik baru ditetapkan setelah audit S1.
SHA-256 berkas awal:
`744baba0ff7cf357397fbec8fa000ddc130cead2a0faa56c612de57ef3324a11`.

## Batas kerja

- Kerjakan satu tahap sampai kriteria selesainya terpenuhi, lalu lanjut.
- Mulai dengan korpus kecil 5–10 dokumen; perluas setelah alur utuh terverifikasi.
- Pakai ulang pipeline yang sudah ada. Tambah kode hanya untuk kebutuhan yang nyata.
- Pertahankan grounding, validasi ID, sitasi per klaim, dan laporan run baru.
- Pisahkan database, indeks, dan evaluasi skripsi dari benchmark M6.
- Jangan mengubah berkas `.bib` asli atau menghapus hasil eksperimen lama.
- PDF, teks penuh, metadata ekspor berisi abstrak, indeks, dan cache tetap lokal
  di `data/`; jangan ikutkan isi korpus dalam commit.
- Aturan saat ini tetap hanya menerima paper open access dengan lisensi jelas.
  Memiliki PDF di Mendeley tidak otomatis memenuhi aturan itu.
- Sumber unduhan baru dan dependensi baru memerlukan konfirmasi sesuai AGENTS.md.
- API berbayar default mati. Persetujuan batch lama M6 tidak berlaku untuk batch baru.

## S0 — Tetapkan scope dan keputusan teknis

Dependensi: tidak ada. Hasil: scope tertulis yang sesuai dengan aturan repo.

- [x] Tetapkan cakupan: semua referensi dalam `.bib` atau subset pilihan pengguna;
  catat topik dan contoh pertanyaan skripsi yang ingin dijawab.
- [x] Catat lokasi PDF yang sudah tersedia dan bahasa pertanyaan yang diperlukan.
- [x] Tetapkan perlakuan untuk artikel, bab buku, prosiding, laporan, dan entri
  non-paper. Entri yang dikecualikan tetap tercatat beserta alasannya.
- [x] Selaraskan OVERVIEW.md dan AGENTS.md dengan korpus skripsi; catat perluasan
  domain dari RAG evaluation dan sumber dari arXiv.
- [x] Tinjau ID paper non-arXiv, pemetaan citation key, dan metadata lisensi.
  Utamakan kontrak saat ini; ajukan perubahan skema/ID bila memang diperlukan.
- [x] Tetapkan sumber metadata/unduhan tambahan dan dapatkan konfirmasi sebelum
  menggunakannya. Jangan menganggap URL dalam `.bib` sebagai URL PDF tepercaya.
- [x] Catat rancangan peran model: DeepSeek sebagai generator; JEV sebagai kandidat
  verifier utama; GPT-4o-mini sebagai pemeriksa kedua; MiniCheck sebagai baseline.
  Penetapan akhir mengikuti evaluasi S5, bukan asumsi kualitas model.

Kriteria selesai: scope, sumber yang diizinkan, dan keputusan kontrak dicatat;
tidak ada perubahan arsitektur yang diterapkan tanpa persetujuan yang diperlukan.

**Keputusan S0 (2026-11-19):** seluruh 83 entri menjadi kandidat audit. Artikel,
prosiding, bab buku, laporan, dan entri misc tetap tercatat; kelayakan bukti
ditentukan oleh identitas dokumen, full text, serta lisensi, bukan tipe BibTeX
saja. Metadata yang tidak menunjuk dokumen ilmiah dipisahkan saat tinjauan S2.
Pengguna menyatakan belum memiliki PDF lokal. Target awal pertanyaan/bukti
Indonesia dan Inggris; kemampuan model default belum diasumsikan memadai.

Tema sementara dari bibliografi: NLP, aspect-based sentiment analysis, evaluasi
model, dan kualitas layanan kesehatan. Contoh pertanyaan awal untuk pilot
(bukan gold yang disetujui): perbedaan metrik klasifikasi; metode ABSA pada
ulasan rumah sakit Indonesia; dimensi kualitas layanan yang dibahas referensi.
Judul skripsi tidak ditebak dari metadata dan dapat diperjelas kemudian.

Pengguna menyetujui tambahan parser `bibtexparser==2.1.0` untuk alur menuju
unduhan otomatis. Sumber tambahan pilot juga disetujui: Crossref untuk DOI;
ACL Anthology, PMC, dan situs penerbit/repository yang dirujuk metadata untuk
full text. Batas keras pilot: **5 PDF, total maksimum 30 request jaringan**,
termasuk redirect/kegagalan, tanpa API berbayar. Request berikutnya di luar
batas ini memerlukan persetujuan baru. Pemeriksaan lisensi tetap wajib.

Metadata audit memakai `reference_id` tersendiri, bukan ID sitasi. Belum ada
paper non-arXiv yang dimasukkan ke database. Format ID umum yang ada ditinjau
dan dipertahankan; pemilihan ID/versi konkret dilakukan setelah PDF cocok,
tanpa mengarang versi arXiv atau mengubah regex/skema secara diam-diam.

## S1 — Impor dan audit BibTeX

Dependensi: S0. Hasil: daftar referensi terstruktur dan laporan audit lokal.

- [x] Pilih parser dari kemampuan/dependensi yang tersedia. Jika perlu dependensi
  baru, jelaskan alternatif dan minta konfirmasi; jangan membuat parser regex umum.
- [x] Impor citation key, tipe, judul, penulis, tahun, DOI, dan URL bila tersedia.
  Bedakan metadata referensi dari bukti full text.
- [x] Tangani Unicode, kurung bertingkat, field opsional, key duplikat, dan input
  tidak valid. Laporkan konflik tanpa menimpa entri secara diam-diam.
- [x] Normalisasi DOI dan deteksi duplikat; kecocokan judul saja menjadi kandidat
  tinjauan, bukan penggabungan otomatis.
- [x] Simpan hubungan entri asal dengan referensi kanonis, termasuk dua entri
  `Rahmatia2025`. Citation key Mendeley tidak menggantikan ID chunk.
- [x] Tulis laporan jumlah input, referensi unik, duplikat, metadata kurang,
  dan entri yang perlu ditinjau; simpan hash input dan konfigurasi.
- [x] Uji dengan fixture sintetis: Unicode, duplikat, metadata hilang, sintaks
  rusak, dan pengulangan impor. Jangan menyalin abstrak korpus ke fixture.

Kriteria selesai: seluruh 83 entri awal terhitung dalam laporan; impor ulang
tidak menggandakan referensi atau mengubah sumber asli.

**Verifikasi S1 (2026-11-19):** CLI offline berhasil membaca 83 entri menjadi
82 kelompok referensi. Duplikat `Rahmatia2025` pada ordinal 64 dan 81 dipetakan
ke satu referensi dengan kedua entri tetap tersimpan; nol blok gagal, nol
konflik metadata, dan 21 entri tanpa DOI. Jumlah 82 adalah identitas menurut
aturan DOI/metadata, belum verifikasi identitas full text secara eksternal.

Run awal `data/skripsi/references/2026-11-19T06-25-06Z_e88eb2/` dan pengulangan
`data/skripsi/references/2026-11-19T06-35-57Z_826ae9/` menghasilkan bytes
entries/references yang identik, dengan laporan run berbeda. Hash `.bib` asal
serta 212 file benchmark/label/evaluasi tetap sama. Berkas ekspor yang memuat
abstrak sekarang diabaikan Git; tidak ada PDF atau korpus baru yang masuk Git.

Seluruh **426 test lulus**, termasuk 22 test baru impor/audit; Ruff lint dan
format bersih. Test memakai metadata sintetis, termasuk Unicode, nested braces,
DOI URL, key/field duplikat, konflik, input rusak, replay, penolakan overwrite,
dan CLI offline. Instalasi hanya menambah parser serta `pylatexenc==2.11`;
PyTorch tetap `2.15.0+cu132`, tanpa `uv sync` atau perubahan runtime model.
S1 tidak memakai API LLM atau request pengunduhan paper.

## S2 — Kumpulkan dan cocokkan PDF

Dependensi: S1. Hasil: PDF yang lolos pemeriksaan dan daftar kekurangannya.

- [x] Cocokkan PDF lokal dengan metadata dan verifikasi judul, penulis, tahun,
  serta versi; kesamaan nama file tidak cukup.
- [x] Cari PDF yang belum tersedia hanya lewat sumber yang sudah disetujui.
  Catat asal, lisensi, versi, waktu pengambilan, dan SHA-256 PDF.
- [x] Bedakan versi penerbit dan preprint. Tautkan ke referensi asal tanpa
  menganggap isi dan nomor halamannya identik.
- [x] Validasi URL, redirect, tipe/ukuran berkas, dan batas request. Gunakan cache;
  jangan mengunduh ulang PDF yang sudah cocok dan utuh.
- [x] Catat status setiap referensi: PDF siap, perlu pencocokan manual,
  belum ditemukan, lisensi belum jelas, atau dikecualikan.
- [ ] Pilih 5–10 dokumen berlisensi jelas untuk pilot, mencakup bahasa dan jenis
  dokumen yang tersedia. Jangan memaksakan unduhan 100%.
  **Sebagian selesai:** 5 PDF siap (1 artikel dan 4 prosiding), tetapi full text
  berbahasa Indonesia belum tercakup. Jangan centang cakupan bahasa sebagai selesai.
- [x] Uji unduhan dengan mock jaringan: gagal HTTP, HTML berkedok PDF, file rusak,
  identitas salah, lisensi hilang, dan pengulangan tanpa duplikasi.

Kriteria selesai: pilot siap diproses; setiap referensi lain memiliki status
dan alasan. Referensi tanpa full text tidak dipakai sebagai bukti jawaban.

**Hasil pilot S2 (2026-11-19):** pengunduhan memakai config
`configs/skripsi-download.yaml`, tanpa dependensi baru. Lima PDF berjumlah
66 halaman tersedia di `data/skripsi/downloads/pdf/`:

| Citation key | Halaman | Lisensi |
|---|---:|---|
| Yulianti2024 | 11 | CC-BY-SA-4.0 |
| Koto2021 | 9 | CC-BY-4.0 |
| Scaria2024 | 17 | CC-BY-4.0 |
| Wilie2020 | 15 | CC-BY-4.0 |
| Lu2025 | 14 | CC-BY-4.0 |

Status di atas berasal dari pemeriksaan otomatis DOI/judul/tahun/penulis pertama
terhadap Crossref, DOI/judul pada halaman artikel, lalu judul/penulis pertama/tahun
pada dua halaman awal PDF. Ini bukan audit manual seluruh penulis atau isi paper.
Lisensi berasal dari `rel=license` artikel; tautan lisensi biasa memerlukan
konfirmasi URL lisensi dalam PDF. CC-BY-SA-4.0 diizinkan dalam config pilot
dan dicatat apa adanya; default config MVP tidak diubah. Versi dicatat sebagai
`publisher_linked_pdf` dan snapshot SHA-256; tidak diklaim sebagai versi penerbit
definitif bila sumber tidak menyatakannya. Tidak ada ID/sitasi baru atau baris
paper/chunk yang ditulis pada tahap ini.

**Batas kampanye:** total 26/30 request HTTP, termasuk tiga lookup DOI dan
pemeriksaan halaman awal saat menyiapkan resolver, redirect, serta kegagalan.
Enam percobaan tautan menghasilkan lima PDF dan satu HTML penangguhan situs.
HTML lengkap tidak memakai slot PDF; hasil transfer yang tidak diketahui akibat
crash tetap menahan slot secara konservatif. Ledger di
`data/skripsi/download-budget.json` bertahan lintas run; jangan dihapus/reset
untuk menambah kuota. Batas lima PDF sudah tercapai, jadi empat request tersisa
bukan izin mengunduh PDF keenam. Run paralel ditolak melalui lock kampanye.

Laporan unduhan awal `data/skripsi/downloads/2026-11-19T06-47-52Z_b81df6/`
dipertahankan. Perbaikan pencocokan angka afiliasi yang menempel pada nama
penulis diuji dengan fixture sintetis, lalu run baru
`2026-11-19T06-50-55Z_cca2b8` mencapai lima PDF; laporan lama tidak diubah.
Replay offline `2026-11-19T06-53-52Z_57a5ae` memakai **nol request baru** dan
memverifikasi ulang hash PDF. Laporan kumulatif `report.json`/`status.md` memuat
82 referensi: 5 `pdf_ready`, 1 `download_failed`, 2 `needs_manual_match`, dan
74 `not_attempted`. Status terdahulu tetap dibawa bila referensi tidak dicoba
ulang pada run berikutnya, dengan `attempted_this_run=false`.

Setiawan2024 gagal karena URL PDF mengarah ke halaman penangguhan situs;
Koto2020 memakai host ACL lama di luar allowlist pilot; Rainio2024 mengarah ke
host di luar allowlist. Sisa referensi belum ditelusuri, bukan dinyatakan tidak
tersedia. Pilot belum mencakup full text Indonesia, bab buku, atau laporan.
Perluasan koleksi memerlukan batas batch baru; lima PDF yang ada siap menjadi
input pilot parsing S3. Belum ada parsing/indexing korpus skripsi atau perubahan model.

**Verifikasi:** 459 test lulus (33 test downloader baru), Ruff lint/format bersih.
Mock mencakup budget persisten, redirect/host, error transport tanpa retry,
ukuran/tipe berkas, PDF rusak/identitas salah, lisensi hilang, cache/hash,
angka afiliasi, lock, konfigurasi, replay, dan penolakan overwrite. Hash 213
file terlindungi (.bib asal, benchmark M6, label, dan eval) tetap sama. Tidak ada
API LLM berbayar, dependensi baru, atau PDF/isi korpus yang ditambahkan ke Git.
Satu pengulangan suite sempat gagal pada penulisan file sementara Windows
(`WinError 32`, file dipakai proses lain); suite lengkap berikutnya lulus
459 test. Helper atomic write tidak diubah di luar scope S2.

## S3 — Bangun korpus pilot dan periksa bahasa

Dependensi: S2. Hasil: indeks pilot dan laporan kualitas sumber.

- [x] Buat config skripsi terpisah dengan lokasi data/indeks/laporan baru.
- [x] Jalankan parsing, chunking, dan indexing yang sudah ada secara berurutan.
- [x] Periksa manual urutan baca, halaman PDF, section, tabel, dan kutipan pada
  sampel setiap dokumen; bedakan halaman PDF dari nomor halaman cetak.
  Pemeriksaan visual dilakukan oleh AI; bukan label manusia atau audit semua halaman.
- [x] Catat PDF scan atau layout yang gagal; OCR ditunda sampai ada kebutuhan
  nyata dan persetujuan dependensi. Jangan menganggap hasil kosong berhasil.
- [x] Pastikan jumlah chunk, vektor, dan FTS cocok; input melebihi batas tokenizer
  tetap ditolak tanpa truncation diam-diam.
- [x] Bandingkan BM25 dan dense pada pertanyaan Indonesia/Inggris yang relevan.
  Model embedding default berorientasi Inggris; ukur kebutuhan multibahasa dahulu.
- [x] Bila perlu model embedding lain, catat lisensi, revisi, biaya perangkat,
  serta keputusan pemilihan. Bangun indeks baru, jangan campur ruang vektor.
  Belum mengganti model: smoke test belum cukup untuk memutuskan penggantian.
- [x] Periksa pengulangan offline dan pastikan benchmark M6 tidak berubah.

Kriteria selesai: pertanyaan pilot menemukan bukti yang dapat diperiksa pada PDF;
batas bahasa, parsing, dan model tercatat dengan contoh kegagalan.

**Implementasi S3 (2026-11-19):** `prepare-bib` menghubungkan laporan PDF siap
S2 ke skema `paper` yang sudah ada, tanpa mengubah SQL atau regex ID/sitasi.
Paper ID memakai `crossref:<DOI>_sha256_<SHA-256 PDF>`: hash adalah versi
snapshot lokal, bukan nomor versi publikasi yang dikarang. Citation key dan
reference ID dipertahankan dalam laporan prepare. Hash bibliografi/PDF,
identitas, halaman, lisensi, dan metadata lama diperiksa; file/metadata yang
berubah ditolak, pengulangan tidak mereset parse status atau menggandakan paper.

Config `configs/skripsi-pilot.yaml` memakai direktori
`data/skripsi/pilot-v1/` untuk raw/parsed/SQLite/indeks/laporan. Cache model dan
embedding di `data/cache` dipakai ulang dengan identitas yang sudah dikunci.
Model tetap BGE base Inggris, revision lama, CPU batch 16, seed 42. Chunking
220 token leksikal, overlap 40, minimum 60, kebijakan drop seperti pilot M6;
parameter ini tidak mengubah chunk/data M6. Lokasi dataset evaluasi di config
masih rencana S5 dan belum merupakan dataset resmi yang tersedia.

**Hasil nyata:** 5/5 PDF, 66 halaman, nol gagal parsing; 310 chunk = 310 vektor
= 310 FTS. Sebanyak 394 token leksikal bagian pendek/ekor dibuang oleh drop;
tidak ada truncation model. Jumlah maksimum tokenizer embedding 384/512
termasuk special tokens. Encoding CPU nyata menghitung 310 embedding baru
dalam run indeks `2026-11-19T07-08-21Z_9a1442` (48,60 detik termasuk pemuatan).
Tidak ada unduhan model/paper; proses memakai `HF_HUB_OFFLINE=1` dan
`TRANSFORMERS_OFFLINE=1`. GPU inference dan puncak RAM/VRAM belum diukur.

**Replay:** `prepare-bib`, parse (semua cached), chunk, dan index diulang
offline. Indeks `2026-11-19T07-11-55Z_558ba7` memakai 310 cache hit dan nol
embedding baru (1,76 detik setelah model tersedia). Hash logis paper, chunk,
FTS, serta metadata/vektor LanceDB identik. Hash 213 file terlindungi termasuk
`.bib` asal, benchmark M6, label manusia, dan eval tetap sama. Ledger unduhan
tetap 26/30 request dan lima PDF; tidak ada API LLM berbayar.

**Pemeriksaan kualitas:** AI membandingkan gambar satu halaman per dokumen
dengan hasil parsed. Bukti di `data/skripsi/pilot-v1/quality-review/` berisi
`review.md`, `parsed-samples.json`, dan lima PNG. Teks narasi sampel terbaca,
tetapi tabel diratakan, rumus/gambar tidak terstruktur, section dapat keliru,
dan header/glyph Yulianti2024 masih masuk. Contoh halaman PDF/cetak:
Yulianti 4/3582, Koto 3/10662, Scaria 3/722, Wilie 3/845, Lu 3/4907.
Sitasi tetap memakai halaman PDF. Flag low_quality nol tidak berarti parser
sempurna; angka tabel perlu dicocokkan dengan PDF asli.

**Smoke retrieval:** 12 pertanyaan berpasangan (6 Inggris, 6 Indonesia),
disusun AI sebagai draf routing, belum ditinjau pengguna. Skrip/hasil lokal:
`data/skripsi/pilot-v1/check_retrieval.py` dan
`reports/retrieval-smoke-2026-11-19T07-11-58Z_e35509.json`.

| Bahasa | Mode | Paper target draf muncul dalam top-5 |
|---|---|---:|
| Inggris | BM25 | 6/6 |
| Inggris | dense | 6/6 |
| Indonesia | BM25 | 5/6 |
| Indonesia | dense | 6/6 |

Seluruh ranking/skor direplay identik dan query dense ulang memakai cache.
Ini bukan accuracy/Recall benchmark berlabel manusia atau evaluasi jawaban.
Contoh kegagalan: BM25 pertanyaan Indonesia tentang kalimat tunggal/pasangan
tidak mengambil Yulianti2024 dalam top-5; dense mendapatkannya pada rank 2.
Model Inggris belum dinyatakan cukup untuk semua pertanyaan multibahasa.
Belum ada alasan terukur untuk menambah model/dependensi pada pilot kecil ini;
keputusan dapat dibuka ulang setelah evaluasi S5. Tidak ada label yang
dipindahkan, dataset `eval/` baru, atau perubahan skor benchmark lama.

**Verifikasi:** 468 test lulus, termasuk sembilan test baru admission dan
integrasi prepare → parse → chunk → index memakai embedder mock. Test mencakup
ID snapshot, skema 14 kolom, replay/cache, metadata/lisensi/hash/halaman/tanggal
tidak valid, penolakan overwrite, dan config eksplisit pada CLI. Ruff lint/format
bersih. S4 Streamlit, generasi jawaban pilot, reranking nyata pada pilot ini,
serta verifikasi semantik klaim belum dijalankan.

## S4 — Tanya korpus skripsi di Streamlit

Dependensi: S3. Hasil: alur tanya-jawab skripsi dengan sitasi yang bisa diperiksa.

- [x] Pakai ulang UI Tanya korpus dengan config skripsi dan generator DeepSeek.
- [x] Tampilkan judul, citation key asal, halaman, dan kutipan untuk tiap sitasi,
  tanpa mengubah format ID chunk yang menjadi kontrak evaluasi.
- [x] Pertahankan cache-first, izin API eksplisit, batas per submit, usage token,
  serta penanganan gagal dan bukti kosong.
- [x] Tampilkan korpus yang sedang dipakai dan bedakan referensi terdaftar dari
  dokumen yang benar-benar sudah terindeks.
- [x] Uji pertanyaan faktual, lintas paper, Indonesia/Inggris yang diperlukan,
  serta pertanyaan di luar korpus. Jangan memberi status terverifikasi palsu.
- [x] Perbarui DESIGN.md hanya jika keputusan visual berubah; verifikasi widget
  dan keterbacaan bila UI diubah.

Kriteria selesai: pengguna dapat bertanya tentang pilot dan membuka bukti asli;
referensi tanpa PDF tidak menghasilkan kutipan atau halaman rekaan.

**Pelaksanaan S4, 2026-11-19:** integrasi pilot selesai dengan batas verifikasi
berikut. UI memakai config DeepSeek yang ada, tanpa request provider berbayar
baru. Flag `--bibliography-report` mengikat citation key ke paper/PDF snapshot,
laporan unduhan, dan daftar referensi dengan pemeriksaan hash. Header memisahkan
82 referensi dari 5 paper/310 chunk yang dapat dicari; daftar sumber hanya
memuat paper dalam database. Identitas korpus/config menghapus jawaban sesi dan
izin API sebelumnya. ID chunk, skema SQL, prompt, dan dataset M6 tetap.

Sembilan test baru memeriksa jumlah/alias, pembacaan tanpa penulisan, penolakan
snapshot atau provenance berbeda, indeks BM25 tidak lengkap, form awal pilot,
sitasi, dan reset jawaban/izin. Seluruh 477 test lulus; Ruff lint/format bersih.
AppTest lama tetap memeriksa batas dua request, koreksi format, error provider,
cache miss, dukungan partial/unverified, dan ketiadaan bukti dengan mock.

Retrieval/reranking **nyata CPU offline** dijalankan pada empat pertanyaan:
faktual Inggris, faktual Indonesia, lintas paper, dan pertanyaan di luar korpus.
Keempatnya direplay dengan ranking/skor sama; reranking awal menghitung 200
pasangan, replay 200 cache hit. Generation memakai **mock dengan identitas
model/cache terpisah** `s4-fixture-not-a-paid-model`, bukan DeepSeek nyata.
Mock mengutip chunk yang benar-benar diambil dan mengembalikan klaim kosong
pada kasus luar korpus; replay memakai cache. Verifier sengaja tidak memberi
label semantik pada matriks ini, sehingga klaim tetap belum diverifikasi.
Ini menguji kontrak dan tampilan; tidak membuktikan kualitas jawaban atau
abstention DeepSeek pada skripsi. Pengujian semantik nyata tetap terbuka di S5.

Artefak lokal di `data/skripsi/pilot-v1/ui-review/`:

- `qa-matrix-20261119T074300Z.json`: config/model, hash korpus, hasil retrieval,
  replay, dan lokasi delapan laporan generation pada salinan database.
- `browser-validation.json`: browser Chrome headless dengan korpus/config asli,
  validasi form kosong, cache miss tanpa API, inventaris, keyboard, dan viewport.
- `browser-fixture-validation.json`: jawaban mock **berbanner fixture**, kutipan
  lintas paper, ekspander, tautan sumber, fokus keyboard, serta reflow kutipan.
- PNG form/kutipan/error pada 320/1280px dan teks 200%; tanpa overflow pada
  tujuh lebar 320–1280px. Tautan sumber membuka tab ke URL tersimpan; status HTTP
  halaman tidak diukur ulang. Batas ini tidak menjadi klaim kualitas sumber.
- `contrast-validation.json`: 40 elemen teks, rasio minimum 4,57:1; fokus/border
  slate memenuhi 3:1. `control-measurements.json`: target kontrol termasuk submit
  44px. Heading jawaban h2 dan fokus native dipertahankan.

Tidak ada PDF baru, perubahan model runtime, label manusia baru, atau evaluasi
M6 yang ditimpa. Pemeriksaan hash 213 berkas terlindungi tetap sama; ledger
downloader tetap 26/30 request dan 5 PDF. API nyata pada pilot skripsi, MiniCheck
semantik pada jawaban pilot baru, serta JEV/GPT-4o-mini belum diuji di S4.
Delivery Gate antislop lengkap ada di TASKS.md bagian S4. Perintah menjalankan
UI tersedia di USAGE.md bagian S4.

## S5 — Evaluasi dan tetapkan verifier utama

Dependensi: S4. Hasil: perbandingan model pada korpus skripsi dan keputusan peran.

- [ ] Buat set evaluasi skripsi terpisah dengan pertanyaan answerable/unanswerable
  dan pasangan klaim-bukti berlabel supported, partial, serta unsupported.
  Label manusia ditinjau sebelum prediksi model ditampilkan bila memungkinkan.
- [ ] Ajukan penambahan dataset evaluasi secara eksplisit; simpan versi, hash,
  status tinjauan, dan persetujuan pengguna. Pertahankan dataset M6 utuh.
- [ ] Bandingkan MiniCheck, JEV `jev-1.14`, dan GPT-4o-mini pada pasangan sama,
  termasuk bukti berbahasa Indonesia dan klaim salah. Jangan ubah alias JEV diam-diam.
- [x] Pisahkan peran GPT-4o-mini sebagai audit dari label manusia; kesepakatan
  antarmodel bukan ukuran kebenaran manusia. Alasan naratif juga perlu diperiksa.
- [x] Sebelum request nyata, sepakati batas keras jumlah request per model,
  anggaran biaya, dan data yang dikirim. Gunakan cache dan tanpa retry tak terbatas.
- [ ] Laporkan ketepatan per label, kegagalan menerima klaim salah, abstention,
  coverage, latensi, token, biaya yang diketahui, dan batas ukuran sampel.
  Confidence JEV tidak dianggap ambang terkalibrasi tanpa pengukuran lokal.
- [x] Tetapkan kriteria pemilihan sebelum melihat hasil; dokumentasikan apakah
  JEV layak menjadi verifier utama dan kapan GPT-4o-mini perlu dipanggil.
- [ ] Jika JEV dipilih, hubungkan ke runtime melalui kontrak verifier yang ada.
  Kegagalan tetap berstatus belum diverifikasi; model tidak menggantikan validasi ID.
- [ ] Uji seluruh jalur dengan mock provider dan replay cache tanpa biaya.

### S5a: RAGAS dan audit manusia kecil

Pengguna menyetujui jalur ini setelah meminta pengurangan pekerjaan manual.
Ini tambahan evaluasi otomatis, tidak mengubah hasil M6 atau mempromosikan
verifier baru tanpa perbandingan yang memadai.

- [x] Pasang RAGAS `0.4.4` di environment terpisah dan kunci seluruh dependensi.
- [x] Ekspor 20 pertanyaan/acuan draf AI dengan hash sumber; pisahkan dari gold manusia.
- [x] Sediakan audit referensi acak maksimal 10 contoh dengan bukti/halaman dan tanpa prediksi judge.
- [x] Hubungkan faithfulness dan context recall RAGAS ke client cache/budget proyek.
- [x] Pertahankan status unknown pada gagal penilaian dan penjelasan penyebut metrik.
- [x] Uji mock pada library RAGAS nyata serta snapshot/replay tanpa API.
- [x] Catat persetujuan pilot 4 pertanyaan, maksimum 8 DeepSeek + 12 GPT-4o-mini.
- [x] Jalankan pilot nyata dan replay tanpa request baru; simpan temuan tanpa mengubah skor lama.
- [x] Tinjau audit kecil 5–10 referensi dan catat penilaian manusia sebagai versi baru.
- [x] Tetapkan batch lanjutan sebelum mengevaluasi sisa 16 pertanyaan dengan API.
- [x] Bandingkan verifier kandidat dengan pasangan dan kriteria yang ditetapkan sebelum prediksi.
  S5c bersifat eksploratif; bukan validasi akurasi manusia atau kontrol klaim salah.

**Pelaksanaan 2026-11-19:** kode berada di `rag.evaluation.ragas` dan
`ragas_adapter`; ekspor draf di `eval/prepare_skripsi_ragas.py`. Environment
RAGAS memakai lockfile khusus, karena pemasangan langsung akan mengganti SDK
OpenAI dan Rich utama. Versi Torch `2.15.0+cu132`, OpenAI `3.54.0`, dan CUDA
utama dipertahankan. Tidak ada perubahan SQL/ID/sitasi, UI, atau model runtime.

Draf disusun AI berdasarkan chunk lokal, bukan testset generation LLM RAGAS.
Komposisi 15 lookup, 2 comparison, dan 3 unanswerable; belum ada synthesis.
Manifest/20 pertanyaan lokal:
`data/skripsi/s5-ragas/drafts/2026-11-19T08-17-12Z_87a27c/`.
SHA-256 dataset:
`f2eeb59b928993f2f5ae008a62caa07e200bfacad1e4f2798cd13e5b49d435ed`.
Audit 10 referensi ada di
`data/skripsi/pilot-v1/reports/evaluation/ragas-inputs-2026-11-19T08-17-12Z_9d2275/reference-audit.md`
dan JSONL di direktori sama. Jawaban acuan AI terlihat dalam audit; ini tidak
disebut penilaian manusia buta. User telah menilai sepuluh acuan: sembilan
sesuai dan satu bukti belum cukup (`skripsi-draft-018`, perbandingan
IndoNLU/IndoBERTweet). Nomor 2 (`skripsi-draft-001`) disetujui lewat konfirmasi
chat; checkbox asli tetap kosong. User kemudian menambahkan alasan untuk 018:
"Bukti hanya mengambil konteks singkat dari abstract, harusnya mengambil contoh
empiris juga dari section lain".

Versi audit baru:
`data/skripsi/s5-ragas/reviews/2026-11-19T09-48-57Z_3046bb/`, melanjutkan
versi `2026-11-19T09-44-55Z_f06733` tanpa menimpanya.
Manifest mengikat hash dataset, lembar audit, konfirmasi, dan label baru.
Pertanyaan, acuan, serta kutipan diverifikasi terhadap JSONL awal dan teks
chunk database read-only; hanya checkbox pada lembar yang berubah. Sembilan
acuan diterima, 018 tetap insufficient/unknown, dan sepuluh acuan lain belum
ditinjau. Ini audit acuan berbantuan AI, bukan label klaim generation atau
ukuran akurasi manusia. Dataset/skor asli tidak diubah; nol API baru.

`evidence-proposal-018.md` pada versi terbaru memuat usulan jawaban dan empat
chunk tambahan dari isi paper: IndoNLU halaman PDF 3/4 (contoh domain tugas dan
cakupan Indo4B), IndoBERTweet halaman PDF 2/3 (jumlah tweet/token serta tujuh
dataset evaluasi). Angka diambil dari narasi; tabel rata tidak ditafsir ulang.
Ini pencarian bukti lokal oleh AI, bukan uji retrieval atau revisi yang sudah
disetujui manusia. Label 018 tetap bukti belum cukup hingga revisi ditinjau.

**Pembaruan persetujuan:** user mencentang "Bukti tambahan cukup" pada usulan
018. Audit kecil selesai: sembilan acuan awal dan satu acuan revisi diterima.
Versi terbaru `data/skripsi/s5-ragas/reviews/2026-11-19T09-51-25Z_b9f906/`
mengikat acuan revisi ke empat chunk; acuan 018 lama tetap insufficient pada
riwayat sebelumnya. Sepuluh acuan di luar sampel belum ditinjau. Dataset/skor
asli tetap, nol API baru, dan ini bukan label klaim generation. Tidak ada
putaran anotasi tambahan yang diperlukan untuk menutup audit kecil ini.

Run persiapan 20 pertanyaan memakai retrieval/reranking CPU nyata dan cache-only
generation. Seluruh cache jawaban saat itu kosong, jadi berstatus gagal dengan
nol API, bukan abstention atau skor nol. Hash input diperbaiki agar membaca
byte berkas Windows CRLF secara konsisten; test integrasi mereproduksinya.
Run awal sebelum perbaikan dipertahankan dan tidak dijadikan hasil evaluasi.

**Persetujuan:** user menjawab "iya aku izinin bro pangggil api" untuk pertanyaan
pilot yang membatasi 8 request DeepSeek dan 12 GPT-4o-mini/Surplus, output maksimal
2048 token/request, prompt judge maksimal 65536 byte, tanpa retry jaringan.
Izin disimpan bersama hash dataset/korpus dan marker reservasi sekali jalan di
`data/skripsi/s5-ragas/api-authorization-pilot4-v1.json`. Jatah CLI bukan ledger
lintas crash; wrapper lokal menolak mengulangi fase berbayar yang sudah dimulai.
Tidak memakai sisa jatah untuk eksperimen lain atau memperluas pertanyaan.

**Hasil pilot nyata:** generation
`ragas-inputs-2026-11-19T08-26-41Z_8ba4d6`, judge
`ragas-scores-2026-11-19T08-27-42Z_4ee90c`, di
`data/skripsi/pilot-v1/reports/evaluation/`.

| Pertanyaan | Tipe | Faithfulness RAGAS | Context recall terhadap acuan AI |
|---|---|---:|---:|
| 001 | Faktual Inggris | 1,0000 | 1,0000 |
| 002 | Faktual Indonesia | 0,8889 | 1,0000 |
| 003 | Lintas paper | 1,0000 | 0,5000 |
| 004 | Di luar korpus | 0,3333 | Tidak berlaku |
| Rerata | Penyebut 4 / 3 | 0,8056 | 0,8333 |

Semua skor eligible selesai tanpa error judge/usage yang hilang. Nol sitasi
ditolak parser. Jumlah klaim 3/3/8/1; pertanyaan terakhir menolak menjawab tetapi
menyimpan penolakan sebagai klaim unsupported tanpa sitasi. Kontrak abstention
nol klaim gagal: **0/1**. Ini berbeda dari mengatakan model mengarang akurasi
dataset pribadi; responsnya memang menyatakan tidak ada bukti. Jangan mengubah
skor/keluaran tersebut secara retroaktif.

**Temuan inspeksi AI, bukan label manusia:** jawaban 002 menambah frasa
"kategori keempat" tanpa menjelaskan kategorinya. Dekomposisi RAGAS memberi
satu verdict unsupported. Untuk 003, kedua paper dan uraian tiga pendekatan
IndoBERT ada dalam konteks, tetapi judge menolak setengah acuan karena nama
Yulianti/Nissa tidak eksplisit pada teks chunk terambil. Skor 0,5 sendiri tidak
membuktikan retrieval kehilangan metode yang diperlukan. Untuk 004, dekomposisi
RAGAS menghilangkan pembatas dataset pribadi November 2026 pada sebagian
pernyataan, sehingga flag mencampur ketiadaan hasil pribadi dengan keberadaan
hasil benchmark. Skor otomatis tidak diperlakukan sebagai kebenaran manusia.

**Usage:** generator DeepSeek Flash 4 request, 15414 token input / 1909 output;
judge GPT-4o-mini 11 request, 26240 input / 2733 output. Di bawah batas 8/12.
Model yang dilaporkan server sesuai nama tersebut. Biaya USD tetap null karena
tarif gateway belum diverifikasi; bukan dianggap gratis. Tidak ada request JEV.

**Replay:** generation `ragas-inputs-2026-11-19T08-30-14Z_ec8e39` memakai empat
cache hit dan nol request; konteks, klaim, dan sitasi identik setelah mengabaikan
ID run internal baru. Judge `ragas-scores-2026-11-19T08-30-16Z_b0f606` memakai
11 cache hit dan nol request; skor dan trace identik. Receipt disimpan di
`data/skripsi/s5-ragas/`.

S5 belum ditutup: evaluasi sisa pertanyaan, perbandingan
MiniCheck/JEV/GPT-4o-mini, serta keputusan verifier utama belum selesai.
Skor RAGAS di atas bukan precision sitasi MiniCheck, Recall@K manusia, atau
akurasi manusia. Panduan reproduksi dan batas ada di USAGE.md bagian S5.

Kriteria selesai: keputusan model didukung hasil yang dapat direproduksi;
tidak wajib memanggil tiga model pada setiap pertanyaan. Penolakan mengganti
verifier tetap keputusan sah bila hasil belum mendukung penggantian.

### S5b: persiapan lanjutan 16 pertanyaan (2026-11-19)

Persiapan selesai; **izin dan eksekusi berbayar belum dilakukan**. Selector
`prepare --offset 4 --limit 16` memilih qid 005–020 dari dataset asli tanpa
membuat dataset/label pengganti. Manifest mengikat hash dataset utuh, offset,
dan daftar qid. Offset tidak valid ditolak sebelum membuat artefak run.

Run offline nyata:
`data/skripsi/pilot-v1/reports/evaluation/ragas-inputs-2026-11-19T09-59-06Z_8087a3/`.
Retrieval/reranking CPU memilih 16 pertanyaan (13 lookup, 1 comparison,
2 unanswerable); generation semuanya cache miss dengan nol request API.
Ini persiapan, bukan skor baru atau abstention. Audit kecil tetap ditutup.

Paket rencana dan bukti:
`data/skripsi/s5-ragas/continuation-20261119T095905Z/`:

- `api-plan.json`: status `proposed_not_authorized`, hash dataset/korpus/config,
  qid, batas, data yang dikirim, dan kebijakan crash/replay.
- `verifier-pairs.jsonl`: 12 pasangan unik klaim/sitasi dari 19 pasangan pilot
  nyata, dipilih seed 42 sebelum prediksi verifier. Komposisi qid 001/002/003
  sebanyak 4/3/5; klaim dan hash chunk kanonis diperiksa. Tidak diberi label manusia.
- `before.json` / `verification.json`: 107 file yang diperiksa tetap identik,
  mencakup dataset, audit/revisi, artefak laporan lama, eval, dan SQLite pilot.

Usulan batas batch baru: **32 DeepSeek Flash non-thinking**, **46 GPT-4o-mini
untuk RAGAS**, dan **12 JEV 1.14 + 12 GPT-4o-mini untuk pasangan verifier**.
Total GPT maksimum 58. Generation mengizinkan satu koreksi format per pertanyaan;
RAGAS membutuhkan maksimal 16×2 langkah faithfulness + 14 context recall = 46
request. Cache hit tidak menghabiskan jatah; kegagalan tetap memakai jatah.
Chat dibatasi 2048 token output/request dan prompt judge 65536 byte, tanpa retry
jaringan/judge. Tarif gateway belum diverifikasi; ini batas request/token,
bukan batas rupiah/USD. Sebelum eksekusi harus ada persetujuan yang mengikat
hash rencana serta marker reservasi eksklusif per fase; crash hanya dilanjutkan
dengan pemeriksaan receipt/cache dan replay tanpa API.

Kriteria pembandingan ditetapkan sebelum hasil: ketiga verifier menerima pasangan
dan teks chunk sama; `partial` tetap kelas tersendiri, error/overlength tetap
unverified tanpa truncation. Laporkan coverage, distribusi label, disagreement,
penerimaan supported, latensi, token, dan replay. Tidak ada label manusia klaim,
kontrol klaim salah terkalibrasi, atau full text Indonesia pada sampel ini;
agreement tidak cukup untuk promosi verifier. Runtime tetap DeepSeek/MiniCheck.
Evaluasi lebih luas sesuai checklist S5 masih terbuka.

Context recall lanjutan tetap terhadap draf asli. Khusus 018, acuan lama pernah
dinilai insufficient; persetujuan revisi tersendiri tidak dipindahkan ke dataset
lama. Jangan menyebut agregat sebagai gold manusia atau akurasi manusia.

Verifikasi: **489 test utama lulus, 1 modul opsional dilewati**; **21 test**
di environment RAGAS lulus, termasuk library nyata dengan provider mock.
Ruff lint/format bersih. Test baru memeriksa pemilihan subset, cache replay,
dataset tetap, serta penolakan offset negatif/bool/noninteger/di luar dataset.
Delivery Gate antislop: backend/dokumentasi saja, tanpa perubahan UI/aset;
hasil nyata dan keterbatasan dicatat, tidak ada anotasi atau API baru.

### S5c: batch nyata lanjutan dan keputusan terbatas (2026-11-19)

User menjawab **"mari kerjakan!"** atas rencana S5b. Persetujuan terpisah
`authorization.json` mengikat hash rencana
`850b631c777d8653e437665d920f0be5340a5bd099a5e215e6c87acc0f950841`
pada `data/skripsi/s5-ragas/continuation-20261119T095905Z/`.
Rencana awal tidak diubah. Wrapper lokal `execute.py` memeriksa hash dataset,
korpus/config/pasangan serta identitas model, menolak marker fase berbayar
yang sudah ada, membatasi prompt judge aktual, dan menyimpan receipt.

**Hasil otomatis:**

| Cakupan | Faithfulness RAGAS | Context recall terhadap draf AI | Abstention ketat |
|---|---:|---:|---:|
| Sisa 16 pertanyaan | 0,985714 (14/14 dinilai) | 1,000000 (14/14) | 2/2 |
| Gabungan 20 pertanyaan | 0,945679 (18/18) | 0,970588 (17/17) | 2/3 |

Gabungan dihitung per pertanyaan pada laporan baru, bukan rerata dua rerata run.
Dua jawaban kosong tidak diberi skor faithfulness; recall hanya answerable.
Tidak ada generation gagal. Batch baru memuat 49 klaim dan nol sitasi ditolak
validator ID. Penolakan pilot lama tetap satu klaim unsupported: skor lama
0/1 dipertahankan, bukan dianggap telah diperbaiki oleh hasil dua kontrol baru.
Skor otomatis bukan akurasi manusia atau precision sitasi.

**Perbandingan pada 12 pasangan pilot yang dibekukan:**

| Verifier | Supported | Partial | Not supported | Coverage |
|---|---:|---:|---:|---:|
| MiniCheck | 5 | 0 | 7 | 12/12 |
| JEV 1.14 | 8 | 4 | 0 | 12/12 |
| GPT-4o-mini | 11 | 1 | 0 | 12/12 |

Agreement JEV/GPT 9/12 (kappa 0,307692); MiniCheck/JEV 5/12 (0,192308);
MiniCheck/GPT 5/12 (0,056180). MiniCheck biner, partial tidak digabung dengan
supported. Tidak ada error/overlength/truncation pada 12 pasangan ini. JEV
melaporkan `typesafe/jev-1.14-20261014`, bukan alias versi lain. Median waktu
adapter per pasangan MiniCheck/JEV/GPT: 1,003/0,738/1,543 detik; MiniCheck awal
72,133 detik termasuk pemuatan. Peak RAM/VRAM wrapper ini tidak diukur.

**Keputusan:** pertahankan runtime DeepSeek/MiniCheck; JEV belum dipromosikan.
Agreement bukan akurasi; sampel belum memiliki label manusia klaim generation,
kontrol klaim salah terkalibrasi, atau full text Indonesia. Tidak ada putaran
anotasi baru yang dibuka. Checklist validasi per label/false acceptance S5 tetap
terbuka; keputusan tidak mengganti verifier berlaku untuk bukti saat ini.

**Temuan inspeksi AI:** qid 008 mendapat faithfulness 0,8. Jawaban menyatakan
dataset Table 3 dibagikan **kecuali Twitter**; dekomposisi RAGAS memisahkannya
menjadi klaim semua dataset Table 3 dibagikan, lalu menolak pernyataan itu karena
pengecualian Twitter. Skor mentah dipertahankan, bukan dikoreksi manual. Acuan
018 tetap draf lama yang pernah dinilai insufficient; persetujuan revisi tidak
dipindahkan. Sembilan acuan awal + satu revisi diterima, sepuluh lainnya belum
ditinjau. Dataset didominasi lookup dan belum memuat synthesis.

**Penggunaan baru:** DeepSeek 16/32 request (59523 input / 6069 output token);
GPT RAGAS 42/46 (100569/9848); GPT pasangan 12/12 (4309/618);
JEV 12/12 (8401/516). Total GPT **54/58**, total batch **82 request**.
Tidak ada usage unknown, retry jaringan/judge, atau penggunaan sisa jatah untuk
eksperimen lain. Biaya mata uang tetap unknown; bukan dianggap gratis.

Artefak di `data/skripsi/pilot-v1/reports/evaluation/`:

- Generation `ragas-inputs-2026-11-19T11-34-01Z_2b0890`.
- RAGAS `ragas-scores-2026-11-19T11-35-01Z_16f94a`.
- Replay generation `ragas-inputs-2026-11-19T11-35-09Z_9b76da`.
- Replay RAGAS `ragas-scores-2026-11-19T11-43-59Z_f94ec5`.

Paket continuation memuat `verifiers/`, `verifiers-replay/`,
`verifier-analysis.json`, `combined-summary.json`, `summary.md`,
authorization/marker/receipt, serta provenance hash source dan versi.
Replay generation identik pada konteks/klaim/sitasi, replay RAGAS pada skor dan
trace terstruktur, dan replay verifier pada label/probabilitas/alasan; semua
memakai **nol API baru**. ID run/waktu baru tidak dibandingkan sebagai isi jawaban.

Verifikasi ulang: **489 test utama lulus, 1 modul opsional dilewati; 21 test
environment RAGAS lulus; Ruff lint/format bersih**. Pemeriksaan wrapper lokal
memastikan batas byte diterapkan sebelum backend dan marker tidak ditimpa.
107 file lama yang dicheckpoint, dataset, audit/revisi, dan SQLite pilot tetap
identik. CUDA/Torch utama tetap `2.15.0+cu132`, SDK utama OpenAI `3.54.0`;
evaluasi memakai RAGAS `0.4.4`/OpenAI `3.3.0` terpisah. Tidak ada dependensi,
skema, format sitasi, UI, atau aset baru. Delivery Gate antislop DURING:
angka berprovenance, batas metrik dinyatakan, replay nyata terverifikasi;
antislop-ui dibaca sesuai permintaan, gate visual tidak berlaku pada batch ini.

## S6 — Perluas korpus dan tutup pekerjaan

Dependensi: S5. Hasil: korpus skripsi yang siap dipakai dan dokumentasi jujur.

Kontrak persiapan sebelum rencana 44 PDF ada di
[KB-PREPARATION.md](KB-PREPARATION.md). Alur memisahkan ingestion, parsing/OCR,
pemeriksaan kualitas, chunking tabel, indexing, serta uji aplikasi. Aturan
default menahan tabel meragukan tanpa mewajibkan koreksi semua paper. Inventaris
codebase awal belum menetapkan file yang aman dihapus. Status masih untuk
diterapkan; belum ada penggantian parser aktif, pemindahan/penghapusan file,
atau parsing penuh. Mulai adapter/gate pada korpus baru dan uji tiga dokumen
lengkap; inventaris folder PDF final setelah path diberikan.

**Riwayat handoff sebelum implementasi adapter:** pengguna menyetujui kelanjutan setelah penjelasan aturan
penahanan dan meminta pindah sesi. Arah proses/default penahanan disepakati;
implementasi adapter, gate, serta chunk tabel belum tersedia. Pengguna sedang
mengunduh 44 paper sendiri; path folder akan diberikan kemudian. Sesi berikutnya
dapat mulai adapter/test memakai lima PDF pilot tanpa menunggu folder final.
Inventaris 44 file dilakukan setelah path tersedia. Peta entry point dan urutan
kerja ada di KB-PREPARATION.md bagian 8–9. Tidak ada cleanup destruktif,
parsing massal, atau request jaringan/API pada handoff ini.

**Arah berikutnya:** pengguna menunda pengukuran akurasi manusia dan meminta
lanjut pengumpulan PDF. Audit kecil tetap ditutup, status gold tidak dinaikkan.
Rencana offline ada di `data/skripsi/download-batch2-plan-20261119T115052Z/`:
prioritas Maretta2025, Imaduddin2023, Perwira2025, Hidayah2024, Rifaldi2023;
cadangan Koto2020 dan Pontiki2014. Usulan maksimal lima PDF tambahan dan
40 request jaringan termasuk redirect/gagal, tanpa API berbayar. Lisensi dan
bahasa full text masih unverified. Batas kampanye ini belum disetujui.
Sumber tetap Crossref, ACL, dan penerbit/repository yang dirujuk metadata cocok;
host harus masuk allowlist eksplisit setelah pemeriksaan. Ledger lama tetap
26/30 dan lima PDF; kampanye baru harus memakai ledger baru. `preferred_keys`
hanya urutan, sehingga eksekusi harus membatasi kandidat secara eksplisit
sebelum jaringan; jangan otomatis menelusuri seluruh 82 referensi. Persiapan ini
tidak mengubah kode, database/indeks, label, atau laporan eksperimen lama.

- [ ] Proses sisa dokumen yang memenuhi syarat; catat semua kegagalan dan
  pengecualian. Target mengikuti referensi pengguna, bukan 100–500 paper MVP awal.
- [ ] Pastikan penambahan dokumen dapat diulang tanpa merusak data lama;
  jalankan ingestion/indexing terpisah dari query aktif.
- [ ] Jalankan evaluasi retrieval dan sitasi pada korpus final sebagai run baru.
  Nilai ulang label bila chunk berubah; jangan memindahkan label lama sembarangan.
- [ ] Lengkapi OVERVIEW.md, ARCHITECTURE.md, USAGE.md, dan README.md sesuai
  perilaku yang sudah diterapkan. Catat verifikasi dan handoff di TASKS.md.
- [ ] Jalankan seluruh pytest, Ruff lint/format, dan pemeriksaan diff setelah
  perubahan kode. Gunakan Python `.venv` langsung untuk menjaga build CUDA.
- [ ] Periksa perubahan Git: tidak ada secret, PDF, teks penuh/abstrak korpus,
  indeks, atau file besar. Tinjau `.bib` sebelum memutuskan ikut commit.
- [ ] Catat yang benar-benar diuji, jumlah referensi/PDF/indeks, hasil evaluasi,
  model efektif, biaya yang diketahui, dan hal yang belum terverifikasi.

Kriteria selesai: referensi dalam scope seluruhnya memiliki status; dokumen yang
layak sudah terindeks; QA dan sitasi lolos verifikasi; batas cakupan dilaporkan.

### Pilot parser Docling GPU untuk persiapan knowledge base (2026-11-19)

Pengguna menyetujui percobaan Docling setelah membahas komponen dan VRAM 8 GB.
Ini eksperimen terpisah, belum mengganti parser/index/runtime. Pengguna sedang
mengunduh PDF referensinya sendiri; rencana unduhan batch kedua di atas tetap
belum dijalankan. Pengukuran akurasi manusia masih ditunda sesuai permintaan.

Implementasi: `rag.evaluation.docling`, `configs/docling-pilot.yaml`, serta
`eval/docling-requirements.in`/`.lock`. Environment
`data/skripsi/docling-pilot/.venv` memakai Docling 2.151.1, EasyOCR 1.7.2,
Torch 2.15.0+cu132 dan torchvision 0.29.1+cu132. Tidak menyinkronkan environment
utama. Seluruh dependensi eksperimen dikunci dengan hash; model layout/tabel
dipin ke commit dan semua bobot dicatat SHA-256. Sumber bobot resmi Hugging Face
dan EasyOCR, tanpa API berbayar atau unduhan paper baru. Heron Apache-2.0,
TableFormer/docling-models CDLA-Permissive-2.0; EasyOCR Apache-2.0.

Konfigurasi: Heron CUDA, TableFormer V1 accurate + cell matching CUDA, EasyOCR
id/en CUDA (CRAFT + latin_g2). Batch layout/OCR/tabel satu; tanpa VLM deskripsi
gambar/rumus. Tiga sampel halaman PDF 3 Koto2021/Wilie2020/Scaria2024 diuji
native dan sebagai raster 200 dpi tanpa layer teks: **6/6 berhasil**.
Masing-masing menemukan 1/1/5 tabel pada native maupun kontrol scan.

**Memori nyata:** GPU keseluruhan teramati maksimum **6718 MiB = 6,56 GiB**
pada RTX 3060 Ti 8 GiB. Polling 0,5 detik termasuk aplikasi lain dan dapat
melewatkan puncak singkat. Torch allocated/reserved maksimum 2,80/5,36 GiB.
Working set proses 2,22 GiB, private commit 9,90 GiB; keduanya bukan ukuran RAM
yang sama. Run final offline per halaman: native 5,91/1,01/1,28 detik (pertama
termasuk pemuatan), scan 3,83/4,02/5,21 detik. Bukan benchmark throughput penuh.

**Kualitas:** tabel menjadi grid sel/HTML, dibandingkan baseline teks rata
parser lama. Pada Koto native, nama IndoLEM dan SmSA tergabung sehingga 3,638
dapat tersambung ke SmSA, padahal baris SmSA memiliki 11,000. Pada scan Scaria,
OCR membaca Rest14/Rest15 sebagai Restl4/Restl5 dan beberapa label ABSA1 salah.
Angka benar belum cukup bila relasi baris/header salah. Probe v2 native 8/9,
scan 6/9: pemeriksaan spot AI, bukan gold/akurasi manusia. Semua probe dibatasi
pada tabel yang sama, bukan mencocokkan angka dari tabel lain.

Satu probe AI v1 salah ketik 90.10; PDF asli dan render tabel independen
membuktikan 92.10. `samples-v2.json` dan `checks-revision-v2.json` menyimpan
koreksi/provenance; `samples.json` dan dua laporan v1 tetap. Tidak ada label
M6/S5 atau dataset benchmark yang diubah untuk memperbaiki skor.

Artefak lokal `data/skripsi/docling-pilot/` memuat `summary.md`/`summary.json`,
checkpoint `before.json`, model, manifest, render asli untuk pemeriksaan, dan:

- Run awal `runs/2026-11-19T16-23-48Z_5915cd`.
- Replay offline `runs/2026-11-19T16-24-49Z_7a14fd`.
- Run v2 offline `runs/2026-11-19T16-26-47Z_46aa62`.

Grid sel identik pada tiga run dan hash model identik. Tiap run baru menyimpan
hasil Docling JSON/Markdown, HTML per tabel, baseline parsed, hash sumber,
config/versi/seed, waktu, serta memori. Halaman scan buatan 1 dipetakan ke
halaman PDF asli 3; belum ada chunk/ID sitasi baru.

**Verifikasi:** 492 test utama lulus, 1 modul opsional RAGAS dilewati; tiga
test Docling juga lulus di environment terpisah. Test memeriksa ikatan sel,
penolakan nilai dari tabel lain, serta raster tanpa teks native. Ruff lint dan
format bersih. 60 file lama yang dicheckpoint (PDF, parsed, SQLite, ledger,
evaluasi) serta versi environment utama tetap sama. `uv pip check` pada
environment Docling menandai lima dependensi aplikasi yang sengaja tidak
dipasang lewat editable `--no-deps`; jalur Docling/test tidak memerlukannya.
Tidak menambah paket tersebut atau mengubah pyproject/lock CUDA utama.

**Keputusan:** VRAM 8 GiB layak untuk konfigurasi/sampel ini, belum jaminan
seluruh PDF muat atau seluruh tabel benar. Pertahankan parser runtime PyMuPDF;
atasi kasus tabel/OCR gagal sebelum integrasi ke knowledge base baru. Belum
menguji full document, scan asli, full text Indonesia, atau dampak retrieval.
Tidak ada perubahan UI, skema, format sitasi, indeks, atau eksperimen lama.
Delivery Gate antislop DURING: hasil terukur dan batasnya dinyatakan, artefak
lama dipertahankan, tidak ada aset/visual UI baru; gate visual tidak berlaku.

### Adapter Docling, gate, dan chunk tabel penuh (2026-11-19–20)

Pengguna meminta implementasi bertahap memakai fixture/PDF pilot, lalu tiga
dokumen lengkap pada database/index baru. Folder 44 PDF belum diberikan;
tidak ada unduhan PDF tambahan, paket baru, API berbayar, atau promosi runtime.

Implementasi opt-in:

- `rag.parsing.docling_pipeline extract`: maksimal tiga PDF lengkap yang
  identitas/hash/lisensinya cocok dengan database sumber baca-saja. Docling
  tetap di environment terisolasi; Heron/TableFormer accurate/EasyOCR id/en,
  batch satu, AUTO OCR selektif, model lokal terkunci, offline.
- `docling_adapter`: halaman asli eksplisit, pemeriksaan teks/angka native,
  grid/header/label/caption, span, dan geometri baris/kolom. Tabel kompleks,
  multiline/pemisah ambigu, mismatch, dan OCR tanpa pembanding ditahan.
  Narasi yang overlap tabel tidak dapat melewati gate sebagai teks rata.
- `rag.chunking.docling`: kelompok baris utuh, caption/header/catatan diulang,
  halaman tetap. Batas tokenizer BGE nyata dan leksikal diperiksa tanpa
  truncation; satu baris/konteks terlalu panjang menahan seluruh tabel.
- `build`: Python utama, gate dihitung ulang dari PDF; hanya chunk lolos
  ditulis ke SQL baru. Konversi gagal tidak boleh membangun subset diam-diam.
  Perubahan hash/config/chunk ditolak, laporan baru mencatat replay/kegagalan.

Artefak final:
`data/skripsi/docling-full/2026-11-19T16-58-24Z_2de8bc/`.
Run ID memakai UTC (waktu lokal proses melintasi pergantian 19–20 November).
`extraction.json`, `*.docling.json`, Markdown/HTML, `*.native.json`, laporan
build/index, `retrieval-smoke.json`, `protected-check.json`, `summary.json`,
serta `verify.py` menyimpan bukti. Config hasil berada dalam run, terpisah dari
pilot aktif; path dataset/label evaluasi baru belum berisi gold resmi.

| Dokumen | Halaman | Chunk | Tabel lolos gate | Ditahan gate | Ditahan ukuran |
|---|---:|---:|---:|---:|---:|
| Koto2021 | 9 | 29 | 1 | 3 | 0 |
| Wilie2020 | 15 | 36 | 5 | 17 | 1 |
| Scaria2024 | 17 | 46 | 14 | 15 | 0 |
| Total | 41 | 111 | 20 | 35 | 1 |

Sebanyak **19 tabel menjadi searchable; 36 dari 55 tabel ditahan**, termasuk
kasus Koto IndoLEM/SmSA. Satu tabel Wilie lolos gate ekstraksi tetapi ditahan
saat chunking karena konteks/baris melebihi batas. Kasus tabel yang belum
didukung disimpan utuh; tidak dibetulkan otomatis. Narasi tertahan 30 blok,
rumus/gambar/kode juga tidak menjadi bukti. Tidak ada halaman tanpa item body;
ini bukan bukti seluruh isi halaman berhasil dipertahankan. Chunker narasi
lama membuang **546 token leksikal** ekor/section pendek sesuai config `drop`.

**Indeks/replay nyata:** 111 chunk = 111 vektor = 111 FTS, maksimum input BGE
349/512 token termasuk special tokens. Final memakai 111 cache hit dan nol
encoding baru; cache berasal dari encoding CPU nyata pada run pengembangan
sebelumnya. Build direplay sama; indeks direplay dengan nol embedding baru.
Tiga query smoke AI (Inggris/Indonesia) × empat mode retrieval, masing-masing
dua kali, memberi ranking/skor/teks identik dan ID kanonis. Bukan evaluasi
accuracy/Recall manusia, generation baru, atau pengujian UI snapshot baru.

Ekstraksi penuh tiga kali menghasilkan byte JSON Docling identik; run awal
`2026-11-19T16-51-20Z_99f119` dan antara
`2026-11-19T16-54-52Z_177bd3` tetap disimpan. Policy awal menghasilkan 112 chunk;
gate geometri lanjutan menahan satu tabel lagi sehingga snapshot final 111.
Database lama tidak dikurangi atau ditimpa. SHA model sama. Puncak Torch final
allocated/reserved **1,24/1,94 GiB**; peak GPU keseluruhan/RAM proses tidak diukur
pada run penuh ini. Durasi per PDF 12,01/26,52/14,77 detik mencakup konversi
dan penulisan/pembandingan, bukan benchmark throughput umum.

Semua 60 hash checkpoint pilot halaman (termasuk database aktif, PDF, parsed,
ledger, dan laporan/label evaluasi yang dicatat) tetap identik. Tidak ada
label/skor lama disalin atau dipromosikan; string ID yang sama lintas parser
tetap terikat snapshot laporan berbeda. Build pengembangan awal sempat
meminta metadata model Hugging Face sebelum guard offline ditambahkan; tidak
mengunduh PDF/dependensi. Run final dan replay berjalan offline, nol API LLM.

**Verifikasi:** 512 test utama lulus, satu modul opsional RAGAS dilewati;
18 test Docling/adapter lulus di environment terpisah. Ruff lint/format bersih.
Tambahan 20 test memeriksa konteks/halaman/baris tabel, scan/mismatch/korupsi,
geometri lintas baris, bypass narasi rata, overlength tanpa truncation,
SQL/FTS/vektor nyata dengan encoder fixture, replay, sumber tetap, hash stale,
dan penolakan build parsial. Test tidak memakai jaringan/API berbayar.

**Batas/keputusan:** parser aktif tetap PyMuPDF. Ambang cakupan kata narasi
0,8 bersifat awal, bukan kalibrasi manusia; status passed bukan akurasi atau
jaminan kebenaran relasi seluruh tabel. Multi-page/merged header, sel multiline,
OCR tanpa pembanding native, scan asli, full text Indonesia, serta dampak
generation/UI belum dituntaskan. Tidak mewajibkan koreksi manual seluruh paper.
Batch 44 PDF menunggu path, inventaris identitas/lisensi, sampel bahasa/scan,
serta pembekuan config sebelum pemrosesan penuh.

Delivery Gate antislop DURING:

- Hard Gate visual/interaksi: tidak berlaku; UI/aset tidak diubah.
- R-17/R-36/R-38 PASS: jumlah/skor berasal dari artefak, smoke AI dan keterbatasan
  kualitas dibedakan dari akurasi manusia.
- R-35/C-2/C-4 PASS: 41 halaman, SQL/vektor/FTS, 12 query/mode dan replay nyata;
  512 test utama + 18 test isolated dan Ruff lulus.
- Purpose/Liveliness: tidak berlaku pada backend; desain UI tetap.
- C-3/C-5 PASS: tidak ada paket/API berbayar/unduhan PDF baru, 60 hash lama sama,
  penahanan terjadi sebelum SQL/index, batas OCR/bahasa dinyatakan.

### Audit tabel tertahan dan adapter lanjutan (2026-11-20)

Pengguna menyetujui pemeriksaan sampel, perbaikan adapter, serta pembandingan
konfigurasi Docling memakai PDF/model lokal. Tidak ada dependensi, API berbayar,
unduhan PDF, atau OCR alternatif baru. Runtime aktif tetap PyMuPDF.

Audit seluruh 55 tabel memakai artefak mentah snapshot awal, dengan 14 render
yang diperiksa AI (12 crop tabel dan dua halaman tambahan). Ini pemeriksaan
struktur/spot oleh AI, bukan label manusia atau koreksi manual seluruh korpus.
Temuan penting:

- Sebagian `cell_native_mismatch` merupakan bug adapter: tanda `-` identik
  diberi coverage nol karena tidak mempunyai token kata. Perbandingan kini
  mempertahankan urutan token termasuk minus, desimal, dan tanda baca.
- Header bertingkat, rowspan label kolom pertama dengan flag eksplisit,
  row-section satu baris penuh, pipe/multiline yang valid kini didukung.
  Header menjadi jalur `parent / child`; konteks kelompok diulang per baris;
  escape JSON mempertahankan isi sel tanpa mencampur batas kolom/baris.
- Grid body berlubang, span ambigu/tumpang tindih, geometri salah, dan native
  yang tidak cocok tetap ditahan. Tidak menebak label/header yang hilang.
  Sel tidak boleh melintasi anchor baris di luar span deklarasinya.
- Sampel Wilie Table 5 memiliki span Classification yang salah memasukkan
  POSP. Gate pusat header gabungan menahannya. Policy awal
  `header_center_tolerance=0.25` memakai proporsi jarak pusat subheader terkecil;
  belum terkalibrasi manusia dan dapat menahan header left-aligned yang benar.
  Kasus IndoLEM/SmSA Koto tetap ditahan; angka/label tidak dikoreksi otomatis.

**Eksperimen `do_cell_matching`:** enam halaman native, masing-masing pada
true/false: Koto halaman 3/4, Wilie 6/13, Scaria 3/4. Terdapat 21 tabel per mode.
Dengan adapter baru, true meloloskan 16 tabel dan menahan 5; false menahan
21/21 tabel. Probe AI yang sama pada Koto/Scaria halaman 3 memberi true 5/6,
false 0/6; bukan accuracy manusia. Mode false menghasilkan sel kosong atau
angka tergabung. Keputusan: **pertahankan true**, tanpa voting atau memilih
konfigurasi per tabel secara otomatis. Opsi boolean kini dapat diberikan pada
config backend baru; config pilot lama tidak berubah byte/hash.

`options.model_dump` lama hanya menyimpan `{}` untuk opsi tabel karena tipe
dasar Pydantic. Backend kini memakai `serialize_as_any=True` agar subclass
tabel/OCR tersimpan lengkap. `effective-options.json` dan skrip pemeriksaannya
mencatat ulang opsi efektif true/false dengan hash laporan asal, tanpa
menimpa laporan konversi yang sudah ada. Perubahan ini menyangkut serialisasi
provenance; mode model yang dibandingkan tetap true/false sesuai config awal.

**Hasil snapshot penuh baru:**

| Dokumen | Halaman | Chunk | Tabel searchable | Ditahan gate | Ditahan ukuran |
|---|---:|---:|---:|---:|---:|
| Koto2021 | 9 | 35 | 2 | 2 | 0 |
| Wilie2020 | 15 | 48 | 12 | 9 | 1 |
| Scaria2024 | 17 | 48 | 18 | 11 | 0 |
| Total | 41 | 131 | 32 | 22 | 1 |

Tabel searchable naik **19 menjadi 32**, tabel tertahan turun **36 menjadi 23**.
Ada 17 tabel lama dipulihkan, tetapi empat tabel prompt Scaria yang sebelumnya
lolos sekarang ditahan: pembanding native mempunyai glyph apostrophe rusak,
sedangkan Docling menulis apostrophe. Ini keterbatasan pembanding, bukan bukti
empat tabel tersebut salah diekstrak Docling. Tidak mengganti glyph unknown
secara spekulatif atau melonggarkan pemeriksaan tanda/angka.

131 chunk = 131 vektor = 131 FTS; maksimum input BGE 349/512 token. CPU
menghitung 35 embedding baru dan memakai 96 cache hit; replay 131 cache hit,
nol encoding baru. Build/index direplay identik; tiga query smoke AI × empat
mode retrieval, masing-masing dua kali, memberi ranking/skor/teks identik.
JSON ekstraksi penuh identik byte dengan snapshot awal; SHA model sama.
Narasi masih memakai drop lama, kini 604 token leksikal akibat perubahan batas
kelompok narasi/tabel yang lolos. Bukan truncation tokenizer atau skor accuracy.

Artefak audit:
`data/skripsi/docling-table-review/2026-11-19T17-16-57Z_47557e/`:
`before.json`, `audit.json`, render, JSON/Markdown/HTML kedua mode,
`matching-*-report.json`, `effective-options.json`, dan skrip reproduksi.
Snapshot penuh baru di
`full/2026-11-19T17-24-19Z_728589/` berisi config/JSON/native/build/index,
summary/retrieval/replay dan skrip verifikasi. Run ID UTC; tanggal lokal 20 November.
Seluruh **292 hash file lama yang dicatat tetap identik**, termasuk tiga
snapshot penuh awal serta 60 file checkpoint pilot sebelumnya. SQL/ID/sitasi,
label/skor lama, model/runtime, dan database aktif tidak berubah.

**Verifikasi:** 526 test utama lulus, satu modul opsional RAGAS dilewati;
32 test Docling/adapter lulus di environment terpisah. Ruff lint/format bersih.
Empat belas kasus test tambahan memeriksa jalur header, rowspan, konteks saat
split chunk, punctuation-only, pipe/multiline, minus/desimal/urutan tanda,
glyph native rusak, salah span header, dan teks gabungan lintas baris.
Test otomatis tetap fixture/mock tanpa jaringan atau API berbayar.

**Batas berikutnya:** 23 tabel masih ditahan karena struktur/header/body,
pembanding native rusak, atau ukuran. Scan asli/full text Indonesia belum diuji;
belum ada evaluasi manusia, generation, atau UI pada snapshot ini. Jangan
mengulang penuh 44 PDF; tunggu path/inventaris/lisensi dan pembekuan konfigurasi.
Tidak ada keharusan mengoreksi semua tabel secara manual.

Delivery Gate antislop DURING:

- Hard Gate visual/interaksi: tidak berlaku; UI/aset produk tidak diubah.
- R-17/R-36/R-38 PASS: angka dari audit/run baru; review/probe AI dan masalah
  pembanding dibedakan dari akurasi manusia serta kesalahan Docling.
- R-35/C-2/C-4 PASS: 12 konversi halaman, tiga PDF penuh, indeks/retrieval/replay,
  526 test utama + 32 test isolated, dan Ruff lulus.
- Purpose/Liveliness: tidak berlaku pada backend; desain UI tetap.
- C-3/C-5 PASS: tidak ada paket/API/PDF baru; 292 hash lama tetap; tabel ambigu
  tetap tidak dapat dicari, empat penahanan tambahan dilaporkan terbuka.

### Inventaris awal input pengguna (2026-11-20)

Folder tersedia: `data/reference-skripsi/`, berisi 41 PDF + 3 TXT dan
`manifest_skripsi.csv` (44 entri). Audit offline membaca seluruh PDF: 746
halaman, tanpa password/error baca, jumlah halaman dan hash cocok dengan
manifest. Tidak ada duplikat byte atau file dokumen yang tidak terdaftar.
Hash 45 file input sebelum/sesudah identik. Belum admission atau indexing.

Artefak dan agenda:
`data/skripsi/local-inventory/2026-11-20T00-23-38Z_b7dd4c/summary.md`,
`inventory.jsonl`, `summary.json`, hash/provenance dan skrip reproduksi lokal.
Empat hash PDF cocok dengan bukti lisensi pilot lama; petunjuk CC lain belum
dianggap hasil verifikasi lisensi. Enam DOI manifest merupakan metadata baru
relatif bibliografi lama, bukan enam konflik yang telah terbukti.
Dewi mencetak DOI berbeda dari manifest; Szeghalmy belum tercatat pada impor
bibliografi. Tiga TXT ditahan karena tidak memiliki pemetaan halaman PDF.
Parasuraman memiliki sampul native dan 29 halaman bergambar/minim teks,
kandidat OCR setelah identitas/lisensi lolos. Bahasa Indonesia/bilingual
terindikasi pada Aufar/Dewi, belum diuji model atau diverifikasi seluruh isi.

Selanjutnya: verifikasi identitas/versi/lisensi, admission PDF lokal yang belum
tersedia, lalu maksimal tiga PDF pilot baru yang memenuhi syarat pada snapshot
terpisah. Batch penuh menunggu pembekuan input/config. Parser aktif, 23 tabel
tertahan, label/skor, database/index lama tetap. Tidak ada dependensi baru,
unduhan/jaringan/API berbayar, penghapusan atau pemindahan file.

Verifikasi: 526 test utama lulus, satu modul opsional RAGAS dilewati; Ruff
lint/format repo dan skrip audit lokal bersih. Pemeriksaan konsistensi inventaris,
45 hash sumber dan enam hash input provenance lulus. Ini verifikasi audit lokal,
bukan hasil parser/OCR pada korpus baru atau pengukuran akurasi manusia.

### Pilot input lokal Indonesia/Inggris (2026-11-20)

Izin pengguna "woke gas mari kerjakan" melanjutkan pilot sebelum batch penuh.
Admission opt-in `prepare-local` tersedia untuk 1-3 PDF, dengan hash bibliografi,
PDF/HTML penerbit, identitas artikel, dan bukti lisensi; database harus baru.
Jalur ini tidak menyamar sebagai laporan downloader atau mengubah bibliografi.
`fetched_at` berarti observasi lokal, dibedakan dari receipt unduhan pada laporan.

Aufar2023/Dewi2025/Koto2020: 34 halaman, final 115 chunk = 115 vektor = 115 FTS;
9/20 tabel searchable dan 11 ditahan. Dua chunk narasi Aufar overlength ditahan;
short-chunk drop lama 78/442/4 token leksikal dilaporkan. Native Indonesia sudah
tercakup terbatas. Scan Parasuraman tidak diadmit karena lisensi belum jelas;
tiga TXT tetap tanpa pemetaan halaman PDF. DOI Dewi pada artikel penerbit cocok
manifest; DOI lama pada PDF dicatat tanpa menimpa sumber.

Spot visual AI menemukan salah gabung baris pada tabel Cleaning Aufar yang
sebelumnya lolos native comparison. Gate band baris diperketat dan diberi test
reproduksi. Tabel itu serta dua tabel panel sejajar Koto ditahan konservatif.
Run awal 119 chunk/12 tabel tetap utuh; raw JSON dua konversi/model SHA identik.
115 chunk final maksimum 512/512 token; replay build/index/retrieval identik,
115 cache hit dan nol encoding baru. Enam query smoke AI pada empat mode memberi
21/24 target top-8: BM25 5/6, dense 6/6, hybrid 6/6, rerank 4/6. Ini bukan
akurasi manusia/dataset evaluasi resmi. Dua target tabel turun setelah reranker.

Artefak: `data/skripsi/local-pilot/2026-11-20T00-35-31Z_6fb4ad/summary.md`,
manifest/HTML berhash, raw/native/table, delapan render, replay/integrity, dan
`verification-2026-11-20T00-45-25Z_96b12d/`. Snapshot final di
`extractions/2026-11-20T00-43-25Z_a665c8/`. Peak Torch final allocated/reserved
terbesar 1737,21/3338 MiB, bukan peak GPU keseluruhan/RAM. Embedding/reranker CPU.

545 test utama + 33 test isolated lulus, satu modul RAGAS dilewati; Ruff bersih.
Tiga HTML sumber diverifikasi; index pengembangan awal sempat meminta metadata
HF sebelum flag offline dipasang. Final build/index/retrieval/replay offline.
Tidak ada paket/API berbayar/PDF baru, penghapusan/pemindahan, perubahan SQL/ID,
promosi runtime atau label/skor lama. UI/generation baru belum diuji.
Berikutnya periksa target reranker/header/batas chunk lalu bekukan config,
selesaikan admission/lisensi korpus lain; belum batch penuh. Gate antislop:
R-17/R-35/R-36/R-38/C-3/C-5 PASS atas artefak/test/hash; UI visual tidak berlaku.

### Refinement narasi dan keputusan retrieval pilot (2026-11-20)

Pengguna mengizinkan pemeriksaan dua target reranker, header terpecah, dan
narasi overlength. Diagnosis memakai cache: target Aufar turun ke rank 10,
dua chunk tabel dataset Koto ke rank 15/19, bukan hilang dari kandidat.
Tidak ada bug penyimpanan/skor yang dibuktikan; reranker tetap dapat dipakai
untuk pembanding. Default snapshot baru hybrid, tanpa mengubah config aktif.

Lima konfigurasi chunk diuji lokal. Mengecilkan target global ke 200 mengatasi
overlength tetapi menahan satu tabel tambahan. Dipilih perbaikan jendela narasi
berbatas tokenizer saja; anggaran tabel/format ID/skema tetap. PyMuPDF lama
tanpa callback tetap lulus test. Unit tunggal yang tidak muat tetap held.

Snapshot baru 118 chunk = 118 vektor = 118 FTS, maksimum 512/512 token,
9 tabel searchable/11 held. Isi non-whitespace dua chunk lama yang tertahan
tercakup penuh (1277/1277 dan 1392/1392 karakter); 13 chunk tabel identik teks,
caption dan halaman. Short-drop leksikal tetap dilaporkan: 61/442/4 token pada
Aufar/Dewi/Koto, bukan klaim cakupan seluruh paper. Header Lemmatization Aufar
memang terpecah pada PDF sumber; tidak disatukan spekulatif.

Enam smoke AI yang sama tetap 21/24 target pada empat mode: BM25 5/6, dense
6/6, hybrid 6/6, rerank 4/6. Target pertanyaan tidak diubah agar tampak membaik.
Replay build/index/ranking/skor identik; 118 cache hit, nol encoding baru.
Config dibekukan hanya untuk pilot native tiga dokumen, bukan izin batch penuh.

Artefak: `data/skripsi/pilot-refinement/2026-11-20T00-54-04Z_721c6f/summary.md`,
`frozen-config.yaml`, `freeze.json`, perbandingan/diagnosis, content check,
snapshot hasil derivasi raw lama tanpa konversi/model baru, dan dua run replay.
549 test utama + 35 isolated lulus; satu modul RAGAS dilewati; Ruff bersih.
Tidak ada paket/API/PDF/jaringan baru, penghapusan/pemindahan, promosi parser,
atau perpindahan label. Scan asli, generation/UI baru dan gold manusia belum diuji.
Gate antislop R-17/R-35/R-36/R-38/C-3/C-5 PASS: hasil/limit terikat artefak,
test dan hash; UI/aset tidak diubah. Berikutnya admission/lisensi korpus tersisa
secara bertahap; keputusan retrieval umum memerlukan evaluasi lebih luas.

### Pembangunan KB tahap 1 dari folder pengguna (2026-11-20)

Pengguna mengarahkan kembali fokus ke knowledge base, mengizinkan pemeriksaan
manifest, admission dan parsing bertahap; tuning retrieval/generation ditunda.
Seluruh 41 PDF + 3 TXT ditriase. 17 PDF/277 halaman lolos bukti; 24 PDF tertahan
dan tiga TXT belum berpeta halaman PDF. Status/alasan per file ada di
`data/skripsi/kb-build/2026-11-20T01-06-05Z_f81029/readiness.csv`.
Szeghalmy ditambahkan pada salinan bibliografi lokal (84 entri/83 referensi);
BibTeX asli tetap. DOI Dewi memakai bukti penerbit terdahulu, bukan koreksi sumber.

Admission lokal kini mendukung batas batch eksplisit tanpa melewati config;
default tetap maksimal tiga. Identitas/bukti lisensi mengikat hash PDF/bibliografi,
HTML artikel, DOI tercetak atau receipt snapshot sama. Pernyataan CC dataset
ditolak sebagai lisensi artikel; allowlist tidak diperluas. Dua HTML metadata
ACL disimpan, satu request penerbit timeout; tidak ada PDF/API berbayar baru.

Lima raw pilot dipakai ulang setelah hash PDF/model/backend cocok; dua belas
PDF lain dikonversi GPU pada empat batch serial, tanpa kegagalan. Raw 277 halaman
dirangkai ke satu snapshot baru, gate/chunk dihitung ulang: 903 chunk = 903 vektor
= 903 FTS, maksimum 512 token; 44/144 tabel searchable, 100 ditahan, tidak ada
held_narrative overlength. Short-drop leksikal lama 2837 token dilaporkan;
258/277 halaman berada dalam span chunk searchable, bukan cakupan teks penuh.

Build/index replay identik, nol encoding baru dan 902 cache hit untuk 902 teks
unik/903 chunk. Index awal memakai 711 embedding CPU baru + 191 cache hit.
SQLite/foreign keys, ID/halaman, hash PDF serta 62 chunk tabel (header/caption/
catatan/halaman) diperiksa. Sampel sitasi hanya pemeriksaan sumber, bukan evaluasi
retrieval/LLM. Tidak ada query eksperimen, generation atau pemindahan label.

Artefak lengkap di `data/skripsi/kb-build/2026-11-20T01-06-05Z_f81029/`:
`summary.md`, manifest/receipt/bukti, batch raw/native, `kb/pipeline-config.yaml`,
`verification.json`, `citation-samples.json`, `page-coverage.json`, dan integrity.
560 test utama + 35 isolated lulus; satu modul RAGAS dilewati; Ruff bersih.
UI/PyMuPDF aktif, snapshot/label/skor lama tetap; tidak ada penghapusan/pemindahan
atau dependensi baru. KB kandidat ini hanya mencakup dokumen/blok yang lolos;
lanjutkan bukti identitas/lisensi dokumen tertahan, tanpa koreksi manual semua paper.
Gate antislop R-17/R-35/R-36/R-38/C-3/C-5 PASS dari artefak/test/hash;
UI/aset tidak diubah, review otomatis bukan akurasi manusia.

## Perluasan KB tahap 2 (2026-11-20)

Empat halaman penerbit diperiksa ulang. Devlin2019 lolos identitas artikel,
versi prosiding dan CC BY 4.0 dari ACL; PDF pengguna tetap dipakai.
Segura-Bedmar2013 memiliki bukti CC BY 4.0 tetapi DOI belum terverifikasi untuk
kontrak admission saat ini. Maretta timeout; kandidat halaman Hellwig 404.
Kegagalan akses tidak membuktikan artikel tidak ada/tidak berlisensi.
20 PDF tertahan lain tidak diaudit ulang pada tahap ini; tiga TXT belum berpeta halaman.

Snapshot baru: **18 PDF/293 halaman, 974 chunk/vektor/FTS**, 48/152 tabel
searchable dan 104 ditahan. BERT menambah 71 chunk dan empat tabel searchable;
17 ekstraksi lama dipakai ulang setelah hash/backend/model cocok. Replay seluruh
chunk identik, 973 cache hit/0 embedding baru; index awal 902 cache hit/71 encoding CPU.
Batas embedding 512/512; konteks tabel dan ID/halaman diperiksa.
Artefak: `data/skripsi/kb-expansion/2026-11-20T01-33-36Z_3f61ac/summary.md` dan `verification.json`.

560 test utama lulus, satu modul RAGAS dilewati; 35 test parser/adapter isolated
lulus, Ruff bersih. Pemanggilan tambahan test indexing di environment Docling
mengalami satu kegagalan karena sentence-transformers memang terisolasi di
main environment; test yang sama termasuk dalam suite utama yang lulus.
Tidak ada pemasangan dependensi, PDF tambahan, API berbayar atau perubahan kode produksi.
Tidak ada tuning retrieval/generation, promosi UI, penghapusan atau pemindahan file.
Gate antislop R-17/R-35/R-36/R-38/C-3/C-5 PASS: receipt, replay, test dan hash;
review otomatis bukan gold manusia. Berikutnya: lengkapi bukti penerbit/DOI dokumen
tertahan; jangan mengganti aturan lisensi atau format ID untuk memaksa admission.

## Koleksi lokal penuh dengan label sumber (2026-11-20)

Pengguna meminta semua PDF lokal diproses tanpa menunggu DOI/lisensi; informasi
belum terverifikasi menjadi label. Ini mengganti pembatas admission koleksi lokal
pada tahap 1/2, bukan mengubah downloader lama. `prepare-local --local-collection`
memerlukan policy manifest eksplisit; mode default tetap ketat. Skema dan regex
ID/sitasi tetap. 18 identitas terverifikasi lama dipertahankan; 23 sumber lain
memakai `local:sha256_<hash>` dan `LicenseRef-UserProvided-Unverified`. DOI opsional;
identitas metadata mengikuti bibliografi/manifest pengguna, bukan verifikasi penerbit.

Seluruh **41 PDF/746 halaman** selesai diekstrak. 18 raw dipakai ulang setelah
hash/model/backend cocok, 23 PDF tambahan dikonversi dalam delapan batch serial,
tanpa kegagalan. 40 PDF menghasilkan **2.514 chunk/vektor/FTS**; Parasuraman1988
sudah di-OCR tetapi nol chunk lolos kualitas. Tidak ada blocker lisensi/DOI.
100/308 tabel searchable, 208 ditahan beserta raw/HTML/native comparison.
7232 token leksikal short-drop tercatat; span chunk mencakup 670/746 halaman,
bukan ukuran kelengkapan teks/akurasi. Maksimum embedding 512/512 token.

Indeks awal: 973 cache hit dan 1540 embedding CPU baru; 2513 teks unik pada 2514
chunk. Seluruh 974 chunk tahap 2 identik. Replay akhir seluruh chunk identik,
2513 cache hit/0 encoding baru; verification.json merekam hasilnya.
UI katalog/label diuji AppTest: 41 paper/citation key, 23 label lisensi belum
terverifikasi, 23 label sumber lokal, satu paper tanpa chunk; validasi submit kosong
bekerja dan API default nonaktif. Tidak menjalankan generation atau tuning retrieval.

567 test utama lulus/1 modul RAGAS dilewati; 35 parser/adapter isolated lulus;
Ruff bersih. Sumber dan dua snapshot KB sebelumnya: 517 hash file tetap.
Tidak mengunduh PDF, menambah dependensi, memakai API berbayar, menghapus/memindahkan
file, atau mengubah label/skor lama. UI/config default belum dipromosikan;
config/receipt lengkap dan open-ui.ps1 tersedia di `data/skripsi/kb-local-all/2026-11-20T01-59-17Z_c95c3b/`.
Agenda berikutnya berfokus kualitas OCR Parasuraman dan pemetaan halaman tiga TXT;
audit DOI/lisensi bukan prasyarat membangun koleksi lokal ini.

## Evaluasi retrieval KB lokal penuh (2026-11-20)

Instruksi pengguna mengalihkan tahap berikutnya ke pembuktian retrieval sebelum
generation. Snapshot wajib `kb-local-all/2026-11-20T01-59-17Z_c95c3b/` dibaca bersama
summary/freeze/verification/page-coverage, config, dan receipt citation key.
Evaluator `rag.evaluation.retrieval` dipakai ulang; tidak ada perubahan kode produksi.

Artefak baru:
`data/skripsi/retrieval-local-all/2026-11-20T03-14-42Z_956cb9/summary.md`.
`questions.jsonl` berisi **36 acuan AI sementara, bukan gold manusia**:
16 unit bukti pada 11 paper, masing-masing ditanya Indonesia/Inggris (32), serta
empat kontrol tanpa bukti. Delapan unit narasi dan delapan tabel. Semua 2.514 chunk
dari 40 paper searchable bersaing; bukan evaluasi menyeluruh semua paper/halaman.
Target chunk/halaman/hash/probe dipilih dari sumber dan dibekukan **sebelum ranking**.
SHA-256 dataset `c4738c754d5eb6d29cbf41b1ecfce73509f15306336b034d1898b063a3feedb1`.
Probe seluruh unit cocok dengan teks native PDF. Spot visual AI lima tabel pada
empat halaman mengonfirmasi caption/header/baris; tidak menjadi label manusia.

| Mode | Target top-8 | Indonesia | Inggris | Narasi | Tabel | Recall@20 | MRR/20 |
|---|---:|---:|---:|---:|---:|---:|---:|
| BM25 | 25/32 | 10/16 | 15/16 | 12/16 | 13/16 | 0,8438 | 0,5640 |
| Dense | 22/32 | 8/16 | 14/16 | 10/16 | 12/16 | 0,8125 | 0,4065 |
| Hybrid utama | 25/32 | 10/16 | 15/16 | 11/16 | 14/16 | 0,8750 | 0,6230 |
| Hybrid+rerank | 28/32 | 14/16 | 14/16 | 14/16 | 14/16 | 0,9062 | 0,6203 |
| Rerank kandidat 100 | 28/32 | 13/16 | 15/16 | 14/16 | 14/16 | 0,9375 | 0,6163 |

Top-8 memakai batas konteks runtime. Recall/MRR hanya atas 32 answerable dengan
target persis; pasangan bahasa berkorelasi dan sampel dipilih dari sumber.
Miss target QLoRA 05-id tetap dihitung tetapi reranker menemukan bukti setara pada
chunk abstrak/isi lain. Karena itu skor bukan akurasi semantik atau gold manusia.
Empat kontrol tetap mendapat hit pada semua mode: retriever tidak mempunyai
ambang abstention, dan belum ada skor penolakan/hallucination generation baru.

Diagnosis: beberapa pertanyaan Indonesia ke sumber Inggris kehilangan target
dari pool top-50; lainnya kalah ranking. Tabel jumlah kelas Dewi 09-en ada pada
dense rank 37 tetapi terbuang saat RRF dibatasi 50. Satu perubahan config turunan
`rerank_candidates: 100` diuji setelah rencana dibekukan: 09-en pulih top-8,
tetapi 10-id keluar. Aturan pemulihan tanpa regresi **gagal**; tidak dipromosikan.
Ini perbandingan development pada dataset sama, tanpa held-out validation.
Tabel F1 Dewi PDF 8 berisi 82,38, sementara abstrak PDF 1 berisi 82,39;
reranker baseline menempatkan tabel rank 14 pada 10-en. Konflik sumber dan
angka alternatif pada kesimpulan dicatat, bukan dikoreksi atau direlabel.

`source-audit.json`, `evidence-audit.json`, `candidate-evidence-audit.json`,
`failure-review.md`, dan `candidate-diagnosis.json` menyimpan kutipan kanonis,
ID/citation key, caption/header, halaman asli, ranking/skor dan batas interpretasi.
Baseline empat mode serta kandidat 100 direplay identik; replay tanpa encoding
query/pasangan reranker baru. Baseline menghitung 36 query dan 1.800 pasangan CPU.
599 hash berkas snapshot/source/config/test/eval yang diperiksa tetap identik.
Dataset/label/skor M6/S5, SQL/ID/sitasi, gate, indeks, config sumber dan UI lama tetap.

**Keputusan:** gate pra-ranking seluruh 32 target primary hybrid top-8 belum
terpenuhi; belum siap generation umum KB penuh. Berikutnya perbaiki candidate
recall lintas bahasa dan ranking tabel dengan evaluasi terpisah, lalu validasi
pada set baru sebelum promosi. Pilot generation hanya dapat dirancang dengan
bukti yang sudah diperiksa, kontrol abstention dan konflik sumber; belum dijalankan.
Tidak ada API berbayar, PDF/dependensi baru, parsing ulang, cleanup, penghapusan,
atau pemindahan file. Perubahan pengguna yang belum di-commit dipertahankan.

567 test utama lulus, satu modul RAGAS dilewati; Ruff repo dan skrip eksperimen
bersih. Parser tidak berubah; suite isolated 35 test tidak diulang pada tahap ini.
Gate antislop DURING R-17/R-35/R-36/R-38/C-3/C-5 lulus dengan artefak, replay,
test dan batas hasil. UI/aset produk tidak berubah; antislop-code tanpa cleanup
komentar, komentar baru hanya menjelaskan pembekuan target sebelum ranking.

## Refinement retrieval dengan petunjuk sumber/istilah (2026-11-20)

Pengguna meminta kelanjutan setelah baseline dan pemberitahuan sebelum DeepSeek/JEV
berbayar. Eksperimen offline baru:
`data/skripsi/retrieval-refinement/2026-11-20T06-24-43Z_092865/summary.md`.
Nama folder dibuat saat persiapan; waktu pembekuan/eksekusi sebenarnya tercatat UTC
di `freeze.json` dan laporan run. Semua artefak baseline/label lama dipertahankan.

Kebijakan dan implementasi dibekukan sebelum ranking validasi. Helper lokal menambah
kandidat BM25 dari token teknis uppercase/internal-capital pada pertanyaan asli;
paper eksplisit di-resolve melalui citation key/tahun atau alias nama tunggal.
Alias diverifikasi dengan `load_corpus`/receipt snapshot. Pada paper tunggal, semua
chunk searchable direrank (batas 200); satu nomor Table/Tabel eksplisit memprioritaskan
caption yang cocok. Paper terdaftar tanpa chunk memberi retrieval kosong.
Tidak ada terjemahan acuan, aturan qid, penambahan pengetahuan luar, perubahan chunk,
gate, SQL, ID, indeks, model, atau source config. Helper belum menjadi mode produksi/UI.

Validasi baru: delapan unit bukti dari delapan paper di luar development,
masing-masing Indonesia/Inggris (16 pertanyaan berbukti), serta empat kontrol baru.
Empat unit narasi/empat tabel; enam unit menyebut sumber eksplisit, dua tanpa nama
sumber. SHA-256 dataset `d8c03e6488f023b0d6ad0d24ce2dadb3dbb5118b65a498c9111d0e4360941425`.
Seluruh probe cocok dengan teks native PDF; dua halaman tabel diperiksa visual AI.
Target dan kode/kebijakan tidak diubah setelah ranking. Tetap acuan AI sementara,
bukan gold manusia atau validasi generalisasi semua bentuk pertanyaan.

| Set | Baseline reranker top-8 | Helper top-8 | ID | EN | Narasi | Tabel |
|---|---:|---:|---:|---:|---:|---:|
| Development lama | 28/32 | 32/32 | 16/16 | 16/16 | 16/16 | 16/16 |
| Validasi baru | 16/16 | 16/16 | 8/8 | 8/8 | 8/8 | 8/8 |

Empat target lama 04-id/05-id/09-en/10-en pulih, tanpa regresi pada kedua set.
Kasus QLoRA sebelumnya sudah memiliki bukti alternatif; kenaikan target persis
tidak semuanya merupakan kenaikan dukungan semantik. Konflik F1 Dewi abstrak/tabel
tetap. Replay development dan validasi identik, tanpa encoding/pasangan baru.
Kontrol Parasuraman kosong (1 development, 2 validasi); kontrol data privat tetap
mendapat hit dan masih perlu pengujian abstention generation. Tidak mengklaim akurasi
penolakan LLM dari retrieval kosong tersebut.

**Keputusan:** helper layak sebagai kandidat pilot generation terkontrol dengan
konteks yang sudah diperiksa; belum mengubah UI/default hybrid atau menyatakan
generation umum siap. Pertanyaan lowercase tanpa petunjuk, perbandingan/pengecualian
multi-paper, nama ambigu dalam kalimat kompleks, salah nomor tabel dan akurasi
manusia belum diuji. Tidak ada perubahan kode produksi atau dependensi baru.

`generation-plan/plan.json`, `contexts.json`, dan `review.md` menyiapkan delapan
pertanyaan (6 berbukti/2 kontrol), pertanyaan serta chunk yang akan dikirim.
Status **proposed_not_authorized**, belum ada API. Usulan maksimum **14 request
DeepSeek Flash non-thinking**, mencakup gagal dan satu retry format per pertanyaan;
2048 output token/request, maksimum total 28672 output token, pesan maksimum
65536 byte/request. Satu kontrol retrieval kosong memakai nol API. Verifier lokal
MiniCheck; tanpa JEV/judge. Biaya mata uang unknown, bukan plafon biaya rupiah/USD.
Persetujuan harus mengikat hash rencana; eksekusi memakai marker/receipt, client
global berjatah, dan salinan database/output baru. Sisa budget M6/S5 tidak dipakai.

567 test utama lulus/1 modul RAGAS dilewati; enam test eksperimen lulus; Ruff repo
dan skrip lokal bersih. Hash snapshot/source/config/test/eval dan run baseline lama
diperiksa identik oleh runner/summary. Parser isolated tidak diulang karena tetap.
Tidak ada API, parsing ulang, PDF/paket baru, cleanup, penghapusan/pemindahan, atau
perubahan data/label/skor lama. Gate antislop DURING berlaku pada bukti/provenance,
test, replay, dan batas hasil; UI/aset tidak berubah. Antislop-code tanpa cleanup
komentar pengguna; komentar baru menjelaskan prioritas sumber eksplisit.

## Pilot generation DeepSeek pada KB penuh (2026-11-20)

Pengguna menjawab **`boleh`** atas usulan delapan pertanyaan, maksimum 14 request
DeepSeek Flash non-thinking/2048 output token per request, MiniCheck lokal,
tanpa JEV/judge. Izin pada `generation-plan/authorization.json` mengikat proposal
SHA-256 `7210e09f8fa921ea0027195113ec410275b2d1aceb97262adac523201483bf1b`.
Proposal/status lama tidak ditimpa. Runner memeriksa hash plan/context/config/laporan
retrieval, konteks kanonis dan batas byte, menulis marker reservasi sekali jalan,
menggunakan shared client dengan jatah global 14 dan journal append-only per complete.
Kegagalan/retry format ikut jatah; retry transport nol. Generation dan verification
menulis hanya ke salinan SQLite serta output run baru, bukan database KB sumber.

Artefak:
`data/skripsi/retrieval-refinement/2026-11-20T06-24-43Z_092865/generation-plan/summary.md`.
Paid run `paid-2026-11-20T12-27-50Z_04b780`; replay
`replay-2026-11-20T12-28-41Z_053927`. Input berasal dari top-8 beku helper
retrieval eksperimental, bukan config/UI default lima PDF.

**Generation:** enam pertanyaan berbukti menghasilkan **15 klaim/16 pasangan citation**;
nol citation ID ditolak dan nol generation gagal. Delapan pertanyaan selesai.
Jawaban F1 Dewi mengutip Tabel 2 PDF 8, **82,38%**, bukan abstrak 82,39.
Kontrol data pribadi ditolak DeepSeek nyata dengan `claims: []` (satu request);
kontrol Parasuraman berkonteks kosong menghasilkan nol klaim tanpa API.
Kontrak abstention sistem **2/2**, tetapi hanya satu merupakan penolakan provider.
Validitas ID tidak membuktikan kebenaran semantik semua klaim.

**MiniCheck CPU:** 16/16 pasangan dinilai tanpa error/overlength/truncation;
**6 supported/10 not_supported**, nol unverified. Precision menurut MiniCheck
**0,375**, proporsi klaim dengan citation supported (citation recall/faithfulness
implementasi) **0,4**. Empat pasangan QLoRA dan dua konfigurasi Aqiilah didukung;
empat pasangan LoRA, dua Transformer, tiga jumlah kelas Dewi, dan satu F1 Dewi ditolak.
Ini output verifier, bukan akurasi manusia atau bukti 10 pasangan itu salah secara faktual.

Inspeksi AI setelah prediksi menemukan sumber eksplisit: Vaswani menyebut h=8 dan
dimensi 64; tabel Dewi memuat 1.511/1.102/969 serta F1 82,38; Hu menjelaskan merger
LoRA tanpa latensi. `source-review.md` mencatat kandidat false negative serta batas
atribusi/bahasa/tabel/rumus, tanpa mengganti label/probabilitas/skor atau membuat gold.
Penolakan juga terjadi pada pasangan Inggris, sehingga penyebab tidak dapat
disimpulkan hanya bahasa. Ada klaim generation redundan pada LoRA/QLoRA; tidak
diubah atau diregenerasi untuk memperbaiki skor.

**Aktual:** **7/14 request DeepSeek**, **22943 input/1371 output token**, usage
diketahui seluruhnya, nol retry format/transport. Model respons `deepseek-flash`.
Biaya mata uang unknown; tidak dianggap gratis. Sisa tujuh request tidak dipakai
dan bukan izin batch baru. JEV/judge/RAGAS tidak dipanggil.

Generation replay: tujuh cache hit/nol request, klaim/konteks/Markdown identik
setelah mengabaikan ID run/claim baru. MiniCheck replay: 16 cache hit/nol pasangan
baru, label/skor/metrik identik. Masing-masing database paid/replay memiliki
41 paper/2514 chunk, 8 run/8 answer, 15 claim/16 verification; integrity/foreign
keys bersih. 691 hash sumber/kode/config/evaluasi/hasil lama terlindungi tetap.

**Keputusan:** integrasi generation pilot dan penelusuran bukti berjalan; belum
menyatakan jawaban umum atau label otomatis siap. Berikutnya diagnosis verifier
offline pada pasangan beku, tanpa mengulang generation. JEV belum dipromosikan;
pemanggilan berbayar model lain memerlukan izin baru. UI/default/runtime tetap.

567 test utama lulus/1 modul RAGAS dilewati; enam test guard pilot lulus (batas
global, cache, gagal tanpa retry, byte, model dan marker). Ruff repo/script serta
diff check bersih. Parser isolated tidak diulang; peak RAM/VRAM tidak diukur.
Tidak ada PDF/dependensi baru, perubahan SQL/ID/sitasi/gate, parsing ulang,
penghapusan/pemindahan atau cleanup. Perubahan pengguna dipertahankan.
Gate antislop DURING: angka dari receipt, replay dan audit sumber dengan batasnya;
UI/aset tidak berubah. Antislop-code: komentar hanya menjelaskan guard dan scope.

## Diagnosis verifier offline, 2026-11-20

Persetujuan pengguna “oke silahkan!” mencakup diagnosis lokal pada pasangan
generation beku, tanpa mengulang generation atau API berbayar. Hasil baru:
`data/skripsi/verifier-diagnosis/2026-11-20T12-46-00Z_5b9a21/summary.md`.
Persiapan `2026-11-20T12-40-03Z_2e6526` disimpan tanpa scoring; run pengganti
merapikan baris string sebelum inference. Tidak ada artefak dihapus/dipindahkan.

Dataset diagnosis dibekukan sebelum scoring: 43 view pasangan sumber dan 43
kontrol salah buatan AI, termasuk seluruh 16 pasangan kanonis. Ini diagnosis AI
setelah melihat kegagalan, bukan gold manusia atau sampel independen. MiniCheck
revision/threshold/adapter tetap, source chunk dan halaman dicatat per probe.

- Baseline kanonis tereproduksi: 6 supported/10 not_supported, kontrol salah 0/16
  supported. Skor pilot asli dan label lama tetap, bukan dihitung ulang sebagai gold.
- Empat LoRA yang ditolak menjadi supported setelah klaim diterjemahkan ke Inggris;
  evidence identik dan empat kontrol inversi ditolak. Tujuh terjemahan klaim total
  menghasilkan 6/7 supported; F1 Dewi tetap ditolak, dua Aqiilah tetap supported.
- Dua Transformer tetap ditolak pada cuplikan asli. Klaim beratribusi lebih lemah
  diterima, kontrol 16 head/128 ditolak; ini tidak memvalidasi atribusi klaim asli.
- Serialisasi seluruh tabel tetap 2/6 supported; terjemahan tabel Dewi saja 0/4.
  Gabungan atribusi lebih lemah dan tabel Inggris menerima 2/3 klaim kelas, tetapi
  juga **angka netral salah 1.103**, bahkan skornya lebih tinggi daripada 1.102.
  View ini tidak dipromosikan. F1 tabel 82,38 tetap ditolak pada view yang diuji.
- Panjang 38-371/512 token, nol truncation/overlength. Spasi setelah EOS memberi
  token identik pada 86/86 probe. Ini tidak menjelaskan penolakan pada sampel ini.

86 pasangan dihitung lokal; replay 86 cache hit/nol inference baru, baris identik.
741 hash terlindungi tetap. Nol generation/API berbayar/JEV; tidak ada parsing
ulang, dependensi/PDF baru, perubahan SQL/ID/sitasi/gate atau cleanup. Runtime,
default UI, threshold dan label tetap. 567 test utama + empat test diagnosis lulus;
satu modul RAGAS dilewati; Ruff lint/format repo dan script run bersih. Parser
isolated tidak diulang. Warning bobot MiniCheck dicatat, bukan dibungkam.

**Keputusan:** belum ada perbaikan verifier yang aman untuk promosi otomatis.
Retrieval membawa bukti eksplisit pada contoh penolakan ini; status MiniCheck
perlu dibaca sebagai keputusan mesin, bukan kebenaran manusia. Berikutnya tetapkan
kebijakan pelaporan status verifier dan siapkan uji independen sebelum promosi
transformasi/model. Jangan memilih skor view terbaik atau mengganti label lama.
Pemakaian model berbayar lain memerlukan izin baru. Gate antislop DURING PASS:
angka dari artefak dengan batas AI; UI/aset tidak berubah. Antislop-code PASS:
komentar/kode produksi tidak disentuh.

## Kebijakan pelaporan verifier dan rancangan uji independen (2026-11-21)

Kelanjutan agenda setelah diagnosis offline. Kebijakan kini tertulis pada
ARCHITECTURE.md bagian kebijakan pelaporan verifier dan USAGE.md bagian S4.
Implementasi `support_label` sudah sesuai, sehingga kode produksi/UI tidak diubah.
Status mesin, validitas sitasi, dan audit sumber dibedakan; `not_supported` bukan
vonis fakta salah. Judge/manual tidak menimpa ringkasan MiniCheck. Label error atau
hasil hilang tetap unknown, kecuali ada penolakan/partial yang perlu diperiksa.
Klaim unsupported/tanpa sitasi tetap "Tidak ada bukti". Denominator ringkasan UI
(semua sitasi) dibedakan dari citation recall/faithfulness (sedikitnya satu sitasi).
Enam kasus regresi tambahan menguji prioritas status dan isolasi hasil antarverifier/klaim.

### Rancangan uji independen, belum menjadi dataset

Tujuan: mengukur dukungan pasangan kanonis terhadap penilaian manusia pada sampel
baru, sebelum mempertimbangkan promosi model/transformasi. Tidak perlu generation
atau API baru untuk menyiapkan pasangan. Rancangan ini tidak menambah dataset/label,
tidak memberi izin batch berbayar, dan tidak menetapkan MiniCheck sebagai akurat.
Penambahan dataset memerlukan persetujuan eksplisit sesuai AGENTS.md bagian 8/10.

1. Pakai snapshot KB penuh `kb-local-all/2026-11-20T01-59-17Z_c95c3b` tanpa
   mengubah chunk. Target awal: 12 unit bukti baru pada minimal enam paper,
   enam narasi/enam tabel. Keluarkan unit yang sudah digunakan pada development,
   validasi refinement, dan diagnosis; simpan daftar pengecualian beserta alasannya.
   Bila target tidak tersedia, laporkan kekurangan sebelum scoring; jangan mengganti
   unit setelah melihat prediksi. Sampel ini tetap terbatas, bukan representasi semua korpus.
2. Setiap unit memiliki satu klaim Indonesia dan satu Inggris serta satu kontrol
   salah per bahasa: target 48 pasangan. Kontrol mengubah satu angka/relasi/atribusi
   dengan konteks lengkap; pemeriksa manusia menentukan labelnya, bukan pembuat kontrol.
   Pasangan bahasa dan kontrol satu unit berkorelasi; laporkan 12 unit, bukan 48 unit independen.
3. Simpan pasangan/kutipan hanya pada run baru di `data/`. Bekukan teks klaim, chunk ID,
   hash teks/PDF, halaman, bahasa, jenis bukti, unit kelompok, provenance AI/manusia,
   seed 42, urutan, config, model/revision/threshold, dan hash dataset sebelum scoring.
   Gunakan format anotasi yang ada (`claim`, `chunk_id`, `text_sha256`, `label`,
   `annotator`), dengan label/annotator awal null. Catat field tambahan di manifest
   pendamping; tidak perlu mengubah skema SQL, ID, atau format sitasi.
4. Acak paket anotasi tanpa prediksi/skor atau penanda kontrol. Manusia menilai
   seluruh isi klaim terhadap satu chunk: supported, partially_supported, atau
   not_supported. Bukti tambahan dari halaman asli boleh membantu audit parsing,
   tetapi tidak melengkapi dukungan yang tidak ada di chunk. Masalah parsing/ambigu
   dicatat terpisah; pasangan tak terselesaikan tidak diberi label tebakan.
   Simpan label pada versi baru, sebelum membuka skor; label AI tetap bukan gold manusia.
5. Nilai baseline kanonis lokal dengan revision/threshold tetap pada run baru.
   Laporkan coverage/error/overlength, matriks tiga label manusia versus keluaran model,
   jumlah dukungan salah (manusia partial/not_supported, model supported), penolakan
   salah (manusia supported, model not_supported), precision/recall dukungan dan
   agreement/kappa. Denominator nol atau kappa tak terdefinisi tetap null.
   Pisahkan hasil per bahasa, narasi/tabel, klaim/kontrol, serta jumlah unit/paper;
   partial tidak digabung menjadi supported. Hasil unverified tidak dihitung sebagai penolakan.
6. Kandidat transformasi/model memerlukan kebijakan beku sebelum melihat skor baru
   dan penilaian pada pasangan sama, dengan label asal tetap. Sampel yang dipakai
   menyetel kandidat berubah menjadi development; klaim perbaikan perlu set baru.
   Replay harus identik tanpa API/inference baru. Uji ini tidak mengukur retrieval,
   abstention generation, atau kesiapan jawaban umum. Tidak ada promosi otomatis
   dari agreement AI, skor view terbaik, atau hasil sampel kecil ini.

Status: kebijakan tertulis dan rancangan siap ditinjau; dataset independen, anotasi
manusia, scoring baru, serta promosi model/default belum dikerjakan.
Verifikasi sesi ini: `python -m pytest -q` dari `.venv` menghasilkan **573 passed,
1 skipped** (modul RAGAS); Ruff lint dan format bersih (122 file), `git diff --check`
bersih. Tidak menjalankan model/API, scoring dataset, atau suite Docling isolated;
parser tidak berubah. Diff terbatas empat dokumen dan `tests/test_ui.py`, tanpa
korpus/secret/data baru. Pemeriksaan bukti/provenance PASS: aturan dicocokkan dengan
kode dan test; target 48 pasangan dinyatakan sebagai rencana, bukan hasil.
Gate visual tidak berlaku karena source UI, layout, dan aset tidak diubah.

## Paket anotasi verifier independen disiapkan (2026-11-21)

Pengguna menyetujui pembuatan dataset/paket anotasi dengan “gas kerjakan aja!”.
Persetujuan ini tidak menambah izin API berbayar. Paket final berada di
`data/skripsi/verifier-independent/2026-11-21T07-18-43Z_6b031a/`.

- 12 unit dari 12 paper: enam narasi/enam tabel, 48 pasangan klaim Indonesia/Inggris
  dan kontrol. Semua label/annotator awal null; niat pembuat kontrol bukan gold.
- Pemisahan lebih konservatif dari unit: seluruh 19 paper target development,
  validasi refinement, dan diagnosis dikeluarkan. Daftar/alasan/hash input ada di
  `maintainer/exclusions.json`. Ini bukan jaminan paper belum pernah muncul sebagai
  distractor retrieval atau diperiksa dalam audit korpus historis.
- Sampel purposif, bukan random sampling korpus. Seed 42 mengacak urutan anotasi.
  Bukti kanonis semuanya berbahasa Inggris; klaim ID/EN tidak menguji evidence
  native Indonesia. Empat pasangan satu unit berkorelasi, bukan 48 unit independen.
- Hash klaim/evidence/PDF/config, halaman, model/revision/threshold, provenance AI,
  metadata kelompok dan urutan dibekukan sebelum scoring. Kutipan tidak diubah.
  Anchor native lolos untuk 12 unit; enam halaman tabel ditinjau visual oleh AI.
  Ini audit persiapan, bukan anotasi manusia atau bukti akurasi verifier.
- `reviewer/annotations.csv` dan `annotations.jsonl` tidak memuat skor, prediksi,
  niat kontrol atau ID kelompok. `evidence.md` untuk membaca; `README.txt` untuk
  instruksi label. Penilai hanya menerima folder reviewer; file maintainer/specs
  tidak dibuka sebelum label selesai. Relasi bilingual/kontrol membatasi blinding.
- `prepare.py check` memeriksa freeze, sumber dan 836 hash terlindungi. Import CSV
  menolak perubahan klaim/bukti/halaman, ID ganda, label kosong/invalid atau tanpa
  annotator. Label manusia yang diberikan disimpan pada versi baru, memakai loader
  anotasi yang sudah ada. Catatan parsing/ambigu tidak diubah menjadi label tebakan.

Persiapan pertama `2026-11-21T07-14-17Z_9efc2c` tetap disimpan. Run final memakai
script yang dirapikan panjang barisnya; hash dataset, evidence dan urutan identik.
Tidak ada scoring/inference/generation/API baru, perubahan runtime/default,
SQL/ID/sitasi/model/threshold, dependensi/PDF baru, atau penghapusan/pemindahan.
Sebelas test guard lokal dan 573 test utama lulus; satu modul RAGAS dilewati.
Ruff lint/format repo (122 file) serta dua script final bersih; diff check bersih.
Verifikasi akhir dan batas tercatat pada `summary.md`/`verification.json` di run
final. Suite parser isolated tidak diulang karena parser tidak berubah.
Berkas kutipan/paket tetap di `data/`
yang diabaikan Git; perubahan pengguna sebelumnya dipertahankan.

Status: paket siap dinilai manusia. Berikutnya pengguna/penilai mengisi salinan
CSV, mengembalikan path, lalu validasi/import label dan scoring baseline lokal pada
run baru. Tidak ada gold manusia atau hasil evaluasi baru sampai tahap itu selesai.

## Evaluasi verifier seluruhnya oleh AI, 2026-11-21

Pengguna meminta seluruh penilaian diserahkan ke AI, lalu memberi izin “GAS BOLEH!”
untuk Surplus GPT: maksimal 60 request/1.024 output token per request, tanpa retry
otomatis. Ini mengubah prasyarat anotasi manusia untuk run AI baru saja; paket
manusia tetap utuh/null, tidak diubah menjadi gold AI atau ditimpa. Run final:
`data/skripsi/verifier-ai-evaluation/2026-11-21T07-34-32Z_0e9735/`.

Rencana/konfigurasi/prompt/kode dibekukan sebelum scoring. Dataset tetap 48 pasangan
dari 12 unit/12 paper; GPT awal hanya menerima claim/evidence, tanpa penanda kontrol
atau hasil MiniCheck. Model lingkungan yang dibekukan `gpt-4o-mini` lewat Surplus;
48 request awal dan maksimal 12 audit pada konflik pertama dalam urutan beku.
Audit memakai model sama dengan prompt teliti, bukan pemeriksa independen ketiga.
Backend mencatat reservation sebelum request, menghitung kegagalan dalam budget,
menolak model/usage/prompt melampaui batas, tanpa retry/redirect. Marker mencegah
pengulangan fase berbayar; recovery hanya inspeksi receipt/cache dan replay dahulu.

**Hasil:** coverage GPT/MiniCheck 48/48. GPT awal 30 supported/4 partial/14 rejected;
MiniCheck 19 supported/29 rejected. Agreement **29/48 (60,42%)**, kappa **0,3133**.
Matriks GPT supported/partial/rejected versus MiniCheck supported/rejected:
`[[17,13],[0,4],[2,12]]`. Precision/recall dukungan relatif GPT **17/19 = 0,8947**
dan **17/30 = 0,5667**, bukan akurasi manusia. Indonesia agreement 11/24, Inggris
18/24; narasi 15/24, tabel 14/24. Label pasangan bahasa berbeda pada 9/24 kelompok
MiniCheck dan 2/24 GPT; terjemahan AI belum menjadi acuan manusia.

Ada 19 konflik; 12 diaudit GPT sesuai policy, **12/12 label tidak berubah**. Tujuh
konflik tidak mendapat audit berbayar tambahan. Audit sumber AI menemukan kandidat
salah kolom/negasi pada kontrol yang diterima GPT dan/atau MiniCheck; keduanya
bersama menerima dua kontrol bermasalah (item-020/item-030). Audit konflik saja
tidak mendeteksi seluruh shared error. Rincian halaman/hash/angka/rationale ada
di `source-review.md` dan `per-pair.json`, bukan label/gold manusia.

**Aktual:** seluruh **60/60 request**, **17.358 input/3.178 output token**, output
tertinggi 108/request, nol retry/gagal/usage hilang. Model respons gpt-4o-mini;
biaya mata uang unknown. Budget batch sudah habis. Tidak memakai JEV/generator.
MiniCheck pinned/threshold tetap menghitung 48 pasangan lokal, 72–327/512 token,
tanpa truncation/overlength; warning bobot tetap dicatat tanpa perubahan loader.
Replay identik: 48+12 cache GPT dan 48 cache MiniCheck, nol request/inference baru.

860 hash terlindungi tetap, termasuk paket manusia lama. 573 test utama + delapan
test guard lokal lulus; satu modul RAGAS dilewati; Ruff repo/script final dan
diff check bersih. Parser isolated tidak diulang. Tidak mengubah SQL/ID/sitasi,
KB/UI/default/model/threshold/label lama, dependensi/PDF atau melakukan cleanup.
Artefak/kutipan tetap di data/ yang diabaikan Git; perubahan pengguna dipertahankan.

**Keputusan:** evaluasi AI otomatis selesai tanpa perlu input anotasi pengguna.
GPT belum dapat dipromosikan sebagai gold atau pengganti verifier berdasarkan
agreement ini. Pertahankan status mesin dan audit sumber terpisah; human accuracy
tetap null. Tidak ada promosi atau batch paid lanjutan otomatis. Kebutuhan berikut
adalah perbaikan terukur pada negasi/angka/header dan validasi baru sebelum promosi;
dataset yang sudah dilihat ini kini menjadi bahan diagnosis, bukan holdout baru.

## Integrasi produk: KB penuh sebagai UI utama, 2026-11-21

Pengguna meminta kembali ke tujuan RAG referensi skripsi, lalu menyetujui koneksi
KB penuh ke UI, pengujian alur nyata sampai halaman sumber, status verifier yang
transparan, dan perbaikan hambatan penggunaan. Tidak menjalankan eksperimen judge
lanjutan atau batch generation berbayar baru.

**Perubahan produk:**

- Tanpa argumen CLI, UI langsung memilih **Referensi skripsi lengkap (41 PDF)**
  dan **Tanya korpus**, memakai `configs/skripsi-local.yaml`. Pemilih juga memuat
  pilot lima PDF dan benchmark historis dengan config/receipt/demo yang cocok.
  Identitas korpus berubah mereset jawaban dan izin API. `--config` eksplisit tetap
  dihormati; CLI parser/evaluasi dan format config inti tidak diubah.
- Snapshot UI baru `data/skripsi/ui-local/2026-11-21T08-16-45Z_07d296/` menyalin
  database pilot generation KB penuh: 41 paper/40 searchable/2.514 chunk dan
  delapan jawaban tersimpan. Vektor/FTS/chunk tetap KB penuh, alias dibatasi hash
  admission receipt. Manifest merekam sumber/hash; database hasil lama tidak ditulis.
- Delapan contoh pilot bisa dibaca tanpa API/inference, termasuk status MiniCheck
  asli dan kontrol nol klaim. Konteks contoh berasal dari refinement pilot yang
  dibekukan, bukan retrieval ulang form UI. Retrieval runtime tetap empat mode
  produksi; default hybrid mengikuti config, helper refinement belum dipromosikan.
- Saat cache generation kosong, kutipan retrieval tetap dapat dibaca sebagai
  **Bukti hasil pencarian**; tidak diklaim menjadi jawaban terverifikasi. Untuk
  jawaban baru tetap perlu checkbox API, maksimal dua request per submit.
- Sitasi dan bukti pencarian mempunyai **Lihat halaman PDF asli** dan **Unduh PDF
  sumber**. Pembaca hanya memakai raw/pdf dengan nama paper kanonis, memeriksa
  SHA-256 terhadap SQL, dan merender nomor halaman asli. PDF tidak dikirim ke
  pihak luar atau diunduh dari internet. Tidak menambah dependensi/skema/sitasi.
- Label verifier tetap penanda mesin, bukan vonis fakta; pesan nol klaim kini
  dibatasi konteks terambil, tidak menyatakan seluruh korpus tidak punya bukti.

**Pengujian penggunaan:** AppTest pada KB nyata membuka katalog/Parasuraman held,
mengirim pertanyaan BM25, membaca bukti saat cache miss, menampilkan PDF dan kontrol
unduh, membuka seluruh delapan contoh, serta berpindah korpus dan mereset izin.
Ketiga profil diperiksa; contoh benchmark juga dibuka. Uji hybrid lokal nyata
mengembalikan delapan chunk dengan nol API; database sumber identik sebelum/sesudah.
Server berjalan di 127.0.0.1:8501 dengan health ok. Peluncuran Edge headless untuk
browser test ditolak kebijakan alat; tidak mencoba bypass. Interaksi diuji melalui
AppTest, bukan klaim pemeriksaan visual browser/mobile baru. Desain/CSS tetap.

576 test utama lulus/1 modul RAGAS dilewati; Ruff lint/format 122 file dan diff
check bersih. Tiga test baru mencakup pilihan default/pergantian korpus, preview
PDF hash/halaman/tampering, dan bukti retrieval saat cache miss. Suite parser
isolated tidak diulang. Tidak ada API berbayar, parser ulang, PDF/dependensi baru,
penghapusan/pemindahan atau perubahan label/model/threshold. Bukti lokal ada di
manifest/app-test/profiles-check/hybrid-smoke dan summary folder UI baru.

**Status:** integrasi RAG KB penuh ke UI selesai dan dapat digunakan. Jawaban baru
berbayar belum diuji ulang sesi ini; jalur paid mock/regresi tetap lulus. Akurasi
umum/retrieval semua jenis pertanyaan belum dibuktikan. Agenda berikut mengikuti
masalah penggunaan nyata; eksperimen verifier tambahan tidak menjadi prasyarat
penggunaan RAG. Parasuraman held dan tiga TXT belum berpeta halaman tetap terbuka.

## Jawaban KB dengan evaluasi RAGAS opsional, 2026-11-21

Perubahan arah produk yang disetujui pengguna sudah diterapkan: jawaban bersitasi
tampil dahulu; tombol **Evaluasi kualitas** menghitung Faithfulness dan Response
Relevancy. MiniCheck dipindahkan ke diagnostik opsional dan tidak otomatis berjalan
pada query baru. Context Recall tetap batch dengan acuan. Sumber tetap KB saat ini;
tidak ada perubahan skema, ID/sitasi, model, threshold, label, atau dependensi.

Evaluator S5 isolated menggunakan judge/cache/batas yang sudah ada dan embedding lokal
offline melalui environment utama. Izin API evaluasi terpisah, default mati, maksimal
lima request/1.024 token output per request. Seluruh konteks generation termasuk yang
tidak disitasi dibekukan bersama hash sumber/input/config, seed, model/library/backend,
traces dan usage pada run baru `paths.cache_dir/answer-quality/`. Jawaban tampilan
dicocokkan dengan sumber kanonis. Kegagalan/cache miss menghasilkan null, bukan nol;
hasil/izin evaluasi direset ketika jawaban atau korpus berubah.

Setelah listrik padam, perubahan tersimpan diperiksa dan suite dijalankan ulang:
**590 test utama lulus, satu modul RAGAS dilewati; 13 test adapter RAGAS isolated
lulus; Ruff lint/format bersih**. Test mencakup konteks tidak disitasi, input/source
tampering, subprocess/timeout, cache-only, relevancy negatif, replay, pemisahan izin,
reset hasil, kegagalan evaluasi yang mempertahankan jawaban, dan isolasi MiniCheck.
Provider pada test dimock. Tidak ada request API berbayar baru pada implementasi ini.
Smoke AppTest KB penuh membuka jawaban tersimpan, menjalankan worker RAGAS asli
tanpa izin API, mempertahankan jawaban ketika skor null/cache miss, serta membuka
preview/unduhan PDF. Bridge embedding offline nyata menghasilkan vektor 768 dimensi
ternormalisasi; hash database sumber identik sebelum/sesudah. Bukti lokal:
`data/skripsi/ui-local/2026-11-21T08-16-45Z_07d296/quality-smoke.json`.
Server Streamlit dipulihkan di 127.0.0.1:8501, health ok. Pemeriksaan interaksi
memakai AppTest; pemeriksaan visual browser/mobile tidak diulang. Desain/CSS tetap.
Suite parser isolated tidak diulang. Skor AI bukan akurasi manusia; evaluasi API nyata
untuk fitur baru belum dijalankan dan tidak memakai ulang jatah batch sebelumnya.

## Audit cleanup finishing, 2026-11-21

Logger yang tidak dipakai pada evaluator kualitas dihapus. README diringkas dan
diselaraskan dengan KB penuh, alur jawaban/RAGAS/MiniCheck opsional, izin API,
dan batas hasil saat ini. OVERVIEW menandai rancangan awal agar tidak disalahartikan
sebagai status runtime. Tautan lokal kedua dokumen diperiksa dan valid.

Pemeriksaan referensi nama melalui AST pada source/test/script evaluasi tidak menemukan
definisi top-level tanpa referensi; ini audit statis terbatas, bukan bukti seluruh
kode diperlukan saat runtime. Modul historis tetap memiliki caller atau test dan
tidak dihapus. Tes ulang: 590 utama/1 skipped, 13 adapter RAGAS isolated lulus;
Ruff lint/format dan diff check bersih, nol API berbayar.

Kandidat penghapusan terbatas pada 148 file cache pytest/Ruff dan bytecode di 13
folder (2.036.731 byte), dirinci dalam
`data/cleanup-audit/2026-11-21T09-56-21Z/candidates.md` dan `candidates.json`.
Pengguna menyetujui penghapusan daftar konkret. Seluruh 148 file dalam daftar
sudah tidak ada setelah penghapusan nonrekursif; folder cache kosong dibiarkan.
Path absolut diperiksa berada dalam workspace dan bukan reparse point.
Bukti pelaksanaan: `deletion-receipt.json` pada folder audit yang sama.
Suite tidak diulang untuk penghapusan cache saja; hasil 590+13 di atas tetap
hasil verifikasi kode terakhir. Cache/bytecode dapat dibuat ulang saat alat berjalan.
Korpus, cache model/API, hasil eksperimen, environment, dan secret tidak masuk daftar.

Pengguna kemudian menyetujui pembersihan script eksperimen yang diaudit. Sebanyak
23 script lokal (150.098 byte) dihapus: 15 salinan source RAGAS untuk inspeksi,
enam script QA UI pilot, `quality-smoke.py`, dan launcher `open-ui.ps1` lama.
Daftar konkret dan receipt berada pada `script-candidates.md`/`.json` dan
`script-deletion-receipt.json` dalam folder audit yang sama. Semua target
terverifikasi tidak ada; penghapusan nonrekursif setelah validasi path dan ukuran.
Script runtime, pembentukan KB/replay, serta hasil laporan tetap dipertahankan.
Pemeriksaan QA lama tidak lagi dapat diulang persis dengan script yang dihapus.
Sesudah penghapusan script, 590 test utama (satu modul skipped) dan 13 test RAGAS
isolated lulus kembali; Ruff lint/format dan diff check bersih. Pengujian memakai
`PYTHONDONTWRITEBYTECODE=1`, pytest tanpa cacheprovider, serta Ruff tanpa cache.
Tidak ada API berbayar baru atau perubahan perilaku runtime.

## Ditunda

- Sinkronisasi langsung akun Mendeley; cukup ekspor `.bib` dan PDF lokal dahulu.
- Pencarian internet bebas saat menjawab, scraping paywall, dan unduhan tanpa lisensi jelas.
- Penggantian parser runtime menunggu hasil pilot Docling dan perbaikan kasus gagal;
  fine-tuning serta refactor besar tetap ditunda tanpa kebutuhan terukur.
- Generator tambahan, voting tiga model, dan regenerasi otomatis tanpa bukti manfaat.

## Catatan pelaksanaan

Untuk setiap tahap, isi: tanggal, perubahan, perintah/hasil verifikasi, lokasi
artefak lokal, keputusan/persetujuan, serta pekerjaan yang masih terbuka.
Centang hanya tugas yang benar-benar selesai; daftar rencana bukan bukti fitur tersedia.

2026-11-19: dokumen rencana dibuat dan pemeriksaan leksikal `.bib` dilakukan.
Dilanjutkan dengan penetapan S0, impor/replay S1, lalu unduhan/replay S2 sesuai
persetujuan sumber/batas pilot. Lima PDF sudah menjadi indeks S3; perluasan
bahasa/koleksi masih terbuka. S4 menghubungkan pilot ke Streamlit dan menguji
kontrak QA dengan mock; agenda berikutnya S5 tanpa perubahan model runtime
sebelum evaluasi serta izin batch berbayar baru ditetapkan.
