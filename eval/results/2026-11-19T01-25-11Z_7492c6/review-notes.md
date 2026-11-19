# Interpretasi dan batas hasil

Catatan ini adalah tinjauan AI terhadap artefak dan sumber kanonis, bukan label
manusia baru. Metrik, dataset, dan label verifier tetap dipertahankan.

## Kontrol multi029: format penolakan

DeepSeek menyatakan bahwa evidence tidak melaporkan Cohen's kappa untuk
CHEMRAG-BENCH. Pernyataan itu dimasukkan sebagai satu klaim `unsupported=true`
dengan sitasi kosong. Model tidak mengarang angka kappa, tetapi gagal mengikuti
kontrak abstention `{"claims": []}`. Sesuai protokol yang dibekukan, klaim tetap
dihitung gagal; abstention accuracy tetap 3/4 atau 75%. Jangan mengubah gold,
menormalisasi respons secara retroaktif, atau melaporkan angka ini sebagai 4/4.

## Judge: agreement 22/28, kappa 0

GPT-4o-mini memberi label supported pada seluruh 28 pasangan sampel. MiniCheck
sepakat pada 22 dan memberi not_supported pada enam lainnya. Agreement 78,57%
dan Cohen kappa 0 sama-sama benar: distribusi satu kelas pada judge membuat
agreement yang diharapkan dari marginal sama dengan agreement yang diamati.
Sampel ini tidak menguji kemampuan judge membedakan seluruh kelas dan tidak
menghasilkan accuracy terhadap manusia. Label judge tidak menggantikan metrik
utama MiniCheck.

Pembacaan sumber menunjukkan beberapa calon penyebab ketidaksepakatan:

- `multi002`, LegalBench `p5:c24`: tabel PDF terurai menjadi baris dan kolom yang
  saling menyisip. Relasi empat dataset, 194 query per dataset, dan total 776
  lebih sulit dibaca verifier daripada paragraf biasa.
- `multi003`, LegalBench `p5:c20`: file path, exact quote, dan character indices
  tertulis di sumber; pemenggalan kata PDF masih ada. Ini indikasi kemungkinan
  false negative MiniCheck, belum adjudikasi manusia.
- `multi009`, Chemistry `p5:c18`: daftar retriever menyisip dengan tabel korpus
  pada hasil ekstraksi dua kolom. Nama BM25, Contriever, SPECTER, dan e5 ada,
  tetapi susunan teks mengganggu konteks daftar.
- `multi023`, Deepchecks `p8:c18`: chunk dimulai pada kelanjutan definisi dan
  kehilangan heading Retrieval Relevance. Klaim membawa nama properti itu;
  konteks yang tidak utuh dapat membuat penilaian dukungan berbeda.
- `multi023`, Chemistry `p2:c10`: sumber menyebut peningkatan relatif rata-rata
  17,4% atas direct inference. Penolakan MiniCheck menjadi kandidat false
  negative yang perlu dibedakan dari kesalahan generator.
- `multi026`, Deepchecks `p11:c25`: angka ROC-AUC dan label dataset berasal dari
  tabel yang diekstrak menjadi baris terpisah; hubungan kolom rentan ambigu.

Lima belas pasangan not_supported MiniCheck tetap tercantum pada
[analisis kegagalan](failure-analysis.md), termasuk sembilan yang tidak disampel
judge. Belum ada label manusia langsung untuk klaim generation baru ini.
Sebanyak 52 anotasi referensi lama tetap cohort validasi terpisah, dengan
paparan pilot dan coverage yang dijelaskan pada laporan.

## Handoff

Baseline M6 ini selesai sebagai benchmark kecil empat paper. M7 dapat memakai
hasil dan status verifikasi ini untuk UI. Pengukuran 100–500 paper, inference
GPU, kualitas jawaban terhadap seluruh reference answer, dan accuracy verifier
pada klaim generation baru belum diuji. Eksperimen perbaikan parser, prompt
abstention, atau verifier berikutnya harus memakai versi dan run baru.
