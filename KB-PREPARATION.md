# Persiapan knowledge base referensi skripsi

Status: **seluruh 41 PDF diproses; 40 searchable, scan Parasuraman menunggu validasi OCR**, 2026-11-20.
Pengguna menyetujui kelanjutan setelah penjelasan penahanan tabel dan meminta
handoff untuk sesi baru. Parser aktif masih PyMuPDF; dokumen ini tidak berarti
promosi Docling ke parser aktif sudah disetujui. Implementasi pilot penuh
tercatat pada pembaruan di bawah; bagian handoff lama adalah kondisi sebelum
implementasi. Kontrak skema/ID/sitasi tetap mengikuti ARCHITECTURE.md.

**Arah terbaru pengguna (2026-11-20):** proses seluruh 41 PDF lokal terlebih dahulu.
DOI/lisensi yang belum terverifikasi menjadi metadata/label, bukan blocker admission.
Aturan OA lama di bawah berlaku untuk downloader dan run historis; koleksi pengguna
memakai opt-in `user_local_collection`. Gate kualitas, halaman dan hash tetap.
Tidak mengunduh PDF, menambah dependensi/API, atau memasukkan OCR rusak sebagai bukti.

Tujuan: mengubah PDF referensi menjadi bukti yang dapat dicari, dengan identitas
dokumen, halaman PDF, kutipan, dan hubungan tabel yang dapat ditelusuri.

**Fokus aktif KB:** seluruh 41 PDF/746 halaman telah diproses pada snapshot lokal baru.
40 PDF menghasilkan 2.514 chunk/vektor/FTS; 100/308 tabel searchable, 208 ditahan.
Parasuraman1988 telah diekstrak OCR tetapi nol chunk lolos pembanding/kualitas.
DOI/lisensi bukan blocker; 23 sumber baru memakai label belum terverifikasi.
Tiga TXT belum berpeta halaman. Artefak: `data/skripsi/kb-local-all/2026-11-20T01-59-17Z_c95c3b/`.
Evaluasi retrieval offline snapshot penuh selesai pada 36 acuan AI sementara:
hybrid 25/32 target top-8, reranker 28/32. Perluasan kandidat 100 tetap 28/32
dengan satu pemulihan/satu regresi, sehingga tidak dipromosikan. Replay identik;
generation umum belum siap menurut gate target yang dibekukan pada baseline.
Refinement offline berikutnya memakai petunjuk citation key/tabel serta token teknis:
32/32 target development top-8 dan 16/16 validasi baru, replay identik tanpa regresi.
Ini eksperimen lokal/acuan AI, belum perubahan retriever/UI aktif atau bukti akurasi manusia.
Pilot DeepSeek delapan pertanyaan sudah diizinkan dan selesai: 7 request, enam jawaban
bersitasi dan dua kontrol nol klaim. MiniCheck mendukung 6/16 pasangan, menolak 10;
audit sumber AI menemukan kandidat false negative. Label asli tetap; akurasi manusia belum diuji.
Diagnosis offline 86 probe/replay mengonfirmasi sensitivitas bahasa/atribusi pada
contoh tertentu; varian tabel menerima satu angka salah. Tidak ada transformasi
verifier dipromosikan. Hasil lokal dan batas pada TASKS-SKRIPSI.md bagian diagnosis verifier.
Rincian dan batas pada TASKS-SKRIPSI.md bagian refinement retrieval. UI/default parser
lama belum dipromosikan; JEV/judge tidak dipanggil. Detail pada TASKS-SKRIPSI.md bagian pilot generation.
Tahap 1/2 berikut adalah riwayat sebelum instruksi koleksi lokal penuh.

