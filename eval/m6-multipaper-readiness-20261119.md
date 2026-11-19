# Kesiapan evaluasi M6, 2026-11-19

Catatan ini adalah snapshot persiapan sebelum izin. Batch kemudian disetujui
dan selesai; hasil akhir ada di [laporan M6](results/2026-11-19T01-25-11Z_7492c6/m6-summary.md).
Harga judge pada pelaksanaan mengikuti penawaran Surplus yang diberikan pengguna,
US$0,027/juta input dan US$0,11/juta output; estimasi awal di bawah dipertahankan.

Dataset sudah ditinjau dan disetujui pengguna. Generation/sitasi dan judge nyata
belum dijalankan; batch berbayar belum disetujui. M6 tetap terbuka.

## Dataset dan korpus

`questions.jsonl`: 30 pertanyaan, 12 lookup, 8 comparison, 6 synthesis lintas
paper, 4 unanswerable (13,3%). Dataset disusun AI lalu ditinjau manusia, bukan
ditulis manusia secara independen. Persetujuan: “Sudah saya tinjau; setujui
draf v1”. Isi identik dengan versi yang dibekukan sebelum retrieval; persetujuan
manusia terjadi setelah run retrieval awal. Manifest mencatat urutan ini.

SHA-256: `67df3529d67ceabf6770e20ab32871752b3509508052425a7119ed696e9f45d9`.

Empat paper berlisensi CC-BY-4.0, 66 halaman, 236 chunk:

| Paper | ID | Halaman | Chunk |
|---|---|---:|---:|
| Deepchecks | arxiv:2605.14488v1 | 16 | 38 |
| Benchmarking RAG for Chemistry | arxiv:2505.07671v2 | 20 | 70 |
| LegalBench-RAG | arxiv:2408.10343v1 | 12 | 52 |
| MIRAGE | arxiv:2504.17137v1 | 18 | 76 |

Ini benchmark kecil M6, belum target korpus v1 100–500 paper. Dari batas awal
10 kandidat, empat lolos kebijakan lisensi. Parsing, chunking 220 token leksikal,
embedding dan retrieval memakai CPU. Indeks memuat 236 vektor dan 236 entri FTS5.
Panjang evidence maksimum pada tokenizer T5 adalah 394 token; panjang klaim
masih dapat membuat pasangan melebihi batas 512 dan harus dilaporkan unverified.

LegalBench-RAG menyebut total QA berbeda pada abstrak (6.858) dan bagian 3.3.1
(6.889). Topik jumlah total QA dikeluarkan sebelum pembekuan dataset; konflik
sumber tetap dicatat. Tidak ada perubahan dataset setelah melihat skor.

## Retrieval

Semua mode selesai untuk 30 pertanyaan. Recall/MRR hanya pada 26 pertanyaan
answerable, ranking sampai 20. Pengulangan offline memberi ranking, skor, dan
metrik identik; reranker memakai 1.500 cache hit dan nol pasangan baru.

| Mode | Recall@5 | Recall@10 | Recall@20 | MRR | Run awal | Run ulang |
|---|---:|---:|---:|---:|---|---|
| BM25 | 0,8013 | 0,8205 | 0,9295 | 0,6892 | 00-50-25Z_1e2f62 | 00-55-43Z_1b87c7 |
| Dense | 0,5705 | 0,7051 | 0,8526 | 0,5431 | 00-50-25Z_89a67c | 00-55-43Z_0665d2 |
| Hybrid | 0,7436 | 0,8718 | 0,8910 | 0,6247 | 00-50-32Z_f768ec | 00-55-49Z_f6849b |
| Hybrid+rerank | 0,7436 | 0,8013 | 0,8590 | 0,7105 | 00-50-32Z_854817 | 00-55-50Z_43fb5e |

Semua direktori run di `results/` diawali `2026-11-19T`. BM25 memiliki Recall@5
dan @20 tertinggi; hybrid Recall@10 tertinggi; reranker MRR tertinggi. Hybrid
tidak unggul pada semua metrik. Mode sitasi utama `hybrid+rerank` sudah ditetapkan
sebelum retrieval dan tidak diganti berdasarkan hasil ini.

## Judge dan batas berikutnya

Pengguna memilih GPT-4o-mini melalui Surplus (`GPT_MODEL_ID=gpt-4o-mini`).
Katalog GET Surplus mengenali model tersebut; belum ada inference nyata.
Adapter `surplus-chat` mempertahankan label dan alasan generatif, tanpa key
OpenAI langsung. Jev 1.14 tetap jalur pilot keputusan yang terpisah.

Proposal: maksimum 60 request DeepSeek, termasuk retry format, dan 50 request
judge Surplus. Sampel 25% klaim, seed 42, maksimum output 2.048 token/request,
nol retry transport. Estimasi sekitar US$0,54 memakai asumsi input konservatif;
jumlah request/output adalah batas keras, bukan meter batas dolar.

Config: `data/m6-multipaper/20261119T004114Z/config-citations-surplus-gpt-proposal.yaml`.
Rencana rinci: `judge-and-api-plan-surplus-gpt-v1.md` pada direktori yang sama.

Label manusia 52 pasangan dari eksperimen sebelumnya tetap dilaporkan terpisah:
batch 1–4 memiliki agreement 30/35, coverage 35/40, kappa 0,710265. Dua belas
pilot memiliki paparan usulan AI. Label itu bukan label klaim generation pada
236 chunk baru; ID lama tidak dipakai ulang untuk mengasumsikan teks yang sama.

## Validasi

380 test lulus, termasuk transport SDK Surplus dengan mock, key `.env`, model
efektif, model respons, token, batas request, nol retry, cache, endpoint ditolak,
independensi keluarga, dan runner sitasi yang diulang tanpa request baru.
Ruff lint/format bersih. Tidak ada dependensi, perubahan skema, format sitasi,
UI, atau key yang ditambahkan ke hasil. Hash korpus lama, label manusia, dan
draf lama tetap sama. Teks lengkap paper dan cache tetap di `data/`.
