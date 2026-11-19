# Evaluasi M6

Baseline M6 selesai untuk benchmark kecil empat paper pada 2026-11-19.
[Laporan final](results/2026-11-19T01-25-11Z_7492c6/m6-summary.md) mencatat
precision sitasi 86,24%, faithfulness 88,12%, dan abstention 3/4. Replay
memakai nol request baru dengan ranking, klaim, label, dan metrik identik.
Label manusia lama dilaporkan terpisah; accuracy pada klaim generation baru
belum diukur. `questions.jsonl` memuat 30 pertanyaan lintas empat
paper yang disusun AI lalu ditinjau dan disetujui pengguna pada 2026-11-19.
Provenance dan hash ada di `questions.reviewed-v1.manifest.json`; isi identik
dengan draf yang dibekukan sebelum retrieval. Dataset berisi 12 lookup,
8 comparison, 6 synthesis lintas paper, dan 4 unanswerable (13,3%).
Lihat [kesiapan batch](m6-multipaper-readiness-20261119.md) untuk catatan
persiapan sebelum izin batch. Run nyata memakai 30 request DeepSeek dan
28 judge Surplus, di bawah batas yang disetujui 60/50 request.

`questions.draft-v1.jsonl` tetap dipertahankan sebagai draf lama satu paper.
Uraian draf dan riwayat eksperimen di bawah mengacu pada versi lama itu.
`gold_labels.jsonl` belum tersedia; label manusia lokal dilaporkan terpisah.

Status anotasi 2026-11-19: seluruh 52 pasangan draf kini berlabel manusia pada
versi lokal baru; bahan awal tetap null. Jumlah anotasi mencapai rentang 50–100,
tetapi pasangan masih dari satu paper dan belum menjadi gold final. Pisahkan
12 pasangan pilot yang sudah melihat usulan AI dari 40 pasangan batch 1–4.
Label kumulatif tersimpan pada
`data/annotations/batches02-04-2026-11-19T00-31-04Z_673846/human-labels.jsonl`.

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

## Tinjauan lanjutan pilot

Paket lokal tersedia di
`data/annotations/m6-review-20261118T150117399425Z/`:

- `confirm-four.md` dan JSONL pendamping memuat empat usulan AI yang berbeda
  dari label manusia v2, beserta chunk lengkap. Label manusia baru masih kosong.
  Tinjauan ini tidak blind karena usulan dan hasil pilot telah terlihat.
- `remaining-01.md` sampai `remaining-04.md`, masing-masing dengan JSONL
  pendamping, memuat 40 pasangan unik di luar 12 pasangan pilot. Urutan diacak
  dengan seed 42; prediksi verifier tidak ditampilkan. Klaim atau paper mungkin
  telah terlihat, sehingga ini bukan jaminan studi blind.
- `manifest.json` menyimpan urutan pasangan, hash input/output, dan hasil
  pemeriksaan keutuhan sumber. Skrip pembuat berada di
  `data/jev-smoke/surplus-jev-v1/prepare-next-review.py`.

Mulai dari empat kasus konfirmasi, lalu isi batch tersisa. Simpan lembar yang
diisi sebagai file baru. Isi S/P/N, anotator, dan alasan per pasangan; untuk P,
sebutkan bagian klaim yang didukung serta bagian yang tidak didukung. Nilai
dukungan faktual terhadap chunk yang diberikan. Panjang jawaban, posisi abstrak,
dan ada/tidaknya eksperimen tidak menentukan label. Semua label/annotator pada
template JSONL masih null dan akan ditolak loader manusia sampai diisi.

Empat konfirmasi merupakan tinjauan ulang pasangan pilot, bukan pasangan baru.
Seluruh bahan tetap berasal dari 52 pasangan draf referensi satu paper; belum
menjadi gold final atau anotasi keluaran generation benchmark. Label lama dan
usulan AI tidak ditimpa, digabung, atau dipromosikan otomatis. M6 tetap menunggu
penilaian manusia, korpus lintas paper, dan benchmark final.

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

