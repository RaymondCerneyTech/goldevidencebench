from __future__ import annotations

import json
import math
import re
import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    from llama_cpp import Llama
except ImportError as exc:  # pragma: no cover - optional dependency
    raise ImportError("llama_cpp not installed; install via `pip install llama-cpp-python`") from exc

from goldevidencebench.util import get_env


@dataclass(frozen=True)
class DocRecord:
    doc_id: str
    text: str
    title: str | None = None


def _tokenize(text: str) -> list[str]:
    if not text:
        return []
    tokens = re.sub(r"[^0-9a-zA-Z]+", " ", text.lower()).split()
    return [tok for tok in tokens if tok]


def _bm25_scores(docs: list[DocRecord], query: str) -> list[float]:
    doc_tokens = [_tokenize(doc.text) for doc in docs]
    query_tokens = _tokenize(query)
    if not doc_tokens:
        return []
    if not query_tokens:
        return [0.0 for _ in doc_tokens]
    doc_lens = [len(tokens) for tokens in doc_tokens]
    avgdl = sum(doc_lens) / len(doc_lens) if doc_lens else 0.0
    df: dict[str, int] = {}
    for tokens in doc_tokens:
        for tok in set(tokens):
            df[tok] = df.get(tok, 0) + 1
    k1 = 1.5
    b = 0.75
    scores: list[float] = []
    for tokens, dl in zip(doc_tokens, doc_lens):
        score = 0.0
        for tok in query_tokens:
            n = df.get(tok, 0)
            if n == 0:
                continue
            idf = math.log((len(doc_tokens) - n + 0.5) / (n + 0.5) + 1.0)
            tf = tokens.count(tok)
            denom = tf + k1 * (1.0 - b + b * (dl / avgdl if avgdl else 0.0))
            score += idf * ((tf * (k1 + 1.0)) / denom)
        scores.append(score)
    return scores


_DENSE_DIM = 256


def _dense_vector(tokens: list[str], dim: int = _DENSE_DIM) -> list[float]:
    vec = [0.0] * dim
    for tok in tokens:
        digest = hashlib.md5(tok.encode("utf-8")).digest()
        idx = int.from_bytes(digest[:4], "little") % dim
        sign = 1.0 if (digest[4] & 1) == 0 else -1.0
        vec[idx] += sign
    return vec


def _dense_cosine(vec_a: list[float], vec_b: list[float]) -> float:
    if not vec_a or not vec_b:
        return 0.0
    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    na = math.sqrt(sum(a * a for a in vec_a))
    nb = math.sqrt(sum(b * b for b in vec_b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


def _load_doc_index(path: Path) -> list[DocRecord]:
    if not path.exists():
        raise FileNotFoundError(path)
    docs: list[DocRecord] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        row = json.loads(line)
        if not isinstance(row, dict):
            continue
        doc_id = row.get("id") or row.get("doc_id")
        text = row.get("text") or row.get("content") or row.get("document")
        if not doc_id or not text:
            continue
        docs.append(DocRecord(doc_id=str(doc_id), text=str(text), title=row.get("title")))
    if not docs:
        raise ValueError(f"No docs loaded from {path}")
    return docs


def _extract_json(text: str) -> dict[str, Any] | None:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None


class OpenBookRetrievalAdapter:
    """
    Minimal open-book adapter that retrieves from a doc index and prompts the model with top-k docs.
    Doc index JSONL rows must include: {"id": "...", "text": "..."}.
    """

    def __init__(
        self,
        model_path: str | None = None,
        doc_index_path: str | None = None,
        retriever_mode: str | None = None,
        top_k: int | None = None,
        n_ctx: int = 2048,
        n_threads: int | None = None,
    ) -> None:
        model_path = model_path or get_env("MODEL")
        if not model_path:
            raise ValueError("Set GOLDEVIDENCEBENCH_MODEL to a GGUF model path or pass model_path.")
        self.llm = Llama(model_path=model_path, n_ctx=n_ctx, n_threads=n_threads)
        doc_index_path = doc_index_path or get_env("RAG_DOC_INDEX")
        if not doc_index_path:
            raise ValueError("Set RAG_DOC_INDEX to a JSONL doc index path.")
        self.docs = _load_doc_index(Path(doc_index_path))
        self.retriever_mode = (retriever_mode or get_env("RAG_RETRIEVER_MODE", "bm25")).lower()
        self.top_k = int(top_k or get_env("RAG_TOP_K", "3"))
        self._last_diag: dict[str, Any] | None = None
        self._last_perf: dict[str, Any] | None = None

    def _retrieve(self, query: str) -> list[DocRecord]:
        if self.retriever_mode == "dense":
            doc_vecs = [_dense_vector(_tokenize(doc.text)) for doc in self.docs]
            query_vec = _dense_vector(_tokenize(query))
            scores = [_dense_cosine(vec, query_vec) for vec in doc_vecs]
        else:
            scores = _bm25_scores(self.docs, query)
        ranked = sorted(range(len(self.docs)), key=lambda i: scores[i], reverse=True)
        top = ranked[: max(1, self.top_k)]
        picked = [self.docs[i] for i in top]
        self._last_diag = {
            "retriever_mode": self.retriever_mode,
            "top_k": self.top_k,
            "top_ids": [doc.doc_id for doc in picked],
        }
        return picked

    def _build_prompt(self, docs: list[DocRecord], question: str) -> str:
        doc_blocks = []
        for doc in docs:
            header = f"[DOC {doc.doc_id}]"
            if doc.title:
                header += f" {doc.title}"
            doc_blocks.append(f"{header}\n{doc.text}")
        context = "\n\n".join(doc_blocks)
        return (
            "You are answering from provided documents.\n"
            "Return JSON: {\"value\": <answer>, \"support_ids\": [\"<doc_id>\"]}\n\n"
            f"DOCUMENTS:\n{context}\n\n"
            f"QUESTION:\n{question}\n"
        )

    def predict(self, row: dict[str, Any], *, protocol: str = "open_book") -> dict[str, Any]:
        if protocol != "open_book":
            raise ValueError("OpenBookRetrievalAdapter supports open_book only.")
        question = row.get("question", "")
        docs = self._retrieve(question)
        prompt = self._build_prompt(docs, question)
        resp = self.llm.create_completion(prompt=prompt, max_tokens=96, stop=["\n\nQUESTION:"])
        usage = resp.get("usage") if isinstance(resp, dict) else None
        if isinstance(usage, dict):
            total = usage.get("total_tokens")
            prompt_tokens = usage.get("prompt_tokens")
            completion_tokens = usage.get("completion_tokens")
            if isinstance(total, (int, float)):
                self._last_perf = {
                    "total_tokens": int(total),
                    "prompt_tokens": int(prompt_tokens) if isinstance(prompt_tokens, (int, float)) else None,
                    "completion_tokens": int(completion_tokens) if isinstance(completion_tokens, (int, float)) else None,
                }
        text = resp["choices"][0]["text"]
        parsed = _extract_json(text) or {}
        value = parsed.get("value")
        support_ids = parsed.get("support_ids")
        if not isinstance(support_ids, list):
            support_ids = []
        if not support_ids and docs:
            support_ids = [docs[0].doc_id]
        return {"value": value, "support_ids": support_ids}

    def take_diag(self) -> dict[str, Any] | None:
        diag = self._last_diag
        self._last_diag = None
        return diag

    def take_perf(self) -> dict[str, Any] | None:
        perf = self._last_perf
        self._last_perf = None
        return perf


def create_adapter():
    return OpenBookRetrievalAdapter()