**Perluasan tahap 2:** BERT/Devlin2019 lolos identitas dan lisensi artikel dari ACL.
Snapshot terpisah 18 PDF/293 halaman menghasilkan 974 chunk/vektor/FTS;
23 PDF dan tiga TXT masih tertahan. Artefak: `data/skripsi/kb-expansion/2026-11-20T01-33-36Z_3f61ac/`.
Empat halaman penerbit diperiksa ulang, bukan audit ulang seluruh dokumen.
Segura-Bedmar memiliki CC BY 4.0 tetapi DOI belum terverifikasi untuk kontrak
admission saat ini; Maretta timeout, kandidat halaman Hellwig 404.

**Pembaruan implementasi:** `rag.parsing.docling_pipeline extract/build`,
`docling_adapter`, dan `rag.chunking.docling` tersedia tanpa perubahan SQL/ID.
Konversi serial terpisah memakai maksimal tiga PDF lengkap per pemanggilan; keputusan ditahan
dikeluarkan sebelum SQL/index, artefak asli tetap disimpan. Sel tabel diperiksa
terhadap teks native serta geometri; caption/header/catatan/halaman dijaga.
Header bertingkat, rowspan label baris eksplisit, row-section penuh, dan
multiline yang lolos pemeriksaan kini didukung. OCR tanpa pembanding native
dan span/body/header ambigu tetap ditahan. Ambang narasi
0,8 belum dikalibrasi manusia. Parser/runtime aktif tetap PyMuPDF.
Perintah aktual di USAGE.md; bukti dan batas uji lengkap di TASKS-SKRIPSI.md.

Audit tabel lanjutan: **32/55 tabel searchable, 23 ditahan**, dengan 131
chunk/vektor/FTS pada snapshot baru; hasil awal 19/55 dan 111 chunk tetap.
Sebanyak 17 tabel lama dipulihkan, empat tabel lain kini ditahan karena native
apostrophe rusak. `do_cell_matching=False` tidak dipromosikan setelah uji enam
halaman. Pemeriksaan dilakukan AI, bukan gold manusia. Parser aktif tetap.

**Input pengguna tersedia (2026-11-20):** `data/reference-skripsi/` memuat
41 PDF + 3 TXT dan manifest 44 entri, total 746 halaman PDF. Audit lokal di
`data/skripsi/local-inventory/2026-11-20T00-23-38Z_b7dd4c/` mencatat hash,
metadata, kebutuhan OCR, dan petunjuk lisensi; belum admission atau indexing.
TXT ditahan karena belum memiliki pemetaan halaman PDF. Agenda kini verifikasi
identitas/lisensi lalu pilot baru untuk bahasa Indonesia/scan yang lolos syarat.

**Pilot input lokal selesai:** Aufar2023/Dewi2025/Koto2020, 34 halaman,
115 chunk/vektor/FTS; 9/20 tabel searchable dan 11 ditahan. Native Indonesia
tercakup terbatas; scan Parasuraman ditunda karena lisensi belum jelas. Gate
baris diperketat setelah spot visual menemukan teks salah baris yang sebelumnya
lolos pembanding native. Enam query AI pada empat mode menemukan target 21/24;
replay identik bukan akurasi manusia. Parser aktif tetap. Bukti di TASKS-SKRIPSI.md.

Refinement pilot: dua chunk narasi overlength dipulihkan melalui jendela berbatas
tokenizer, menjadi 118 chunk/vektor/FTS; tabel tetap 9 lolos/11 ditahan. Config
dibekukan khusus tiga PDF dengan default hybrid; reranker tetap pembanding karena
menurunkan dua target tabel. Header terpecah pada layout sumber dipertahankan tanpa
menebak sambungan kata. Batch penuh dan promosi parser belum diputuskan.

## 1. Kondisi awal dan cakupan

- Bibliografi memiliki 82 referensi kanonis. Rencana 44 PDF belum merupakan
  inventaris yang selesai diverifikasi; input kini tersedia seperti pembaruan di atas.
