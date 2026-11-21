# AGENTS.md

Panduan agent untuk Evidence-Based Research Assistant, sistem RAG lokal dengan sitasi per klaim.

## 1. Proyek

Arah aktif: korpus referensi skripsi dari ekspor Mendeley, terpisah dari benchmark MVP.
82 referensi menjadi kandidat audit. Input lokal di `data/reference-skripsi/`: 41 PDF + 3 TXT dan manifest 44 entri;
seluruh PDF sudah diproses sebagai koleksi lokal dengan label sumber/lisensi.
KB lokal terbaru: 41 PDF/746 halaman terdaftar; 40 searchable, 2.514 chunk/vektor/FTS.
Scan Parasuraman belum memiliki chunk lolos kualitas; tiga TXT belum berpeta halaman.
Bibliografi KB turunan berisi 83 referensi setelah pencatatan Szeghalmy; sumber Mendeley 82 tetap utuh.
Koleksi PDF pengguna boleh diproses lokal meski DOI/lisensi belum terverifikasi, sesuai instruksi 2026-11-20.
Status sumber/lisensi menjadi label, bukan penghalang admission. Downloader lama tetap memakai syarat lisensi.
Bahasa Indonesia/Inggris harus diuji; gate kualitas parsing tetap berlaku.

Baca sesuai pekerjaan:

- [ARCHITECTURE.md](ARCHITECTURE.md): kontrak data, ID/sitasi, dan perilaku pipeline.
- [USAGE.md](USAGE.md): setup, perintah, dan troubleshooting.
- [KB-PREPARATION.md](KB-PREPARATION.md): alur korpus, gate kualitas, dan persiapan batch.
- [TASKS-SKRIPSI.md](TASKS-SKRIPSI.md): scope aktif, persetujuan, hasil, dan pekerjaan tersisa.
- [TASKS.md](TASKS.md): riwayat MVP dan verifikasi; bukan daftar instruksi aktif setiap sesi.
- [OVERVIEW.md](OVERVIEW.md): tujuan produk; [DESIGN.md](DESIGN.md): desain visual, baca untuk perubahan UI.

Jika kode dan dokumen bertentangan, periksa sumber dan tandai ketidaksesuaian; jangan menebak.
Jangan menambah riwayat eksperimen panjang ke dokumen ini; simpan pada kedua file TASKS.

## 2. Perintah dan environment

Jalankan dari root repo memakai Python `.venv` langsung. **Jangan `uv sync`/`uv run` pada environment CUDA saat ini**:
Torch dipasang manual dan sumber CUDA belum diselaraskan dengan lockfile. Launcher `pytest.exe` diblokir Windows.

```powershell
.venv/Scripts/python.exe -m pytest -q
.venv/Scripts/python.exe -m ruff check .
.venv/Scripts/python.exe -m ruff format --check .
```

Docling terisolasi di `data/skripsi/docling-pilot/.venv`, lock `eval/docling-requirements.lock`.
RAGAS terisolasi di `data/skripsi/s5-ragas/.venv`, lock `eval/ragas-requirements.lock`.
Jangan memasang keduanya ke `.venv` utama atau menyinkronkan environment satu sama lain.
Shared cache model boleh dipakai. Uji encoding GPU harus memakai cache baru agar membuktikan inference nyata.

Status operasional terakhir (2026-11-21):

| Bagian | Status |
|---|---|
| Korpus/UI aktif | `configs/skripsi-local.yaml`: KB Docling penuh, 41 PDF/40 searchable, 2.514 chunk; pilot lima PDF opsional |
| Parser kandidat | Docling 2.151.1, Heron/TableFormer accurate/EasyOCR id/en; `do_cell_matching=True` |
| Snapshot Docling awal | 3 PDF/41 halaman, 131 chunk/vektor/FTS; 32/55 tabel searchable, 23 ditahan |
| Pilot input lokal terbaru | Aufar/Dewi/Koto2020: 34 halaman, 118 chunk/vektor/FTS; 9/20 tabel searchable, 11 ditahan; default hybrid khusus snapshot ini |
| KB kandidat tahap 1 | `data/skripsi/kb-build/2026-11-20T01-06-05Z_f81029/kb/`: 17 PDF, 903 chunk; 44 tabel searchable/100 ditahan |
| KB kandidat tahap 2 | `data/skripsi/kb-expansion/2026-11-20T01-33-36Z_3f61ac/kb/`: 18 PDF, 974 chunk; 48 tabel searchable/104 ditahan; replay identik |
| KB koleksi lokal lengkap | `data/skripsi/kb-local-all/2026-11-20T01-59-17Z_c95c3b/kb/`: 41 PDF terdaftar/40 searchable, 2.514 chunk; 100 tabel searchable/208 ditahan |
| Runtime jawaban/evaluasi | DeepSeek Flash non-thinking; RAGAS dan diagnostik MiniCheck opsional setelah jawaban; JEV `jev-1.14` belum dipromosikan |
| Verifikasi terakhir kode | 590 test utama + 13 test RAGAS isolated lulus; satu modul RAGAS dilewati di environment utama; Ruff bersih; suite parser isolated tidak diulang |

