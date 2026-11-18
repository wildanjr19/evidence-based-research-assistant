# Evaluasi M6

M6 masih berjalan. `questions.draft-v1.jsonl` adalah draf yang ditulis AI untuk
ditinjau manusia, bukan gold set manual final. Dataset final `questions.jsonl`
dan label manusia `gold_labels.jsonl` belum tersedia.

Draf mempunyai 30 pertanyaan: 15 lookup, 7 comparison, 4 synthesis, dan
4 unanswerable (13,3%). Semua ID berasal dari 21 chunk pada indeks M3 satu paper,
`arxiv:2605.14488v1` (CC-BY-4.0). Synthesis menggabungkan bagian dalam paper yang
sama; kebutuhan sintesis lintas paper belum terpenuhi. Ringkasan terkait karya
lain adalah pernyataan paper ini, bukan verifikasi terhadap paper lain tersebut.
Pertanyaan dan referensi perlu ditinjau, termasuk apakah kontrol unanswerable
benar-benar tidak terjawab oleh seluruh korpus.

SHA-256 draf v1:
`a6fc480fc37dd1e2d101030575f1a728f0e3b149b3e53f47b94dd3fda8f0c820`.
Jangan menyesuaikan label setelah melihat skor. Revisi draf disimpan sebagai versi
baru dengan alasan dan hash baru; pertahankan versi yang telah dievaluasi.

## Bahan anotasi lokal

`data/m6-smoke/local-verifier-v1/reference-annotations.jsonl` berisi 52 pasangan
untuk anotasi buta: masing-masing dari 26 jawaban referensi draf dipasangkan dengan
satu chunk kandidat relevan dan satu distraktor. Ini kandidat klaim buatan AI,
bukan keluaran generation benchmark. Tidak ada label verifier atau label manusia
yang diisikan. Urutan pasangan tidak boleh dianggap sebagai label.

Runner sitasi juga mengekspor pasangan dari keluaran sistem yang sesungguhnya
ke `data/annotations/<run_id>.jsonl`. Smoke test cache DeepSeek menghasilkan
empat pasangan tambahan per run. Jangan menghitung pengulangan pasangan yang
sama sebagai anotasi independen. Teks chunk tetap di `data/`, diabaikan Git.

Untuk setiap pasangan, baca klaim dan seluruh evidence, lalu isi:

- `supported`: seluruh isi faktual klaim didukung chunk tersebut.
- `partially_supported`: hanya sebagian klaim didukung.
- `not_supported`: bukti tidak mendukung, bertentangan, atau tidak cukup.
- `annotator`: identitas/pseudonim manusia yang memberi label.

Jangan memakai pengetahuan luar untuk melengkapi bukti. Klaim gabungan dinilai
terhadap satu chunk pada baris itu. Pertahankan `claim`, `chunk_id`, dan
`text_sha256`. Simpan hasil berlabel pada file baru; jangan menimpa bahan awal.

Setelah manusia memberi label, jalankan:

```powershell
.venv/Scripts/python.exe -m rag.evaluation --stage agreement --config data/m6-smoke/local-verifier-v1/config.yaml --annotations data/annotations/human-v1.jsonl
```

Runner memvalidasi label, identitas anotator, duplikasi, dan hash teks sumber.
Ia menjalankan MiniCheck lokal, menulis laporan run baru, dan menghitung Cohen's
kappa tanpa bobot pada tiga kelas. MiniCheck menghasilkan dua kelas, sehingga
`partially_supported` tetap kelas berbeda dan tidak dipetakan menjadi supported.
Kappa yang tidak terdefinisi ditulis `null`, termasuk semua label satu kelas.
File dengan label kosong ditolak. Kesepakatan terhadap label fixture dalam test
bukan kesepakatan terhadap manusia nyata.

`gold_labels_path` dapat menunjuk file berlabel di `data/`. Jika label akan
disimpan sebagai `eval/gold_labels.jsonl`, keluarkan field `evidence` terlebih
dahulu agar isi korpus tidak masuk Git. Gunakan 50–100 pasangan yang telah benar-benar
dinilai manusia untuk acceptance M6; bahan 52 pasangan tanpa label belum memenuhinya.

## Run yang tersedia

`results/2026-11-18T10-26-20Z_a8dbda/` dan
`results/2026-11-18T10-27-40Z_6a576e/` adalah smoke test satu pertanyaan,
empat klaim DeepSeek Flash dari cache API M5, dengan MiniCheck nyata pada CPU.
Tidak ada request API baru, judge nyata, atau label manusia pada run ini.
Nilai 1,0 pada precision/recall/faithfulness hanya hasil MiniCheck pada empat
pasangan ini. Nilai itu bukan benchmark 30 pertanyaan atau validasi manusia.
Detail RAM/VRAM dan pemeriksaan integritas berada di TASKS.md.