- Pilot aktif: 5 PDF, 66 halaman, 310 chunk/vektor/FTS, parser PyMuPDF.
- Pilot halaman Docling awal mencakup tiga halaman dan kontrol raster.
  Uji lanjutan kini mencakup tiga PDF lengkap/41 halaman pada snapshot baru;
  penggabungan baris dan label OCR tetap alasan penahanan, bukan koreksi otomatis.
- Adapter opt-in ke chunk/indeks tersedia; runtime aktif belum dipromosikan.
- Pengukuran akurasi manusia ditunda. Audit kecil sebelumnya tetap ditutup.
- PDF yang dimiliki pengguna tetap harus diperiksa identitas dan lisensinya.
  Aturan saat ini hanya menerima full text open access berlisensi jelas.

## 2. Alur yang disepakati

| Tahap | Pekerjaan | Hasil dan syarat lanjut |
|---|---|---|
| Inventaris | Baca folder PDF dan ekspor Mendeley; hitung hash, duplikat, halaman; cocokkan judul/DOI/versi/lisensi | Manifest seluruh file dan status setiap referensi; konflik ditahan |
| Ingestion | Daftarkan PDF yang identitas dan lisensinya lolos | Snapshot sumber dengan provenance; file asli tidak diubah |
| Parsing | Docling mengekstrak teks, layout, dan tabel; OCR selektif untuk bagian scan | Artefak terstruktur dengan halaman asli dan versi model/config |
| Pemeriksaan ekstraksi | PyMuPDF membaca teks asli PDF digital; cek struktur dan perbedaan hasil | Laporan kualitas per halaman/blok/tabel; hasil meragukan ditahan |
| Chunking | Buat chunk narasi dan kelompok baris tabel yang mempertahankan konteks | Chunk yang lolos pemeriksaan, tanpa kehilangan header/satuan/halaman |
| Indexing | Bangun vektor dan FTS dari chunk yang sama | Jumlah/ID/hash konsisten pada SQLite, vektor, dan FTS |
| Uji aplikasi | Retrieval, kutipan, halaman, cache/replay, dan penolakan saat bukti kurang | Korpus baru siap dipakai setelah pemeriksaan alur utuh |

Parsing dan OCR dilakukan saat persiapan korpus, bukan saat pengguna bertanya.
Jumlah dokumen memengaruhi waktu proses; pemrosesan awal dilakukan serial dengan
batch halaman satu sesuai pilot GPU. Ukuran halaman/dokumen tetap dapat memicu
kehabisan memori; kegagalan dicatat dan tidak dianggap sukses.

## 3. Pembagian peran parser

- **Docling:** kandidat parser utama, memakai Heron, TableFormer accurate,
  serta EasyOCR Indonesia–Inggris yang sudah diuji secara terbatas.
- **PyMuPDF:** pembaca PDF, hash/render/halaman, dan pembanding layer teks asli
  pada PDF digital. Ia bukan validator kebenaran hubungan sel tabel.
- **OCR:** selektif pada bagian yang tidak memiliki layer teks memadai. Tidak
  memaksa seluruh PDF digital menjadi gambar. Bahasa harus diuji pada sampel nyata.
- Tidak menjalankan beberapa parser lalu memilih hasil secara acak, voting,
  atau menganggap kesepakatan dua parser sebagai bukti bahwa tabel benar.
- Jika kelak mencoba mesin OCR/model lain, tetapkan kasus gagal yang ingin
  diperbaiki dan periksa lisensi/dependensi sebelum menambahkannya.

## 4. Aturan kualitas dan kebutuhan koreksi manual

Default yang disepakati: **proses otomatis; hasil yang meragukan ditahan**. Tidak ada
kewajiban mengoreksi seluruh 44 paper. Tinjauan pengguna hanya opsional untuk
membuka bukti tertentu yang ditahan. Hasil yang ditahan tetap tercatat.

