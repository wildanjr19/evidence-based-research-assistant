# Evidence-Based Research Assistant

Asisten riset literatur ilmiah yang dirancang untuk menjawab pertanyaan dengan bukti yang bisa ditelusuri sampai ke paper, halaman, dan kutipan aslinya.

Proyek ini memakai Retrieval-Augmented Generation (RAG): sistem mengambil potongan teks (chunk) dari korpus, lalu menyusun jawaban berdasarkan bukti tersebut. Setiap klaim wajib memiliki sitasi chunk yang valid atau diberi label "tidak ada bukti". Ketepatan sitasinya diukur melalui evaluasi.

## Ruang lingkup

Aplikasi menjawab pertanyaan dari **KB referensi skripsi pengguna**, dengan sitasi
per klaim yang dapat dibuka sampai ke kutipan dan halaman PDF asli. Jawaban hanya
memakai chunk hasil retrieval; klaim tanpa bukti diberi label yang sesuai.

KB aktif berisi **41 PDF terdaftar, 40 searchable, dan 2.514 chunk** dari koleksi
lokal pengguna. Bibliografi turunan memuat 83 referensi; ekspor Mendeley sumber
memuat 82 referensi. Satu PDF scan belum menghasilkan chunk yang lolos kualitas,
dan tiga TXT belum berpeta halaman. Status sumber/lisensi dicatat sebagai label;
koleksi ini tidak diklaim seluruhnya open access.

## Alur aplikasi

1. Pilih korpus dan tulis pertanyaan Indonesia atau Inggris.
2. Retrieval mengambil bukti lokal; generator menyusun jawaban bersitasi.
3. Buka sitasi untuk membaca kutipan, halaman PDF, dan lisensi sumber.
4. RAGAS otomatis menghitung Faithfulness dan Response Relevancy di tiap card.
   Buka **Penggunaan token** untuk melihat pemakaian generator/evaluator.
   MiniCheck tersedia sebagai diagnostik opsional.

Jawaban tampil sebelum evaluasi. Skor RAGAS adalah estimasi AI terhadap konteks
atau relevansi, bukan jaminan kebenaran maupun ketepatan setiap sitasi. Context
Recall tersedia pada evaluasi batch yang memiliki jawaban acuan. Evaluasi gagal
atau cache miss ditampilkan sebagai belum tersedia, bukan skor nol.

Parsing dan indeks KB memakai snapshot Docling; retrieval memakai BGE, LanceDB,
dan SQLite FTS5. UI memakai Streamlit, generator aktif DeepSeek Flash. RAGAS
berjalan di environment terpisah, dengan embedding pertanyaan lokal. PDF, teks
korpus, indeks, dan cache berada di `data/` dan tidak di-commit.

## Menjalankan aplikasi lokal

Dari root repo, dengan environment dan data lokal yang sudah disiapkan:

```powershell
.venv/Scripts/python.exe -m streamlit run src/rag/ui/app.py --server.address 127.0.0.1
```

Buka [localhost:8501](http://127.0.0.1:8501). Default memakai KB skripsi penuh
melalui `configs/skripsi-local.yaml`. Mode **Demo tersimpan** menyediakan delapan
jawaban pilot tanpa panggilan generator baru. Pilihan korpus juga menyediakan
pilot lima PDF dan benchmark historis dengan config masing-masing.

API UI aktif otomatis sesuai instruksi pengguna: maksimal dua request generator
per submit termasuk koreksi format, serta lima request evaluator per card dengan
1.024 output token/request. Cache diperiksa dahulu; pertanyaan, klaim dan konteks
dikirim ke provider saat cache kosong. Demo memakai jawaban tersimpan tetapi tetap
menjalankan evaluasi otomatis. Batas total evaluator bergantung jumlah card.
API key hanya dari environment
atau `.env`; clone repo saja belum menyediakan model, PDF, database, dan cache.

Jawaban baru dan diagnostik menulis salinan database tersendiri. Evaluasi RAGAS
menyimpan artefak baru yang mengikat jawaban, seluruh konteks generation, config,
model, hash, dan usage. Kegagalan evaluasi tidak menghalangi pembacaan jawaban.
Jangan menjalankan `uv sync` atau `uv run` pada environment CUDA lokal saat ini.

## Status dan batas hasil

Integrasi KB penuh, jawaban bersitasi, PDF sumber, dan evaluasi RAGAS per card
sudah tersedia. Tes utama dan tes adapter RAGAS memakai provider mock; alur
cache-only, worker terpisah, dan embedding lokal sudah diuji. Evaluasi otomatis
diuji terbatas pada tiga card demo dengan API nyata. Akurasi manusia dan kualitas
retrieval untuk seluruh jenis pertanyaan belum dibuktikan.

Benchmark MVP empat paper dan hasil eksperimen terdahulu dipertahankan sebagai
riwayat terpisah. [Metrik M6](eval/results/2026-11-19T01-25-11Z_7492c6/metrics.json)
tersedia untuk pemeriksaan hasil benchmark kecil tersebut; hasilnya tidak
mewakili akurasi manusia pada KB skripsi penuh.

## Pengembangan

Python 3.11+; dependensi utama ada di [pyproject.toml](pyproject.toml).
Docling dan RAGAS memakai environment terpisah dengan lockfile
[Docling](eval/docling-requirements.lock) dan [RAGAS](eval/ragas-requirements.lock).
Keduanya tidak dipasang ke environment CUDA utama.

Jalankan pemeriksaan dari root repo:

```powershell
.venv/Scripts/python.exe -m pytest -q
.venv/Scripts/python.exe -m ruff check .
.venv/Scripts/python.exe -m ruff format --check .
```

Verifikasi terakhir: 598 test utama dan 15 test adapter RAGAS isolated lulus;
satu modul RAGAS dilewati di environment utama. Test menggunakan mock provider.
Dokumentasi kerja dan laporan Markdown tambahan dipertahankan secara lokal.
