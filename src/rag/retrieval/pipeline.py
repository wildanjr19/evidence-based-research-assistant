from rag.config import Config
from rag.indexing.embedding import Embedder, SentenceEmbedder, embed_chunks, embedding_identity
from rag.retrieval.fusion import reciprocal_rank_fusion
from rag.retrieval.rerank import Reranker, rerank
from rag.retrieval.store import RetrievalStore

MODES = ("bm25", "dense", "hybrid", "hybrid+rerank")


class Retriever:
    def __init__(
        self, config: Config, embedder: Embedder | None = None, reranker: Reranker | None = None
    ) -> None:
        self.config = config
        self.store = RetrievalStore(config)
        self.embedder = embedder
        self.reranker = reranker
        self.statistics: dict = {}

    def retrieve(
        self, question: str, mode: str | None = None, top_k: int | None = None
    ) -> list[dict]:
        config = self.config
        mode = mode or ("hybrid+rerank" if config.retrieval.use_reranker else "hybrid")
        if mode not in MODES:
            raise ValueError(f"Unknown retrieval mode: {mode}")
        if not isinstance(question, str) or not question.strip():
            raise ValueError("Question must be a non-empty string")
        limit = config.retrieval.final_top_k if top_k is None else top_k
        if type(limit) is not int or limit < 1:
            raise ValueError("top_k must be a positive integer")
        self.statistics = {}
        if not any(c["quality_flag"] != "low_quality" for c in self.store.chunks.values()):
            return []
        dense, keyword = [], []
        if mode != "dense":
            keyword = self.store.bm25(question, config.retrieval.bm25_top_k)
        if mode != "bm25":
            if self.embedder is None:
                self.embedder = SentenceEmbedder(config)
            self.store.open_vectors(embedding_identity(config, self.embedder))
            vectors, stats = embed_chunks(
                [{"chunk_id": "query", "text": config.retrieval.query_prefix + question}],
                config,
                self.embedder,
            )
            self.statistics.update(stats)
            dense = self.store.dense(vectors[0], config.retrieval.dense_top_k)
        if mode == "bm25":
            hits = keyword
        elif mode == "dense":
            hits = dense
        else:
            hits = reciprocal_rank_fusion(
                [
                    [identifier for identifier, _ in dense],
                    [identifier for identifier, _ in keyword],
                ],
                config.retrieval.rrf_k,
            )[: config.retrieval.rerank_candidates]
        if mode == "hybrid+rerank" and hits:
            hits, self.reranker, stats = rerank(
                question,
                [self.store.chunks[key] for key, _ in hits],
                config,
                self.reranker,
            )
            self.statistics.update(stats)
        score_type = {"bm25": "bm25", "dense": "cosine", "hybrid": "rrf", "hybrid+rerank": "logit"}
        return [
            dict(self.store.chunks[key], score=score, score_type=score_type[mode], rank=rank)
            for rank, (key, score) in enumerate(hits[:limit], 1)
        ]


def retrieve(question: str, config: Config, mode: str | None = None) -> list[dict]:
    return Retriever(config).retrieve(question, mode)
