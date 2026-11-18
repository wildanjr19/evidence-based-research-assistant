# AGENTS.md

Panduan kerja untuk AI coding agent (Codex, DeepSeek-based agent, dll.) di repo ini.
Bagian bertanda `TODO` harus disesuaikan dengan kondisi repo sebenarnya.

## 1. Proyek

Evidence-Based Research Assistant: sistem RAG lokal untuk literatur ilmiah.
Jawaban harus berisi klaim yang masing-masing menunjuk ke chunk sumber (paper, halaman, kutipan), dan ketepatan sitasinya diukur.

Sumber kebenaran, baca sebelum mengubah arsitektur:
- `OVERVIEW.md`: tujuan, stack, batasan.
- `ARCHITECTURE.md`: arsitektur, skema data, format ID/sitasi, protokol evaluasi, keputusan desain.
- `DESIGN.md`: sistem desain visual UI (warna, tipografi, spacing). Bukan dokumen arsitektur.
- `TASKS.md`: milestone dan acceptance criteria.
- `USAGE.md`: setup, perintah pipeline, dan batas penggunaan. README berfokus pada pengantar proyek; catatan verifikasi/handoff disimpan di TASKS.md.

Jika kode dan dokumen bertentangan, jangan menebak. Tanyakan, atau tandai ketidaksesuaiannya di jawabanmu.

## 2. Perintah

Perintah fondasi sudah diverifikasi pada M0. Jalankan dari root repo; bentuk module tidak memerlukan `uv` di PATH atau aktivasi virtual environment. Jika belum terpasang: `python -m pip install --user uv`.

```bash
python -m uv sync --locked                        # install dependensi dari lockfile
python -m uv run python -m pytest -q               # semua test (tanpa API berbayar)
python -m uv run python -m pytest -q -m "not gpu"  # test tanpa GPU
python -m uv run ruff check .                      # lint
python -m uv run ruff format --check .             # format
```

Di mesin pengembangan Windows, launcher `pytest.exe` diblokir Application Control; pemanggilan melalui `python -m pytest` sudah diverifikasi.

Jika `.venv` sudah aktif, panggil `python -m pytest`, `python -m ruff`, atau `python -m rag...` langsung. `uv` terpasang di Python luar; `python -m uv` dalam `.venv` dapat gagal dengan `No module named uv`. Di Windows, `py -3.11 -m uv` memakai Python luar bila diperlukan.

Perintah M1 (melakukan request arXiv; jalankan berurutan):

```bash
python -m uv run python -m rag.ingestion discover --config configs/config.yaml
python -m uv run python -m rag.ingestion fetch --config configs/config.yaml
```

Sudah diuji nyata dengan config terpisah yang membatasi satu kandidat. Default repo membatasi 10 kandidat; korpus final belum diunduh. Test tetap memakai fixture lokal.

Runner evaluasi retrieval M4 sudah tersedia; evaluasi sitasi menunggu M6. Dataset final `eval/questions.jsonl` belum tersedia, sehingga evaluasi awal memerlukan `--dataset` yang gold ID-nya sesuai korpus. Perintah dan batas metrik ada di `USAGE.md`.

Perintah M4 (indeks M3 harus sudah lengkap; penggunaan reranker pertama mengunduh bobot):

```bash
.venv/Scripts/python.exe -m rag.retrieval --config configs/config.yaml --question "How is RAG retrieval evaluated?" --mode hybrid
.venv/Scripts/python.exe -m rag.evaluation --config configs/config.yaml --dataset data/validation/questions.jsonl --mode all
```

Path `data/validation/questions.jsonl` pada contoh harus disiapkan lebih dulu. Empat mode diuji dengan fixture lokal dan smoke test CPU pada satu paper. BGE reranker nyata berhasil menghitung 105 pasangan; pengulangan offline memakai 105 cache hit dengan ranking identik. Query embedding/reranker GPU dan korpus penuh belum diuji. Laporan per mode memakai direktori run baru; detail verifikasi/handoff ada di TASKS.md bagian M4.