Pengguna kemudian mengisi empat kasus tersebut dengan N/N/N/P. Revisi manusia
disimpan pada `human-labels-v3.jsonl` dalam direktori pilot lokal; versi lama
tetap utuh. Anotator kosong pada lembar diteruskan sebagai `chat-user` dari label
sebelumnya berdasarkan pernyataan pengguna bahwa ia sendiri yang mengerjakan.
Alasan row-35 secara eksplisit menyetujui penjelasan AI dan disimpan apa adanya.
[Laporan v3](results/2026-11-18T15-17-53Z_8e261f/report.md) mencatat Jev cocok
12/12 dan MiniCheck 10/10 pada pasangan yang dinilai (kappa masing-masing 1,0).
Dua pasangan MiniCheck tetap unverified, sehingga cakupannya 10/12. Agreement
setelah usulan AI terlihat bukan validasi independen accuracy. Jumlah pasangan
unik pilot tetap 12; empat tinjauan merupakan revisi, bukan anotasi pasangan
baru. Empat puluh pasangan dalam `remaining-01` sampai `remaining-04` masih
menunggu label manusia. M6 tetap terbuka.

Batch 1 kemudian diisi sembilan label pada lembar dan satu label N untuk item
04 lewat balasan chat. Alasan item 04 belum diberikan dan tetap null. Sepuluh
label baru (empat S, enam N) disimpan lokal pada
`data/annotations/batch01-2026-11-18T15-34-19Z_111f6f/human-batch01.jsonl`;
`human-labels.jsonl` di direktori yang sama menggabungkan 12 pilot v3 dengan
10 pasangan baru, total 22 pasangan unik. Versi sebelumnya tetap utuh.
[Laporan batch 1](results/2026-11-18T15-34-19Z_111f6f/report.md) memakai MiniCheck
lokal: cocok 7/7 pada pasangan comparable (kappa 1,0), coverage 7/10. Item 03,
04, dan 06 melebihi batas token dan tetap unverified tanpa truncation. Run
incomplete; tidak ada API atau request JEV baru. Agreement batch ini dipisahkan
dari pilot yang sudah melihat usulan AI. Tiga puluh pasangan pada batch 2–4
masih menunggu label manusia; gold final dan M6 tetap terbuka.

## Seluruh anotasi draf selesai, 2026-11-19

Batch 2–4 kini juga berlabel: 30 pasangan baru (14 S, 2 P, 14 N), total 52
pasangan unik (22 S, 3 P, 27 N). Tiga belas alasan masih kosong dan tetap null.
Label, alasan, bukti, dan file lama tidak diubah agar mengikuti model. Gabungan
terbaru beserta snapshot lembar ada pada direktori lokal yang disebut di awal.

[Laporan seluruh cohort](results/2026-11-19T00-31-04Z_673846/report.md) memisahkan
12 pilot setelah usulan AI terlihat dari 40 pasangan batch 1–4. Pada batch 1–4,
MiniCheck cocok 30/35 (85,7%), kappa 0,710265, coverage 35/40. Gabungan deskriptif
seluruh pool cocok 40/45 (88,9%), kappa 0,767322, coverage 45/52. Tujuh input
terlalu panjang tetap unverified tanpa truncation. Run berstatus incomplete;
tidak ada API atau request JEV baru.

[Analisis perbedaan](results/2026-11-19T00-31-04Z_673846/failure-analysis.md)
memuat catatan AI atas lima perbedaan, terpisah dari label/alasan manusia.
MiniCheck biner tidak mempunyai kelas partial; perbedaan itu tidak dipetakan
diam-diam menjadi supported. Catatan AI tidak mengubah label manusia atau
mengisi alasan yang kosong. Volume anotasi mencapai target 50–100 dan kappa
sudah dihitung, tetapi pool draf satu paper belum menjadi gold benchmark final.
Korpus lintas paper, gold pertanyaan final, judge generatif sampel, dan evaluasi
final M6 tetap terbuka.
