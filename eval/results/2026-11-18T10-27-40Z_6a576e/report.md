# Citation evaluation: hybrid+rerank

Run: `2026-11-18T10:27:40Z_6a576e`. Status: ok.

Config SHA-256: `e7c1142da317c2e57e6dc336f0e5b1c7b017fc0bbd1b32cd8e2ddd4aa9721988`.

Dataset SHA-256: `9807d87251449a4673784bf4450709bf7a3009046ed3154248cfd4769f8c7082`.

Seed: 42. Questions: 1.

Models and backends: `{"embedding": {"model": "BAAI/bge-base-en-v1.5", "revision": "a5beb1e3e68b9ab74eb54cfd186867f64f240e1a"}, "embedding_backend": "rag.indexing.embedding.SentenceEmbedder", "generator": "deepseek-flash", "generator_backend": "rag.generation.client.OpenAIBackend", "judge": null, "judge_backend": null, "reported_generator_models": ["deepseek-flash"], "reported_judge_models": [], "reranker": {"model": "BAAI/bge-reranker-base", "revision": "2cfc18c9415c912f9d8155881c133215df768a70"}, "reranker_backend": null, "verifier": {"adapter": "minicheck-flan-t5-pair-v1-no-truncation", "backend": "rag.verification.minicheck.MiniCheck", "device": "cpu", "max_tokens": 512, "model": "lytang/MiniCheck-Flan-T5-Large", "revision": "96eafd01cee2d16cf81aaa2fb226b14f422a37b3", "threshold": 0.5}}`.

Question types: `{"lookup": 1}`.

| Metric | Value |
|---|---|
| citation_precision | 1.0 |
| citation_recall | 1.0 |
| faithfulness | 1.0 |
| hallucinated_citation_rate | 0.0 |
| abstention_accuracy | undefined |
| claim_count | 4 |
| citation_pair_count | 4 |
| supported_pair_count | 4 |
| unverified_pair_count | 0 |
| failed_question_count | 0 |
| unanswerable_count | 0 |
| unanswerable_claim_count | 0 |
| verifier_agreement_kappa | undefined |
| manual_matched_pairs | 0 |
| judge_agreement_kappa | undefined |
| judge_matched_pairs | 0 |
| recall@5 | 1.0 |
| recall@10 | 1.0 |
| recall@20 | 1.0 |
| mrr | 0.5 |

MiniCheck pair labels determine primary support metrics; judge results are separate.
Claims on unanswerable questions fail faithfulness. Failed generation is not abstention.
Unknown support and failed generation make aggregate support metrics undefined.
Citation events count unique IDs per claim after M5 deduplication, including rejections.
Manual agreement requires matching human annotations; no AI labels substitute.
Resources: `{"cuda_initialized": false, "peak_private_commit_bytes": 3295924224, "peak_torch_allocated_bytes": 0, "peak_torch_reserved_bytes": 0, "peak_working_set_bytes": 1346326528, "scope": "Current Python process lifetime; PyTorch allocator only for VRAM"}`.
LLM usage: `{"generation": {"backend_calls": 0, "cache_hits": 1, "input_tokens": 0, "output_tokens": 0, "unknown_usage_attempts": 0}, "judge": {"backend_calls": 0, "cache_hits": 0, "input_tokens": 0, "output_tokens": 0, "unknown_usage_attempts": 0}}`.