Perintah M5 (default hanya membaca cache LLM; cache miss tidak memanggil API):

```bash
.venv/Scripts/python.exe -m rag.generation --config configs/config.yaml --question "How is RAG retrieval evaluated?" --mode hybrid
```

Panggilan LLM nyata memerlukan `--allow-api`, model yang tersedia, dan key provider di environment. `.env` tidak dibaca otomatis. Config awal `deepseek-chat` belum divalidasi live; pastikan model sebelum panggilan berbayar. M5 diuji dengan LLM mock/transport HTTP lokal, tanpa API berbayar. Smoke test memakai salinan database/index, retrieval CPU nyata, dan cache respons. Tabel `run`/`answer`/`claim` mengikuti skema ARCHITECTURE.md; tabel sumber tetap. Detail RAM/VRAM serta handoff ada di TASKS.md bagian M5.

Perintah M2 (lokal, memakai corpus hasil M1):

```bash
python -m uv run python -m rag.parsing --config configs/config.yaml
python -m uv run python -m rag.chunking --config configs/config.yaml
```

Gunakan `--paper-id` untuk satu paper. Kedua perintah sudah diuji dengan config lokal terpisah pada PDF 16 halaman. `n_tokens` M2 memakai token leksikal, bukan tokenizer model; M3 wajib memeriksa batas embedding. Perubahan hasil parsing/chunking lama ditolak tanpa penghapusan otomatis. Alasan kegagalan berada di laporan run dalam `paths.parsed_dir/reports/`.

Perintah M3 (seluruh tabel chunk; penggunaan pertama mengunduh bobot model):

```bash
python -m uv run python -m rag.indexing --config configs/config.yaml
```

Sudah diuji pada CPU dengan config `data/m3-smoke/config.yaml`: 21 chunk = 21 vektor = 21 FTS5; pengulangan offline memakai cache tanpa encoding baru. Laporan ada di `paths.index_dir/reports/`. Input melebihi batas tokenizer model ditolak tanpa truncation; gunakan database baru untuk chunk lebih kecil. Indexing dijalankan serial. M3 sudah ditutup; handoff ada di TASKS.md.

PyTorch `2.15.0+cu132` dipasang manual oleh pengguna. CUDA dan operasi tensor GPU sudah diverifikasi pada RTX 3060 Ti; 186 test lulus. Embedding nyata masih diuji pada CPU dan default config tetap CPU. Lockfile belum disesuaikan dengan sumber CUDA. Untuk mempertahankan environment saat ini, gunakan `.venv/Scripts/python.exe` langsung untuk test/pipeline; jangan menjalankan `uv sync`/`uv run` yang menyinkronkan environment sebelum sumber/lock CUDA dirapikan. Uji embedding GPU berikutnya harus memakai cache baru agar tidak hanya membaca embedding CPU.

Jalankan test dan lint setelah setiap perubahan kode, sebelum menyatakan tugas selesai.

## 3. Struktur repo

Struktur final dan peta modul ada di `ARCHITECTURE.md` §2. Ringkasnya:

```
src/rag/           ingestion, parsing, chunking, indexing, retrieval, generation, verification, evaluation, ui
eval/              dataset uji, skrip evaluasi, hasil
data/              korpus dan indeks (TIDAK di-commit)
configs/           config.yaml dan variasi eksperimen
tests/
```

## 4. Aturan inti (invarian proyek)

Aturan ini adalah inti proyek. Jangan dilanggar tanpa persetujuan eksplisit.

1. **Grounding ketat.** LLM hanya boleh menjawab dari chunk yang diambil. Jangan menambahkan pengetahuan dari luar konteks ke prompt jawaban.
2. **Setiap klaim wajib punya sitasi** berupa ID chunk yang valid. Klaim tanpa bukti harus dikeluarkan atau dilabeli "tidak ada bukti". Jangan pernah mengarang ID, judul, atau halaman.
3. **Format sitasi dan skema data bersifat tetap.** Jangan ubah tanpa bertanya, karena memengaruhi evaluasi.
4. **Evaluasi harus bisa direproduksi.** Simpan seed, versi model, dan config tiap eksperimen. Jangan menimpa hasil lama; simpan dengan nama run baru.
5. **Jangan memodifikasi dataset uji (`eval/`) agar hasil terlihat lebih baik.** Perubahan dataset harus eksplisit dan dicatat.