## Pilot Jev / MiniCheck

Eksperimen opsional melalui Surplus tersedia pada
[run pertama](results/2026-11-18T11-50-46Z_ad072b/report.md) dan
[pengulangan cache](results/2026-11-18T11-52-32Z_764cf8/report.md).
Seed 42 memilih 12 dari 52 pasangan kandidat referensi draf sebelum inference.
Input tidak diberi label manusia atau diubah setelah skor terlihat.

Jev `typesafe/jev-1.14-20261014` menjawab 12 pasangan: empat supported, tujuh
not_supported, satu partially_supported. MiniCheck menilai 10; dua input memiliki
518 dan 526 token T5 sehingga ditolak tanpa truncation. Label kedua model sama
pada 10 pasangan yang dapat dibandingkan. Run tetap berstatus incomplete karena
coverage MiniCheck 10/12. Agreement dan kappa antar-model 1,0 bukan accuracy atau
agreement terhadap manusia. Tujuh pasangan negatif menurut kedua model memakai
chunk abstrak yang sama; pilot ini belum menguji keragaman kasus sulit.

Request nyata dibatasi 12, tanpa retry. Pengulangan memakai 12 cache hit Jev dan
10 cache hit MiniCheck, tanpa request API baru; dua input terlalu panjang tetap
ditolak. Laporan memisahkan usage baru, latency HTTP, score/probabilitas, confidence,
coverage, dan memori proses. Tidak ada generator yang dipanggil pada eksperimen.

Bahan tinjauan manusia khusus sampel ini tersedia lokal sebagai
`data/jev-smoke/surplus-jev-v1/human-review.md` dan `human-review.jsonl`.
Kelima chunk unik ditampilkan sekali per kelompok, tanpa label/prediksi model.
Nilai klaim terhadap chunk di kelompoknya, dengan S/P/N dan alasan. Seluruh label
di bahan awal tetap null; jangan menganggap hasil Jev sebagai label manusia. Ini tetap bahan
pilot satu paper; gold final dan acceptance manual M6 belum terpenuhi.

Setelah koreksi P menjadi S, pengguna mengonfirmasi supported untuk seluruh 12
pasangan. Hasil manusia tersimpan terpisah dalam `human-labels-v1.jsonl` pada
direktori pilot lokal, dengan identitas anotator dan hash sumber. Bahan awal
tidak ditimpa. [Perbandingan dengan label manusia](results/2026-11-18T12-25-28Z_4cf0c3/report.md)
memakai prediksi tersimpan: Jev cocok 4/12, MiniCheck 3/10 (dua unverified).
Kappa keduanya 0,0; seluruh label manusia satu kelas, sehingga hasil ini belum
menilai kualitas umum model. Delapan perbedaan dengan Jev perlu adjudikasi
per klaim. Label manusia tidak otomatis diubah untuk mengikuti model.
Satu anotator menilai kelompok chunk dan telah mengetahui hasil agregat model;
pilot ini bukan studi sepenuhnya blind atau gold benchmark final.

Pengguna kemudian meninjau delapan pasangan berbeda secara individual dan
mengubah tujuh label. Versi lokal `human-labels-v2.jsonl` berisi lima S, tiga P,
dan empat N. [Laporan revisi](results/2026-11-18T12-38-58Z_a86400/report.md)
mencatat Jev cocok 8/12 (kappa 0,483871), MiniCheck 7/10 (kappa 0,523810), dengan
dua pasangan MiniCheck tetap unverified. Tiga alasan P masih perlu diperjelas
agar menilai bagian klaim yang didukung, bukan panjang jawaban. Semua label
dipertahankan sesuai masukan pengguna, belum menjadi gold final. Review dipilih
dari ketidaksepakatan model setelah hasil agregat diketahui; kenaikan agreement
bukan bukti independen bahwa model lebih akurat.

Atas permintaan pengguna, agent kemudian meninjau delapan pasangan itu untuk
memperbaiki penerapan rubrik. Usulan tersimpan lokal pada
`data/jev-smoke/surplus-jev-v1/ai-adjudication-v1.jsonl` dan `.md`, terpisah dari
label manusia. Row-08, row-02, dan row-18 diusulkan N; row-35 diusulkan P karena
hanya klausa reference-based didukung chunk. Empat pasangan lain tetap N.
Artefak ini secara eksplisit berjenis AI dan tidak dapat dipakai sebagai label
manual oleh loader. Label manusia tetap utuh; jumlah label manusia dan laporan
agreement manusia tidak bertambah dari tinjauan AI ini. Gold final M6 belum
tersedia.
