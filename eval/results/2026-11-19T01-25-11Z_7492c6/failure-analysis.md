# Analisis hasil M6

Catatan ini dibuat AI dari hasil evaluasi; bukan adjudikasi manusia atau perubahan gold.

MiniCheck labels: `{"not_supported": 15, "supported": 94}`.
Judge labels: `{"supported": 28}`.

## Kontrol unanswerable

| QID | Status generation | Klaim |
|---|---|---:|
| multi027 | no_evidence | 0 |
| multi028 | no_evidence | 0 |
| multi029 | ok | 1 |
| multi030 | no_evidence | 0 |

Klaim pada kontrol tetap dihitung gagal meskipun pasangan evidence mendukung fakta yang disampaikan.

## Pasangan yang tidak didukung MiniCheck

Ketidaksepakatan dengan judge perlu dibaca sebagai hasil antar-model. Label supported judge tidak otomatis membatalkan label MiniCheck atau menjadi gold.

### multi002 / arxiv:2408.10343v1:p5:c24

Klaim: Table 3 shows 194 queries for each of PrivacyQA, CUAD, MAUD, and ContractNLI, totaling 776 queries in LegalBench-RAG-mini.

MiniCheck: not_supported (score 0.09016820788383484). Judge: supported.
Alasan judge: The evidence explicitly states that Table 3 summarizes the datasets in LegalBench-RAG-mini, including the number of queries for PrivacyQA, CUAD, MAUD, and ContractNLI, confirming that there are 194 queries for each of these datasets, totaling 776 queries.

### multi003 / arxiv:2408.10343v1:p5:c20

Klaim: For each relevant snippet in a LegalBench-RAG QA pair, the file path, the exact quote, and the precise character indices within the document are provided.

MiniCheck: not_supported (score 0.07934152334928513). Judge: supported.
Alasan judge: The evidence explicitly states that for each relevant snippet in the LegalBench-RAG QA pairs, the file path, the exact quote, and the precise character indices within the document are provided, which directly supports the claim.

### multi004 / arxiv:2504.17137v1:p12:c60

Klaim: The five source datasets of MIRAGE are PopQA, NQ, IfQA, DROP, and TriviaQA.

MiniCheck: not_supported (score 0.0558587908744812). Judge: tidak disampel.

### multi007 / arxiv:2505.07671v2:p3:c14

Klaim: Table 1 lists MMLU-Chem and ChemBench4K as Multi-Choice and Mol-Instructions as Open-Ended.

MiniCheck: not_supported (score 0.2789474427700043). Judge: tidak disampel.

### multi009 / arxiv:2505.07671v2:p5:c18

Klaim: CHEMRAG-TOOLKIT selects four representative retrievers: BM25, Contriever, SPECTER, and e5.

MiniCheck: not_supported (score 0.015570669434964657). Judge: supported.
Alasan judge: The evidence explicitly states that CHEMRAG-TOOLKIT selects four representative retrievers: BM25, Contriever, SPECTER, and e5, which directly supports the claim.

### multi014 / arxiv:2408.10343v1:p7:c32

Klaim: In its preprocessing experiment, LegalBench-RAG fixed all hyperparameters and compared a naive chunking strategy with a Recursive Text Character Splitter (RTCS).

MiniCheck: not_supported (score 0.03926215320825577). Judge: tidak disampel.

### multi014 / arxiv:2408.10343v1:p7:c33

Klaim: In its postprocessing experiment, LegalBench-RAG froze all other hyperparameters and compared using no reranking strategy of the retrieved chunks with using Cohere's Reranker model.

MiniCheck: not_supported (score 0.04143218696117401). Judge: tidak disampel.

### multi016 / arxiv:2504.17137v1:p8:c36

Klaim: The consistency of context insensitivity and context misinterpretation across retrievers indicates that the ability to utilize context properly relies solely on the LLM's capabilities.

MiniCheck: not_supported (score 0.029087215662002563). Judge: tidak disampel.

### multi017 / arxiv:2505.07671v2:p4:c16

Klaim: For open-ended questions, generated molecules are evaluated by exact match (EM), validity, MACCS FTS, RDK FTS, Morgan FTS, and BLEU.

MiniCheck: not_supported (score 0.015347280539572239). Judge: tidak disampel.

### multi023 / arxiv:2605.14488v1:p8:c18