Pemeriksaan otomatis meliputi halaman kosong/tidak terbaca, karakter rusak,
urutan halaman, cakupan teks, struktur header/baris/kolom, rentang sel, dan
perbedaan angka/teks terhadap layer asli jika tersedia. Sel gabungan atau
header bertingkat menandai kompleksitas; tidak otomatis membuktikan kesalahan.
Ambang kuantitatif perlu ditetapkan pada sampel, bukan ditebak sebagai jaminan.

Keputusan per blok dicatat pada laporan kualitas terpisah: lolos pemeriksaan,
ditahan, atau gagal. Ini usulan artefak audit, bukan penambahan kolom SQL.
Blok ditahan/gagal harus dikeluarkan sebelum penulisan chunk yang dapat dicari;
banner peringatan saja tidak cukup untuk mencegahnya dipakai sebagai bukti.
Narasi yang lolos pada paper yang sama tetap boleh dipakai.

Tabel meragukan tidak boleh menjadi sumber klaim angka/perbandingan otomatis.
Jika narasi lain tidak memberi bukti yang cukup, aplikasi menyatakan bukti
belum cukup. Jangan diam-diam membetulkan angka atau label agar tampak benar.

Pemeriksaan otomatis bisa melewatkan kesalahan. Status lolos berarti lolos
pemeriksaan yang tersedia, bukan akurasi manusia atau jaminan seluruh isi benar.
Sebelum batch besar, uji kasus gagal yang sudah diketahui: baris IndoLEM/SmSA
Koto serta header/label scan Scaria. Kegagalan dapat ditahan bila belum teratasi.

## 5. Kontrak hasil parsing dan chunk

- PDF asli, DOI/citation key, versi, hash, lisensi, dan pemetaan halaman tetap
  tersedia. Nomor sitasi memakai halaman PDF asli, bukan halaman cetak atau
  nomor halaman pada kontrol scan buatan.
- Tabel mempertahankan caption/identitas, header, nama baris, satuan, catatan,
  dan halaman. Tabel panjang dipotong per kelompok baris dengan header diulang.
- Kelompok tabel yang tidak muat batas tokenizer ditahan atau dipecah lebih
  lanjut; tidak dipotong diam-diam. Penghilangan blok/teks harus dilaporkan.
- JSON terstruktur dan HTML/Markdown menjadi artefak lokal. Adapter opt-in telah
  diuji ke format chunk lama pada snapshot tiga PDF terpisah; batch penuh belum diuji.
- Skema SQL dan format ID/sitasi tetap mengikuti ARCHITECTURE.md. Jika kontrak
  ini tidak cukup untuk implementasi, ajukan perubahan secara eksplisit dahulu.
- Gunakan database/index/run baru untuk korpus hasil parser baru. ID harus
  selalu terikat snapshot korpus; kesamaan string ID tidak memindahkan label
  atau membuktikan teks chunk sama. Label/skor M6/S5 tetap pada snapshot asal.

## 6. Peta codebase dan penataan file

| Kelompok | Lokasi saat ini | Perlakuan |
|---|---|---|
| Pipeline dan aplikasi | `src/rag/ingestion`, `parsing`, `chunking`, `indexing`, `retrieval`, `generation`, `verification`, `ui` | Pertahankan batas modul dan jalur yang sudah dipakai |
| Eksperimen/evaluasi | `src/rag/evaluation/docling.py`, `ragas.py`, `decisions.py`, serta runner evaluasi lain | Tetap eksperimen; adapter opt-in berada di parsing/chunking |
| Config | `configs/config.yaml`, `skripsi-pilot.yaml`, `skripsi-download.yaml`, `docling-pilot.yaml` | Nyatakan tujuan dan dataset tiap config; jangan campur benchmark dengan skripsi |
| Lingkungan khusus | Lock Docling/RAGAS di `eval/`; environment di `data/skripsi/` | Pertahankan isolasi; jangan menyinkronkan `.venv` CUDA utama |
| Bukti historis | `eval/results/`, dataset/manifes lama, `data/skripsi/pilot-v1/`, `s5-ragas/`, `docling-pilot/` | Pertahankan hasil dan provenance; ringkas aksesnya lewat indeks dokumentasi |
| Dokumentasi | `ARCHITECTURE.md`, `USAGE.md`, `TASKS.md`, `TASKS-SKRIPSI.md` | Arsitektur, perintah, dan riwayat memiliki peran berbeda; hindari status yang bertentangan |

