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

TODO M6: implementasikan dan verifikasi perintah evaluasi retrieval/sitasi. Runner evaluasi belum tersedia; lokasi config adalah `configs/config.yaml`.

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
