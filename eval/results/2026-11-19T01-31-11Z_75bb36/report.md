# Citation evaluation: hybrid+rerank

Run: `2026-11-19T01:31:11Z_75bb36`. Status: ok.

Config SHA-256: `b717527af1a4ea957998dad9e99c77405d67c040ad6b0e5076f963b9b0132180`.

Dataset SHA-256: `67df3529d67ceabf6770e20ab32871752b3509508052425a7119ed696e9f45d9`.

Seed: 42. Questions: 30.

Models and backends: `{"embedding": {"model": "BAAI/bge-base-en-v1.5", "revision": "a5beb1e3e68b9ab74eb54cfd186867f64f240e1a"}, "embedding_backend": "rag.indexing.embedding.SentenceEmbedder", "generator": "deepseek-flash", "generator_backend": "rag.generation.client.OpenAIBackend", "judge": "gpt-4o-mini", "judge_backend": "rag.generation.client.OpenAIBackend", "judge_identity": null, "reported_generator_models": ["deepseek-flash"], "reported_judge_models": ["gpt-4o-mini"], "reranker": {"model": "BAAI/bge-reranker-base", "revision": "2cfc18c9415c912f9d8155881c133215df768a70"}, "reranker_backend": null, "verifier": {"adapter": "minicheck-flan-t5-pair-v1-no-truncation", "backend": "rag.verification.minicheck.MiniCheck", "device": "cpu", "max_tokens": 512, "model": "lytang/MiniCheck-Flan-T5-Large", "revision": "96eafd01cee2d16cf81aaa2fb226b14f422a37b3", "threshold": 0.5}}`.

Question types: `{"comparison": 8, "lookup": 12, "synthesis": 6, "unanswerable": 4}`.

| Metric | Value |
|---|---|
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
| verifier_agreement_kappa | undefined |
| manual_matched_pairs | 0 |
| judge_agreement_kappa | 0.0 |
| judge_matched_pairs | 28 |
| recall@5 | 0.7435897435897435 |
| recall@10 | 0.8012820512820512 |
| recall@20 | 0.8589743589743589 |
| mrr | 0.7104700854700856 |

MiniCheck pair labels determine primary support metrics; judge results are separate.
Claims on unanswerable questions fail faithfulness. Failed generation is not abstention.
Unknown support and failed generation make aggregate support metrics undefined.
Citation events count unique IDs per claim after M5 deduplication, including rejections.
Manual agreement requires matching human annotations; no AI labels substitute.
Resources: `{"cuda_initialized": false, "peak_private_commit_bytes": 3303985152, "peak_torch_allocated_bytes": 0, "peak_torch_reserved_bytes": 0, "peak_working_set_bytes": 1353121792, "scope": "Current Python process lifetime; PyTorch allocator only for VRAM"}`.
LLM usage: `{"generation": {"backend_calls": 0, "cache_hits": 30, "input_tokens": 0, "output_tokens": 0, "unknown_usage_attempts": 0}, "judge": {"backend_calls": 0, "cache_hits": 28, "input_tokens": 0, "output_tokens": 0, "unknown_usage_attempts": 0}}`.
