# M6: benchmark empat paper, 30 pertanyaan

Baseline M6 selesai untuk benchmark kecil ini. [Catatan interpretasi](review-notes.md)
menjelaskan format penolakan multi029, agreement judge 22/28 dengan kappa 0,
dan batas validasi manusia pada klaim baru.

Run berbayar: `2026-11-19T01:25:11Z_7492c6`. Status `ok`.
Replay tanpa izin API: `2026-11-19T01:31:11Z_75bb36`; nol request baru.

Dataset SHA-256: `67df3529d67ceabf6770e20ab32871752b3509508052425a7119ed696e9f45d9`.

Empat paper CC-BY-4.0, 236 chunk; 12 lookup, 8 comparison, 6 synthesis lintas paper, 4 unanswerable.
Dataset disusun AI lalu ditinjau dan disetujui pengguna; tidak berubah dari pembekuan sebelum retrieval.
Mode hybrid+rerank ditetapkan sebelum skor diketahui. Batas 60 request generator dan 50 judge disetujui pengguna.

| Metrik | Nilai |
|---|---:|
| citation_precision | 0.8623853211009175 |
| citation_recall | 0.8811881188118812 |
| faithfulness | 0.8811881188118812 |
| hallucinated_citation_rate | 0.0 |
| abstention_accuracy | 0.75 |
| claim_count | 101 |
| citation_pair_count | 109 |
| supported_pair_count | 94 |
| unverified_pair_count | 0 |
| failed_question_count | 0 |
| unanswerable_count | 4 |
| unanswerable_claim_count | 1 |
| verifier_agreement_kappa | None |
| manual_matched_pairs | 0 |
| judge_agreement_kappa | 0.0 |
| judge_matched_pairs | 28 |
| recall@5 | 0.7435897435897435 |
| recall@10 | 0.8012820512820512 |
| recall@20 | 0.8589743589743589 |
| mrr | 0.7104700854700856 |

Metrik dukungan utama memakai MiniCheck; agreement judge bukan accuracy terhadap manusia.
Citation recall di implementasi ini adalah proporsi klaim yang didukung, sehingga sama dengan faithfulness; bukan recall semua fakta referensi.
Tidak ada ambang skor kelulusan yang ditetapkan. Hasil ini tidak membuktikan hybrid unggul pada semua metrik.

## Model, token, biaya, dan sumber daya

Model/backends: `{"embedding": {"model": "BAAI/bge-base-en-v1.5", "revision": "a5beb1e3e68b9ab74eb54cfd186867f64f240e1a"}, "embedding_backend": "rag.indexing.embedding.SentenceEmbedder", "generator": "deepseek-flash", "generator_backend": "rag.generation.client.OpenAIBackend", "judge": "gpt-4o-mini", "judge_backend": "rag.generation.client.OpenAIBackend", "judge_identity": null, "reported_generator_models": ["deepseek-flash"], "reported_judge_models": ["gpt-4o-mini"], "reranker": {"model": "BAAI/bge-reranker-base", "revision": "2cfc18c9415c912f9d8155881c133215df768a70"}, "reranker_backend": null, "verifier": {"adapter": "minicheck-flan-t5-pair-v1-no-truncation", "backend": "rag.verification.minicheck.MiniCheck", "device": "cpu", "max_tokens": 512, "model": "lytang/MiniCheck-Flan-T5-Large", "revision": "96eafd01cee2d16cf81aaa2fb226b14f422a37b3", "threshold": 0.5}}`.

Usage: `{"generation": {"backend_calls": 30, "cache_hits": 0, "input_tokens": 87561, "output_tokens": 5865, "unknown_usage_attempts": 0}, "judge": {"backend_calls": 28, "cache_hits": 0, "input_tokens": 10521, "output_tokens": 1565, "unknown_usage_attempts": 0}}`.

Estimasi DeepSeek US$0.033306; judge US$0.000456; total US$0.033763.
DeepSeek memakai [harga resmi peak cache-miss](https://api-docs.deepseek.com/quick_start/pricing/); diskon cache belum diperhitungkan.
Judge memakai harga Surplus yang diberikan pengguna: US$0,027/juta input dan US$0,11/juta output. Angka ini estimasi berbasis usage, bukan tagihan provider.
Durasi run berbayar 262.66 detik; replay 27.67 detik.
Resources proses berbayar: `{"cuda_initialized": false, "peak_private_commit_bytes": 6821879808, "peak_torch_allocated_bytes": 0, "peak_torch_reserved_bytes": 0, "peak_working_set_bytes": 4667105280, "scope": "Current Python process lifetime; PyTorch allocator only for VRAM"}`.

## Batas interpretasi

Cohen kappa manusia pada benchmark jawaban baru tetap null karena tidak ada label manusia yang cocok langsung.
Sebanyak 52 label manusia dari eksperimen satu paper dilaporkan terpisah: 12 pilot terpapar usulan AI; 40 lainnya memiliki 35 pasangan comparable, agreement 30/35 dan kappa 0,710265.
Label lama tidak dipindahkan ke chunk baru. Tidak ada label yang diganti mengikuti prediksi model.
Benchmark ini belum korpus v1 100–500 paper dan belum menguji inference GPU. Semua verifier nyata memakai CPU.
Lihat [analisis kegagalan](failure-analysis.md), [validasi](validation.json), dan [laporan runner](report.md).