Klaim: Deepchecks decomposes RAG evaluation into properties including Retrieval Relevance, which measures that retrieved information is relevant for addressing the input question.

MiniCheck: not_supported (score 0.08684525638818741). Judge: supported.
Alasan judge: The evidence explicitly states that the retrieved information is relevant for addressing the input question, which directly supports the claim about Deepchecks decomposing RAG evaluation into properties including Retrieval Relevance.

### multi023 / arxiv:2505.07671v2:p2:c10

Klaim: CHEMRAG reports an average relative performance improvement of 17.4% when using CHEMRAG compared to direct inference without retrieval.

MiniCheck: not_supported (score 0.18808193504810333). Judge: supported.
Alasan judge: The evidence explicitly states that there is an average relative improvement of 17.4% when applying CHEMRAG over direct inference, which directly supports the claim.

### multi024 / arxiv:2504.17137v1:p7:c34

Klaim: MIRAGE results show that increasing retrieved chunks from Top-1 to Top-3 generally improves performance, but advancing to Top-5 retrieval often introduces additional noise and leads to performance degradation in some configurations.

MiniCheck: not_supported (score 0.18080011010169983). Judge: tidak disampel.

### multi024 / arxiv:2504.17137v1:p7:c34

Klaim: In MIRAGE, the performance degradation from additional noisy chunks at Top-5 is particularly prominent in models like GPT-3.5-Turbo and Llama-2-7B-Chat, which show decreased scores when handling additional noisy chunks.

MiniCheck: not_supported (score 0.08285145461559296). Judge: tidak disampel.

### multi026 / arxiv:2605.14488v1:p11:c25

Klaim: Deepchecks' Grounded in Context was benchmarked against other established approaches using ROC-AUC, with datasets including TRUE, SQuAD, and PubmedQA.

MiniCheck: not_supported (score 0.4738200902938843). Judge: tidak disampel.

### multi026 / arxiv:2605.14488v1:p11:c25

Klaim: In Table 1, Deepchecks' Grounded in Context scored 0.86 on TRUE, 0.92 on SQuAD, and 0.84 on PubmedQA.

MiniCheck: not_supported (score 0.1403452455997467). Judge: supported.
Alasan judge: The evidence explicitly lists the scores for Deepchecks' Grounded in Context as 0.86 for TRUE, 0.92 for SQuAD, and 0.84 for PubmedQA, which directly supports the claim.

## Per tipe pertanyaan

- lookup: `{"abstention_accuracy": null, "citation_pair_count": 30, "citation_precision": 0.8333333333333334, "citation_recall": 0.8214285714285714, "claim_count": 28, "failed_question_count": 0, "faithfulness": 0.8214285714285714, "hallucinated_citation_rate": 0.0, "supported_pair_count": 25, "unanswerable_claim_count": 0, "unanswerable_count": 0, "unverified_pair_count": 0}`.
- comparison: `{"abstention_accuracy": null, "citation_pair_count": 35, "citation_precision": 0.8857142857142857, "citation_recall": 0.9354838709677419, "claim_count": 31, "failed_question_count": 0, "faithfulness": 0.9354838709677419, "hallucinated_citation_rate": 0.0, "supported_pair_count": 31, "unanswerable_claim_count": 0, "unanswerable_count": 0, "unverified_pair_count": 0}`.
- synthesis: `{"abstention_accuracy": null, "citation_pair_count": 44, "citation_precision": 0.8636363636363636, "citation_recall": 0.9024390243902439, "claim_count": 41, "failed_question_count": 0, "faithfulness": 0.9024390243902439, "hallucinated_citation_rate": 0.0, "supported_pair_count": 38, "unanswerable_claim_count": 0, "unanswerable_count": 0, "unverified_pair_count": 0}`.
- unanswerable: `{"abstention_accuracy": 0.75, "citation_pair_count": 0, "citation_precision": null, "citation_recall": 0.0, "claim_count": 1, "failed_question_count": 0, "faithfulness": 0.0, "hallucinated_citation_rate": null, "supported_pair_count": 0, "unanswerable_claim_count": 1, "unanswerable_count": 4, "unverified_pair_count": 0}`.

## Pekerjaan berikutnya

Pertahankan hasil baseline ini. M7 dapat menampilkan hasil verifikasi dan sitasi; evaluasi kualitas berikutnya harus memakai versi eksperimen baru, tanpa menyesuaikan gold untuk menaikkan skor.