Snapshot/parser baru memakai database/index/run baru. Jangan memasangkan laporan bibliografi S3 dengan subset Docling.
Jangan memakai chunker PyMuPDF pada artefak Docling. OCR tanpa pembanding native dan tabel ambigu tetap ditahan.
Tidak wajib mengoreksi manual seluruh paper. Native Indonesia diuji terbatas; scan asli sudah diekstrak tetapi belum searchable. UI katalog/label
diuji AppTest; retrieval dan generation KB penuh sudah diuji pada pilot acuan AI terbatas.
Akurasi manusia/kesiapan umum belum dibuktikan; MiniCheck menunjukkan kandidat false negative.
`prepare-local` default maksimal tiga PDF; batch lokal memakai `--max-documents` eksplisit dan batas config.
Jalur default tetap memerlukan bukti identitas/lisensi berhash. `--local-collection` hanya untuk
koleksi pengguna dengan policy manifest eksplisit; status unverified disimpan, bukan diklaim OA.
Tidak mengunduh PDF. Lisensi dataset bukan lisensi artikel.
Bukti terbaru: TASKS-SKRIPSI.md bagian refinement retrieval, pilot generation KB penuh,
dan diagnosis verifier offline; belum ada transformasi verifier dipromosikan;
rincian run tidak disalin di sini.

## 3. Struktur repo

`src/rag/`: ingestion, parsing, chunking, indexing, retrieval, generation, verification, evaluation, ui.
`configs/`: konfigurasi; `tests/`: test; `eval/`: dataset/laporan evaluasi; `data/`: korpus/cache lokal, tidak di-commit.

## 4. Aturan inti (invarian proyek)

1. Grounding ketat: jawaban hanya dari chunk hasil retrieval; jangan memasukkan pengetahuan luar ke konteks jawaban.
2. Setiap klaim wajib bersitasi ID chunk valid; tanpa bukti harus dikeluarkan atau dilabeli "tidak ada bukti".
3. Skema SQL dan format ID/sitasi tetap. Jangan mengubahnya tanpa persetujuan eksplisit.
4. Simpan seed, model/revision, config/hash, dan run baru; jangan menimpa hasil lama.
5. Jangan mengubah dataset/label agar skor membaik. Kesamaan string ID tidak memindahkan label ke snapshot baru.

## 5. Data dan lisensi

- Simpan identitas, versi/hash, sumber, dan lisensi setiap PDF; akses publik saja bukan bukti lisensi.
- Jangan commit PDF, full text/abstrak korpus, indeks, atau isi `data/`.
- Jangan mengunduh PDF tambahan: pengguna menyiapkannya sendiri. Inventaris sebelum ingestion batch.
- Pilot downloader lama memakai 26/30 request dan seluruh lima slot PDF; sisa request bukan izin PDF/batch baru.

## 6. Secret dan biaya API

- Key hanya dari environment/`.env`; jangan hardcode, mencetak, atau commit. Perbarui `.env.example` jika menambah variabel.
- Test memakai mock/fixture, tanpa API berbayar. Default generation/judge hanya cache; cache miss bukan abstention.
- Request nyata harus eksplisit, berizin, dan berbatas jumlah panggilan/token; hitung kegagalan dan retry format dalam jatah.
- Batch M6/S5 sudah selesai. Jangan mengulang fase berbayar, mereset ledger/marker, atau menganggap sisa jatah sebagai izin baru.
- Setelah crash, periksa receipt/cache dan replay tanpa API dahulu. JEV harus tetap versi eksplisit `jev-1.14`.

## 7. Konvensi kode

Python 3.11+, type hints fungsi publik, fungsi kecil, logika terpisah dari I/O. Gunakan `logging`, bukan `print`.
Parameter eksperimen masuk config; Ruff memakai 100 kolom/py311. Komentar menjelaskan alasan, bukan mengulang kode.

## 8. Dependensi

Jangan menambah dependensi/sumber data atau mengganti versi mayor tanpa konfirmasi. Kunci versi pada lockfile yang tepat.

## 9. Testing

Test chunking, fusion, klaim/sitasi, dan ID; mock model/jaringan. Test GPU memakai marker `gpu`.
Bug sebaiknya mempunyai test reproduksi. Setelah perubahan kode, jalankan pytest serta Ruff lint/format.

## 10. Kapan harus bertanya dulu

Minta persetujuan sebelum mengubah skema/ID/sitasi/struktur folder utama, menambah dependensi/sumber data,
menghapus atau memindahkan file/data/hasil, batch API berbayar atau proses lama, dan refactor besar di luar tugas.
Untuk penghapusan/pemindahan, ajukan daftar file konkret dahulu. Jika ambigu, nyatakan asumsi konservatif.

## 11. Alur kerja

Kerjakan satu tugas kecil; baca caller, config, test, dan dokumen terkait sebelum menulis. Pertahankan perubahan pengguna.
Hindari cleanup di luar scope. Perbarui DESIGN.md hanya bila keputusan visual berubah; pesan commit singkat/deskriptif.

## 12. Definisi selesai

Perilaku diuji sesuai scope; setelah perubahan kode pytest dan Ruff lulus. Tidak ada secret/korpus/file besar ikut commit.
Perbarui dokumentasi yang relevan. Nyatakan apa yang dijalankan, belum diuji, dan batas hasil; jangan mengklaim sukses tanpa bukti.
Agreement antarmodel/review AI bukan akurasi manusia. Label manusia M6 satu paper dan audit acuan S5 bukan label klaim generation baru.
Acuan 018 revisi yang diterima tetap terpisah dari acuan/dataset/skor S5 lama; audit kecil sudah ditutup.
