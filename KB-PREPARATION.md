# Persiapan knowledge base referensi skripsi

Panduan persiapan korpus. Kontrak data: [ARCHITECTURE.md](ARCHITECTURE.md).
Perintah: [USAGE.md](USAGE.md). Run dan hasil: [TASKS-SKRIPSI.md](TASKS-SKRIPSI.md).

## Status aktif

Input `data/reference-skripsi/`: 41 PDF + 3 TXT, manifest 44 entri, 746 halaman PDF.
Seluruh PDF sudah diekstrak pada snapshot
`data/skripsi/kb-local-all/2026-11-20T01-59-17Z_c95c3b/`:
40 searchable, 2.514 chunk/vektor/FTS, 100 tabel searchable dan 208 ditahan.
Parasuraman sudah di-OCR tetapi nol chunk lolos kualitas; tiga TXT belum berpeta halaman.

UI utama memakai KB Docling penuh melalui `configs/skripsi-local.yaml` sejak
2026-11-21. CLI PyMuPDF dan pilot lama tetap terpisah. Handoff lama yang meminta
menunggu folder/implementasi adapter sudah digantikan oleh hasil ini.

## Alur persiapan

| Tahap | Syarat/hasil |
|---|---|
| Inventaris | Hash, duplikat, halaman, judul/DOI/versi, bahasa, dan status setiap file |
| Admission | Manifest/receipt mengikat bibliografi, identitas, hash, halaman dan sumber/lisensi |
| Parsing | Docling isolated, serial maksimal tiga PDF per extract; OCR selektif |
| Gate kualitas | Bandingkan teks native dan geometri; simpan alasan blok lolos/held/gagal |
| Chunking | Narasi berbatas tokenizer; tabel per kelompok baris dengan konteks diulang |
| Indexing | Jumlah/ID/hash SQLite, LanceDB dan FTS harus cocok |
| Uji aplikasi | Retrieval, sitasi/halaman, kontrol tanpa bukti, serta cache/replay |

Parsing/OCR tidak berjalan saat query. Snapshot parser/config baru memakai database,
indeks dan run baru. Raw cache boleh dipakai ulang hanya jika hash PDF/model/backend
cocok; build gabungan menyimpan provenance tiap run dan menghitung ulang gate.
Konversi parsial/gagal tidak dianggap build lengkap.

## Identitas dan lisensi

Jalur default `prepare-local` membutuhkan bukti identitas/lisensi artikel berhash;
DOI, HTML penerbit, halaman PDF atau receipt snapshot harus cocok. Lisensi dataset
bukan lisensi artikel. Default maksimal tiga PDF; batch memakai `--max-documents`
eksplisit di bawah batas config. Database harus baru; sumber tidak diubah.

Instruksi pengguna 2026-11-20 mengizinkan koleksi lokal diproses meski DOI/lisensi
belum terverifikasi. Jalur `--local-collection` membutuhkan manifest dengan
`admission_policy: user_local_collection`. Hash/path/halaman tetap diperiksa;
identitas terverifikasi dipertahankan, sisanya memakai `local:sha256_<hash>` dan
`LicenseRef-UserProvided-Unverified`. Label ini bukan klaim OA atau izin redistribusi.
Downloader lama tetap ketat; jangan mengunduh PDF tambahan.

## Parser, gate, dan chunk

Docling memakai Heron/TableFormer accurate/EasyOCR id/en, CUDA batch satu,
model pinned/offline, dan `do_cell_matching=True`. PyMuPDF membaca/render PDF
serta membandingkan layer native; kesepakatan parser tidak menjamin relasi sel benar.
Jangan menjalankan chunker PyMuPDF pada artefak Docling.

- Halaman sitasi adalah halaman PDF asli 1-indexed, bukan nomor cetak/raster kontrol.
- Narasi overlap tabel tidak boleh lolos sebagai tabel rata. Rumus/gambar/kode
  dan tipe yang belum didukung tidak menjadi bukti.
- Tabel memerlukan caption, header, label baris, grid lengkap, urutan token native,
  dan geometri konsisten. Minus/desimal/tanda baca tetap dipertahankan.
- Header bertingkat, rowspan label eksplisit, row-section penuh dan multiline
  didukung bila valid. Caption/header/catatan/halaman serta konteks kelompok diulang.
- Span ambigu, grid berlubang, salah baris/header, mismatch native dan OCR tanpa
  pembanding ditahan sebelum SQL/index. Narasi valid dari paper yang sama tetap boleh dipakai.
- Satu baris beserta konteks yang tidak muat menahan seluruh tabel. Narasi memakai
  jendela tokenizer tanpa truncation; unit tunggal overlength tetap held.
- `native_word_coverage=0.8` dan `header_center_tolerance=0.25` masih heuristik,
  belum dikalibrasi manusia. Short-drop dan seluruh penahanan dilaporkan.

Default: proses otomatis dan tahan hasil meragukan. Tidak wajib mengoreksi manual
seluruh paper. Status lolos gate bukan jaminan akurasi; jangan membetulkan angka
atau label secara spekulatif. Kasus IndoLEM/SmSA Koto dan OCR Scaria tetap menjadi
acuan kegagalan. ID/label tidak berpindah snapshot hanya karena string-nya sama.

## Entry point dan pekerjaan tersisa

| Peran | Lokasi |
|---|---|
| Bibliografi/admission | `src/rag/ingestion/bibliography.py`, `prepare.py`, `local.py` |
| Konversi/gate | `src/rag/parsing/docling_pipeline.py`, `docling_backend.py`, `docling_adapter.py` |
| Chunk/indeks | `src/rag/chunking/docling.py`, `core.py`, `src/rag/indexing/pipeline.py` |
| UI | `src/rag/ui/app.py`, `service.py`, `configs/skripsi-local.yaml` |
| Uji | `tests/test_docling*.py`, `test_local_admission.py`, `test_chunking.py`, `test_indexing.py`, `test_ui.py` |

Pekerjaan terbuka: kualitas OCR Parasuraman, pemetaan halaman TXT, kalibrasi gate,
evaluasi bahasa/tipe pertanyaan lebih luas, dan validasi manusia sebelum klaim
akurasi atau promosi verifier. Helper refinement retrieval masih eksperimen;
UI tetap memakai empat mode produksi. Perapian UI adalah agenda berikutnya.

Pertahankan environment Docling/RAGAS terpisah, artefak/label lama, dan batas modul.
Penghapusan/pemindahan memerlukan daftar file konkret dan persetujuan; panduan
ini tidak memberi izin cleanup, batch lama, atau API baru.