Inventaris awal belum membuktikan ada file yang aman dihapus. Banyak file lama
merupakan bukti reproduksi, fixture, atau dependensi jalur benchmark.

Urutan merapikan kode setelah kontrak disepakati:

1. Catat perubahan Git yang belum disimpan dan inventaris caller, config, test,
   serta tautan dokumentasi. Jangan reset perubahan pengguna.
2. Buat daftar entry point aktif dan indeks laporan historis tanpa memindahkan data.
3. Pisahkan adapter parsing produksi dari runner eksperimen melalui batas modul
   yang sudah ada. Jangan memindahkan eksperimen mentah langsung ke runtime.
4. Tandai kandidat file tidak terpakai hanya setelah referensi/import dan jalurnya
   diperiksa. Belum ada kandidat penghapusan yang ditetapkan pada draf ini.
5. Ajukan daftar file persis beserta alasan sebelum penghapusan atau pemindahan.
   Hindari refactor besar sekaligus dengan pergantian parser.

## 7. Urutan pelaksanaan sebelum 44 PDF

- [x] Sepakati proses, khususnya penahanan tabel meragukan tanpa koreksi wajib.
- [x] Inventaris awal folder `data/reference-skripsi/`: 41 PDF + 3 TXT,
  hash/halaman/duplikat dan kecocokan manifest diperiksa secara offline.
- [ ] Selesaikan verifikasi identitas, versi, lisensi, dan bahasa; audit awal
  bukan izin admission. Tiga TXT belum memiliki pemetaan halaman PDF.
- [x] Admission dan pilot tiga PDF lokal yang terverifikasi, termasuk native Indonesia;
  scan asli tetap tertunda, retrieval belum dinyatakan layak batch dari smoke saja.
- [ ] Tetapkan manifest/config korpus baru dan versi model yang digunakan.
- [x] Implementasikan adapter Docling serta pemeriksaan/penahanan blok dengan test.
- [x] Implementasikan chunk tabel yang mempertahankan header dan halaman.
- [x] Uji tiga dokumen lengkap yang tersedia: Koto/Wilie/Scaria, 41 halaman,
  111 chunk/vektor/FTS pada snapshot baru. Scan asli/full text Indonesia belum tersedia.
- [x] Periksa replay offline, alokasi/reservasi Torch, provenance, dan konsistensi
  indeks. Peak GPU keseluruhan/RAM proses belum diukur pada run penuh ini.
- [ ] Bekukan konfigurasi dan daftar input; baru lanjutkan parsing seluruh batch.

Parsing penuh terbatas tiga PDF pilot lama sudah dijalankan; tidak ada perubahan parser
aktif, penghapusan file, atau API berbayar baru. Test dan Ruff wajib setelah
perubahan kode. Rincian uji/batas ada di TASKS-SKRIPSI.md bagian adapter penuh.

## 8. Handoff sebelum implementasi (riwayat)

Pengguna sedang menyelesaikan unduhan rencana 44 paper dan akan memberitahukan
path foldernya. Jumlah, kelengkapan, bahasa, dan lisensi file belum diperiksa.
Lokasi yang disarankan adalah `data/skripsi/incoming-pdfs/`, tetapi path aktual
tetap menunggu pengguna. Jangan menganggap folder tersebut sudah berisi PDF.
Jangan meneruskan rencana unduhan otomatis batch kedua atau mencari PDF ulang.

