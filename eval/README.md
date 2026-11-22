# Indeks evaluasi MVP M6

Benchmark M6 empat paper selesai 2026-11-19. Evaluasi korpus skripsi dan UI terbaru
ada di [TASKS-SKRIPSI.md](../TASKS-SKRIPSI.md); riwayat implementasi di [TASKS.md](../TASKS.md).
Laporan run di `results/` dipertahankan sebagai bukti historis.

## Benchmark final

[Laporan final](results/2026-11-19T01-25-11Z_7492c6/m6-summary.md):
30 pertanyaan/101 klaim/109 pasangan, precision sitasi MiniCheck 86,24%,
recall/faithfulness implementasi 88,12%, abstention 3/4. Recall mengukur klaim
dengan sedikitnya satu sitasi supported, bukan seluruh fakta acuan. Akurasi
manusia atas klaim generation baru belum diukur.

Dataset `questions.jsonl`: 12 lookup, 8 comparison, 6 synthesis lintas paper,
4 unanswerable. Draf AI dibekukan sebelum retrieval, lalu ditinjau/disetujui pengguna;
provenance di `questions.reviewed-v1.manifest.json`. Korpus empat paper CC-BY-4.0,
66 halaman/236 chunk, terpisah dari KB skripsi. Jangan memakai label/ID-nya pada snapshot lain.

| Bukti | Isi |
|---|---|
| [Kesiapan batch](m6-multipaper-readiness-20261119.md) | Korpus, freeze, empat mode retrieval dan batas rencana |
| [Laporan run final](results/2026-11-19T01-25-11Z_7492c6/report.md) | Hasil/coverage/config run |
| [Analisis kegagalan](results/2026-11-19T01-25-11Z_7492c6/failure-analysis.md) | Kontrol penolakan dan konflik verifier |
| [Catatan review](results/2026-11-19T01-25-11Z_7492c6/review-notes.md) | Batas interpretasi |
| [Replay final](results/2026-11-19T01-31-11Z_75bb36/report.md) | Ranking/klaim/label/metrik identik tanpa API baru |

Aktual 30 DeepSeek/28 Surplus dari izin maksimum 60/50 request. Seluruh batch
selesai; sisa bukan izin baru. Replay 30 cache generation/28 judge/109 MiniCheck,
nol request atau inference verifier baru. Agreement GPT/MiniCheck bukan akurasi manusia.

## Draf lama dan anotasi manusia

`questions.draft-v1.jsonl` adalah draf 30 pertanyaan satu paper/21 chunk
`arxiv:2605.14488v1`: 15 lookup/7 comparison/4 synthesis dalam paper/4 unanswerable.
SHA-256 `a6fc480fc37dd1e2d101030575f1a728f0e3b149b3e53f47b94dd3fda8f0c820`.
Bukan dataset benchmark final. `gold_labels.jsonl` belum tersedia di repo;
label manusia berada lokal dan bukan label klaim generation benchmark baru.

Bahan awal `data/m6-smoke/local-verifier-v1/reference-annotations.jsonl`:
52 pasangan klaim acuan/distraktor buatan AI, label awal null. Seluruhnya kemudian
berlabel pada versi baru, 22 S/3 P/27 N, dengan 13 alasan tetap kosong.
Label kumulatif:
`data/annotations/batches02-04-2026-11-19T00-31-04Z_673846/human-labels.jsonl`.

Pisahkan 12 pilot yang sudah melihat usulan AI dari 40 batch 1-4. Pada batch
baru MiniCheck cocok 30/35, kappa 0,710265, coverage 35/40. Gabungan deskriptif
40/45, kappa 0,767322, coverage 45/52. Tujuh input panjang tetap unverified,
tanpa truncation. Volume 52 bukan validasi seluruh korpus/gold generation final.

| Laporan historis | Hasil/batas |
|---|---|
| [Pilot JEV](results/2026-11-18T11-50-46Z_ad072b/report.md), [cache replay](results/2026-11-18T11-52-32Z_764cf8/report.md) | JEV 12/12, MiniCheck 10/12; dua input 518/526 token ditahan; agreement comparable 1,0 bukan accuracy |
| [Manusia v1](results/2026-11-18T12-25-28Z_4cf0c3/report.md) | Semua label S; JEV cocok 4/12, MiniCheck 3/10 |
| [Manusia v2](results/2026-11-18T12-38-58Z_a86400/report.md) | JEV 8/12, MiniCheck 7/10; review dari konflik, rubrik partial belum tuntas |
| [Manusia v3](results/2026-11-18T15-17-53Z_8e261f/report.md) | JEV 12/12, MiniCheck 10/10 setelah usulan AI terlihat; bukan validasi independen |
| [Batch 1](results/2026-11-18T15-34-19Z_111f6f/report.md) | 10 pasangan baru, MiniCheck comparable 7/7; tiga overlength |
| [Seluruh cohort](results/2026-11-19T00-31-04Z_673846/report.md), [analisis](results/2026-11-19T00-31-04Z_673846/failure-analysis.md) | Pisahkan cohort pilot/batch; partial tidak menjadi supported |

Versi label/usulan AI di `data/jev-smoke/surplus-jev-v1/`; paket review lama di
`data/annotations/m6-review-20261118T150117399425Z/`. Template null tetap utuh;
revisi manusia disimpan sebagai versi baru, bukan menimpa usulan/prediksi.

## Kontrak anotasi dan reproduksi

Nilai seluruh klaim terhadap satu chunk, tanpa melengkapi bukti dari pengetahuan luar:
`supported`, `partially_supported`, `not_supported`. Isi annotator manusia,
pertahankan claim/chunk_id/text_sha256, dan simpan versi baru. Partial berarti
bagian klaim didukung, bukan sekadar jawaban pendek/abstrak. Usulan AI harus tetap
berlabel AI; pengulangan pasangan bukan anotasi independen.

```powershell
.venv/Scripts/python.exe -m rag.evaluation --stage agreement --config data/m6-smoke/local-verifier-v1/config.yaml --annotations <labels-manusia.jsonl>
```

Loader memeriksa label/annotator/duplikasi/hash; label kosong ditolak. Kappa tiga
kelas tanpa bobot; MiniCheck biner tidak memetakan partial menjadi supported.
Kappa tak terdefinisi null; agreement fixture bukan agreement manusia nyata.
`gold_labels_path` boleh lokal; bila mengekspor label ke `eval/`, buang field
`evidence` agar full text tidak masuk Git. Jangan menyesuaikan label dari skor.

Smoke awal empat pasangan DeepSeek cache + MiniCheck CPU ada di
[run awal](results/2026-11-18T10-26-20Z_a8dbda/report.md) dan
[replay](results/2026-11-18T10-27-40Z_6a576e/report.md). Nilai 1,0 hanya empat
pasangan itu, tanpa API baru; bukan benchmark atau validasi manusia.