## 5. Data dan lisensi

- Hanya paper open access. Simpan lisensi dan sumber di metadata setiap paper.
- **Jangan commit** PDF, teks penuh paper, indeks, atau isi `data/`. Cukup simpan ID/URL dan skrip untuk mengunduh ulang.
- Jangan menambah sumber data baru tanpa memastikan lisensinya.

## 6. Secret dan biaya API

- API key hanya dari environment variable (`.env`, sudah di-gitignore). Jangan hardcode, jangan cetak ke log, jangan commit.
- Perbarui `.env.example` bila menambah variabel baru (tanpa nilai asli).
- **Test tidak boleh memanggil API berbayar.** Gunakan mock atau fixture.
- Panggilan LLM nyata hanya dijalankan lewat skrip evaluasi atau perintah eksplisit. Cache respons dan embedding. Catat penggunaan token.
- Jangan membuat loop panggilan API tanpa batas; selalu beri batas jumlah panggilan.

## 7. Konvensi kode

- Python 3.11+, type hints pada fungsi publik.
- Formatter dan linter: `ruff` (konfigurasi di `pyproject.toml`: line-length 100, target py311).
- Logging dengan modul `logging`, bukan `print`.
- Parameter yang bisa dieksperimenkan (ukuran chunk, bobot RRF, top-k, model) masuk ke config, bukan di-hardcode.
- Fungsi kecil dan bisa diuji. Pisahkan logika dari I/O (jaringan, disk, GPU).
- Komentar menjelaskan *kenapa*, bukan *apa*.

## 8. Dependensi

- Jangan menambah dependensi baru tanpa konfirmasi. Jelaskan alasan dan alternatifnya.
- Kunci versi di file lock. Jangan mengganti versi mayor library tanpa bertanya.

## 9. Testing

- Test unit untuk chunking, fusion (RRF), parsing format klaim-sitasi, dan validasi ID chunk.
- Mock LLM, embedding, dan jaringan.
- Test yang membutuhkan GPU diberi marker `gpu` agar bisa dilewati.
- Bug yang diperbaiki sebaiknya disertai test yang mereproduksinya.

## 10. Kapan harus bertanya dulu

Berhenti dan tanyakan sebelum:
- mengubah skema data, format sitasi, atau struktur folder utama;
- menambah dependensi atau sumber data baru;
- menghapus file, data, atau hasil eksperimen;
- menjalankan perintah yang memanggil API berbayar dalam jumlah besar atau memakan waktu lama;
- melakukan refactor besar di luar lingkup tugas.

Jika instruksi ambigu, nyatakan asumsimu secara singkat, lalu lanjutkan dengan pilihan paling konservatif.

## 11. Alur kerja

- Kerjakan satu tugas kecil pada satu waktu. Hindari perubahan di luar lingkup tugas.
- Baca kode terkait dan dokumen desain sebelum menulis.
- Pesan commit singkat dan deskriptif (misal `retrieval: add RRF fusion`).
- Jika keputusan desain berubah, perbarui `DESIGN.md` pada perubahan yang sama.

## 12. Definisi selesai

Tugas dianggap selesai bila:
- [ ] Perilaku yang diminta berfungsi dan diuji.
- [ ] `pytest -q` lulus.
- [ ] `ruff check .` dan format bersih.
- [ ] Tidak ada secret, data korpus, atau file besar yang ikut ter-commit.
- [ ] `DESIGN.md` / `README.md` diperbarui bila perlu.
- [ ] Ringkasan perubahan, asumsi, dan hal yang belum teruji dinyatakan jujur.

Jangan menyatakan "sudah berjalan" jika belum dijalankan. Katakan apa yang sudah dan belum diverifikasi.