Pekerjaan yang dapat dimulai tanpa folder 44 PDF:

1. Baca AGENTS.md, dokumen ini, ARCHITECTURE.md, USAGE.md, TASKS-SKRIPSI.md,
   dan handoff/hasil Docling di TASKS.md. Periksa perubahan Git yang sudah ada.
2. Gunakan peta entry point di bawah untuk membatasi perubahan. Mulai dari
   adapter hasil Docling menuju format parsing/chunk yang ada, dengan fixture
   sintetis dan penolakan pemetaan halaman yang tidak jelas.
3. Tambahkan pemeriksaan kualitas serta pengecualian blok/tabel yang ditahan
   sebelum chunk dapat dicari. Pemeriksaan otomatis bukan jaminan akurasi.
4. Tambahkan pemotongan tabel per kelompok baris dengan header/caption/halaman
   tetap, sesuai batas tokenizer; tanpa truncation atau kehilangan diam-diam.
5. Uji tiga PDF pilot lengkap pada database/index baru. Jangan menyatakan
   berhasil sebelum benar-benar dijalankan; kegagalan boleh ditahan dan dilaporkan.

Kerjakan satu perubahan kecil tiap langkah, disertai test dan Ruff. Jangan
memindahkan atau menghapus file lama untuk merapikan tampilan repo. Buat daftar
kandidat beserta caller/test/tautan yang diperiksa jika cleanup memang diperlukan.
Jangan mempromosikan Docling ke runtime sebelum jalur utuh terverifikasi.

Setelah path PDF tersedia, lakukan inventaris sebelum ingestion/parsing batch.
Proses hanya dokumen yang lolos identitas/lisensi. Pekerjaan adapter/test tidak
harus menunggu unduhan pengguna selesai. Tidak ada izin API berbayar baru.

## 9. Entry point dan bukti yang dipertahankan

| Peran | Entry point / file | Catatan |
|---|---|---|
| Impor/cocokkan referensi | `src/rag/ingestion/__main__.py`, `bibliography.py`, `prepare.py` | Gunakan provenance bibliografi; belum ada inventaris folder pengguna |
| Parser aktif | `src/rag/parsing/__main__.py`, `pipeline.py`, `pdf.py` | PyMuPDF dan kontrak ParsedPaper/TextBlock saat ini |
| Eksperimen Docling | `src/rag/evaluation/docling.py`, `configs/docling-pilot.yaml` | Runner halaman/probe; jalur adapter penuh terpisah di parsing/docling_pipeline.py |
| Chunking aktif | `src/rag/chunking/core.py`, `pipeline.py` | Chunking teks aktif; chunk tabel opt-in tersedia di chunking/docling.py |
| Indexing aktif | `src/rag/indexing/__main__.py`, `pipeline.py` | SQLite/FTS/vektor harus cocok dengan snapshot yang sama |
| Aplikasi skripsi | `src/rag/ui/app.py`, `service.py`, `configs/skripsi-pilot.yaml` | Tetap menunjuk korpus pilot sampai korpus baru lolos |
| Uji relevan | `tests/test_docling.py`, `test_parsing.py`, `test_chunking.py`, `test_indexing.py`, `test_ui.py` | Tambahkan kasus adapter/gate/tabel tanpa API berbayar |
| Ringkasan Docling | `data/skripsi/docling-pilot/summary.md` | Enam kasus halaman, 6718 MiB puncak GPU teramati; kesalahan tabel/OCR tetap ada |
| Bukti evaluasi lama | `eval/results/`, `data/skripsi/s5-ragas/` | Pertahankan dataset, label, persetujuan, receipt dan cache |

Verifikasi handoff awal: 492 test utama dan tiga test isolated. Verifikasi
adapter penuh terbaru dicatat di TASKS-SKRIPSI.md; angka handoff bukan hasil
pengujian kode yang baru ditambahkan.
