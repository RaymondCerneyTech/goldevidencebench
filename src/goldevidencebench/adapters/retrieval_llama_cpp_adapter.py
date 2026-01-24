from __future__ import annotations

import json
import os
import re
import math
import hashlib
from dataclasses import dataclass
from typing import Any
import random

from goldevidencebench.baselines import parse_book_ledger
from goldevidencebench.book import LedgerEntry, render_book
from goldevidencebench.adapters.llama_prompt import extract_ledger, truncate_tokens, build_prompt
from goldevidencebench.util import get_env


@dataclass(frozen=True)
class RetrievalConfig:
    include_clear: bool = True
    k: int = 1
    wrong_type: str = "none"  # none|same_key|other_key
    retriever_mode: str = "key"  # key|bm25|tfidf|dense
    drop_prob: float = 0.0
    drop_seed: int = 0
    authority_spoof_rate: float = 0.0
    authority_spoof_seed: int = 0
    order: str = "shuffle"  # shuffle|gold_first|gold_middle|gold_last
    order_seed: int = 0
    query_sandwich: bool = False
    pick_then_answer: bool = False
    deterministic_answerer: bool = False
    copy_clamp: bool = False
    abstain_on_missing: bool = False
    rerank_mode: str = "none"  # none|latest_step|last_occurrence|prefer_set_latest|prefer_update_latest|linear
    selection_only: bool = False
    selection_value: bool = False
    authority_filter: bool = False
    step_bucket: int = 1
    linear_tie_break: str = "none"
    linear_tie_eps: float = 0.0


@dataclass(frozen=True)
class LinearSelectorModel:
    feature_order: list[str]
    weights: list[float]


_LINEAR_FEATURE_ORDER = [
    "bias",
    "step_norm",
    "step_delta_norm",
    "is_latest_step",
    "is_second_latest_step",
    "recency_rank_norm",
    "recency_rank_inv",
    "step_gap_range_norm",
    "pos_norm",
    "is_set",
    "is_clear",
    "is_add",
    "is_remove",
    "is_note",
    "is_authoritative",
    "is_update",
    "key_in_question",
    "value_in_question",
    "value_token_overlap",
    "question_len_norm",
    "value_len_norm",
]


def _sorted_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(entries, key=lambda e: int(e.get("step", -1)), reverse=True)

def _filter_authoritative(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not entries:
        return entries
    non_note = [e for e in entries if str(e.get("op", "")).upper() != "NOTE"]
    return non_note if non_note else entries


def _latest_entry_for_key(book: str, key: str) -> dict[str, Any] | None:
    entries = parse_book_ledger(book)
    key_entries = [e for e in entries if e.get("key") == key]
    if not key_entries:
        return None
    return _sorted_entries(key_entries)[0]


def _select_entries_for_key(
    *, entries: list[dict[str, Any]], key: str, k: int, wrong_type: str
) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any] | None]:
    key_entries = [e for e in entries if e.get("key") == key]
    sorted_key = _sorted_entries(key_entries)
    correct = sorted_key[0] if sorted_key else None
    selected = sorted_key[: max(1, k)]
    wrong_entry = None
    if wrong_type == "same_key":
        if len(sorted_key) > len(selected):
            wrong_entry = sorted_key[len(selected)]
    elif wrong_type == "other_key":
        other_entries = _sorted_entries([e for e in entries if e.get("key") != key])
        if other_entries:
            wrong_entry = other_entries[0]
    if wrong_entry and wrong_entry not in selected:
        selected.append(wrong_entry)
    wrong_info = wrong_entry
    selected_sorted = sorted(selected, key=lambda e: int(e.get("step", -1)))
    correct_rank = None
    if correct and correct in selected:
        ranked = _sorted_entries(selected)
        correct_rank = 1 + ranked.index(correct)
    diag = {
        "k": k,
        "wrong_type": wrong_type,
        "correct_uid": correct.get("uid") if correct else None,
        "correct_included": correct in selected if correct else False,
        "correct_rank": correct_rank,
        "selected_count": len(selected),
    }
    return selected_sorted, diag, wrong_info


def _apply_drop_with_rng(
    *,
    selected: list[dict[str, Any]],
    correct_uid: str | None,
    wrong_entry: dict[str, Any] | None,
    drop_prob: float,
    rng: random.Random,
) -> tuple[list[dict[str, Any]], bool]:
    if not correct_uid or drop_prob <= 0.0:
        return selected, False
    if rng.random() >= drop_prob:
        return selected, False
    remaining = [e for e in selected if e.get("uid") != correct_uid]
    if not remaining and wrong_entry is not None:
        remaining = [wrong_entry]
    return remaining, True



def _apply_authority_spoof(
    *, selected: list[dict[str, Any]], rate: float, rng: random.Random
) -> tuple[list[dict[str, Any]], int]:
    if not selected or rate <= 0.0:
        return selected, 0
    spoofed: list[dict[str, Any]] = []
    spoofed_count = 0
    for entry in selected:
        if rng.random() < rate:
            spoofed_count += 1
            spoofed_entry = dict(entry)
            op = str(entry.get("op", "")).upper()
            spoofed_entry["op"] = "SET" if op == "NOTE" else "NOTE"
            spoofed_entry["authority_spoofed"] = True
            spoofed.append(spoofed_entry)
        else:
            clean_entry = dict(entry)
            clean_entry["authority_spoofed"] = False
            spoofed.append(clean_entry)
    return spoofed, spoofed_count


def _apply_order(
    *, selected: list[dict[str, Any]], correct_uid: str | None, order: str
) -> tuple[list[dict[str, Any]], str | None]:
    if order not in {"gold_first", "gold_middle", "gold_last"}:
        return selected, None
    if not correct_uid or not selected:
        return selected, None
    rest = [e for e in selected if e.get("uid") != correct_uid]
    gold = [e for e in selected if e.get("uid") == correct_uid]
    if not gold:
        return selected, None
    if order == "gold_first":
        return gold + rest, "gold_first"
    if order == "gold_last":
        return rest + gold, "gold_last"
    mid = len(rest) // 2
    return rest[:mid] + gold + rest[mid:], "gold_middle"


def _rerank_latest_step(entries: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not entries:
        return None
    return max(entries, key=lambda e: int(e.get("step", -1)))


def _rerank_last_occurrence(entries: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not entries:
        return None
    return entries[-1]


def _rerank_prefer_set_latest(entries: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not entries:
        return None
    set_entries = [e for e in entries if e.get("op") == "SET"]
    candidates = set_entries if set_entries else entries
    return max(candidates, key=lambda e: int(e.get("step", -1)))

def _rerank_prefer_update_latest(entries: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not entries:
        return None
    non_note = [e for e in entries if str(e.get("op", "")).upper() != "NOTE"]
    candidates = non_note if non_note else entries
    return max(candidates, key=lambda e: int(e.get("step", -1)))



def _tokenize(text: str) -> list[str]:
    if not text:
        return []
    tokens = re.sub(r"[^0-9a-zA-Z]+", " ", text.lower()).split()
    return [tok for tok in tokens if tok]


def _entry_text(entry: dict[str, Any]) -> str:
    return f"{entry.get('op','')} {entry.get('key','')} {entry.get('value','')}"


def _bm25_scores(entries: list[dict[str, Any]], query: str) -> list[float]:
    docs = [_tokenize(_entry_text(entry)) for entry in entries]
    query_tokens = _tokenize(query)
    if not docs:
        return []
    if not query_tokens:
        return [0.0 for _ in docs]
    doc_lens = [len(doc) for doc in docs]
    avgdl = sum(doc_lens) / len(doc_lens) if doc_lens else 0.0
    df: dict[str, int] = {}
    for doc in docs:
        for tok in set(doc):
            df[tok] = df.get(tok, 0) + 1
    k1 = 1.5
    b = 0.75
    scores: list[float] = []
    for doc, dl in zip(docs, doc_lens):
        score = 0.0
        for tok in query_tokens:
            n = df.get(tok, 0)
            if n == 0:
                continue
            idf = math.log((len(docs) - n + 0.5) / (n + 0.5) + 1.0)
            tf = doc.count(tok)
            denom = tf + k1 * (1.0 - b + b * (dl / avgdl if avgdl else 0.0))
            score += idf * ((tf * (k1 + 1.0)) / denom)
        scores.append(score)
    return scores


def _select_entries_bm25(
    *, entries: list[dict[str, Any]], question: str, key: str, k: int
) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any] | None]:
    key_entries = [e for e in entries if e.get('key') == key]
    sorted_key = _sorted_entries(key_entries)
    correct = sorted_key[0] if sorted_key else None
    scores = _bm25_scores(entries, question)
    ranked_indices = sorted(range(len(entries)), key=lambda i: scores[i], reverse=True)
    selected = [entries[i] for i in ranked_indices[: max(1, k)]]
    selected_sorted = sorted(selected, key=lambda e: int(e.get('step', -1)))
    correct_rank = None
    if correct and correct in selected:
        correct_rank = 1 + ranked_indices[: max(1, k)].index(entries.index(correct))
    diag = {
        'k': k,
        'wrong_type': 'bm25',
        'correct_uid': correct.get('uid') if correct else None,
        'correct_included': correct in selected if correct else False,
        'correct_rank': correct_rank,
        'selected_count': len(selected),
    }
    return selected_sorted, diag, None


def _tfidf_vectors(entries: list[dict[str, Any]], query: str) -> tuple[list[dict[str, float]], dict[str, float]]:
    docs = [_tokenize(_entry_text(entry)) for entry in entries]
    query_tokens = _tokenize(query)
    if not docs:
        return [], {}
    df: dict[str, int] = {}
    for doc in docs:
        for tok in set(doc):
            df[tok] = df.get(tok, 0) + 1
    n_docs = len(docs)
    idf = {tok: math.log((n_docs + 1) / (df_val + 1)) + 1.0 for tok, df_val in df.items()}
    doc_vecs: list[dict[str, float]] = []
    for doc in docs:
        vec: dict[str, float] = {}
        for tok in doc:
            vec[tok] = vec.get(tok, 0.0) + 1.0
        for tok in list(vec.keys()):
            vec[tok] = vec[tok] * idf.get(tok, 0.0)
        doc_vecs.append(vec)
    query_vec: dict[str, float] = {}
    for tok in query_tokens:
        query_vec[tok] = query_vec.get(tok, 0.0) + 1.0
    for tok in list(query_vec.keys()):
        query_vec[tok] = query_vec[tok] * idf.get(tok, 0.0)
    return doc_vecs, query_vec


def _cosine_similarity(a: dict[str, float], b: dict[str, float]) -> float:
    if not a or not b:
        return 0.0
    dot = sum(val * b.get(tok, 0.0) for tok, val in a.items())
    na = math.sqrt(sum(val * val for val in a.values()))
    nb = math.sqrt(sum(val * val for val in b.values()))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


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

def _select_entries_dense(
    *, entries: list[dict[str, Any]], question: str, key: str, k: int
) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any] | None]:
    key_entries = [e for e in entries if e.get('key') == key]
    sorted_key = _sorted_entries(key_entries)
    correct = sorted_key[0] if sorted_key else None
    doc_vecs = [_dense_vector(_tokenize(_entry_text(entry))) for entry in entries]
    query_vec = _dense_vector(_tokenize(question))
    scores = [_dense_cosine(vec, query_vec) for vec in doc_vecs]
    ranked_indices = sorted(range(len(entries)), key=lambda i: scores[i], reverse=True)
    selected = [entries[i] for i in ranked_indices[: max(1, k)]]
    selected_sorted = sorted(selected, key=lambda e: int(e.get('step', -1)))
    correct_rank = None
    if correct and correct in selected:
        correct_rank = 1 + ranked_indices[: max(1, k)].index(entries.index(correct))
    diag = {
        'k': k,
        'wrong_type': 'dense',
        'correct_uid': correct.get('uid') if correct else None,
        'correct_included': correct in selected if correct else False,
        'correct_rank': correct_rank,
        'selected_count': len(selected),
    }
    return selected_sorted, diag, None


def _select_entries_tfidf(
    *, entries: list[dict[str, Any]], question: str, key: str, k: int
) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any] | None]:
    key_entries = [e for e in entries if e.get('key') == key]
    sorted_key = _sorted_entries(key_entries)
    correct = sorted_key[0] if sorted_key else None
    doc_vecs, query_vec = _tfidf_vectors(entries, question)
    scores = [_cosine_similarity(vec, query_vec) for vec in doc_vecs]
    ranked_indices = sorted(range(len(entries)), key=lambda i: scores[i], reverse=True)
    selected = [entries[i] for i in ranked_indices[: max(1, k)]]
    selected_sorted = sorted(selected, key=lambda e: int(e.get('step', -1)))
    correct_rank = None
    if correct and correct in selected:
        correct_rank = 1 + ranked_indices[: max(1, k)].index(entries.index(correct))
    diag = {
        'k': k,
        'wrong_type': 'tfidf',
        'correct_uid': correct.get('uid') if correct else None,
        'correct_included': correct in selected if correct else False,
        'correct_rank': correct_rank,
        'selected_count': len(selected),
    }
    return selected_sorted, diag, None


def _linear_features(
    *,
    entry: dict[str, Any],
    entries: list[dict[str, Any]],
    index: int,
    total: int,
    max_step: int,
    step_bucket: int = 1,
    question: str,
    key: str,
) -> list[float]:
    step_bucket = max(1, int(step_bucket))
    step = int(entry.get("step", 0)) // step_bucket
    step_norm = step / max_step if max_step else 0.0
    step_delta_norm = ((max_step - step) / max_step) if max_step else 0.0
    is_latest_step = 1.0 if step == max_step else 0.0
    steps = sorted({int(other.get("step", 0)) // step_bucket for other in entries}, reverse=True)
    second_latest = steps[1] if len(steps) > 1 else None
    is_second_latest_step = 1.0 if second_latest is not None and step == second_latest else 0.0
    recency_rank = 0
    for other in entries:
        if (int(other.get("step", 0)) // step_bucket) > step:
            recency_rank += 1
    recency_rank_norm = recency_rank / (total - 1) if total > 1 else 0.0
    recency_rank_inv = 1.0 / (1.0 + recency_rank)
    min_step = min(int(other.get("step", 0)) // step_bucket for other in entries)
    step_range = max(max_step - min_step, 1)
    step_gap_range_norm = (max_step - step) / step_range
    pos_norm = index / (total - 1) if total > 1 else 0.0
    op = str(entry.get("op", "")).upper()
    question_lower = (question or "").lower()
    value = str(entry.get("value", ""))
    key_in_question = 1.0 if key and key.lower() in question_lower else 0.0
    value_in_question = 1.0 if value and value.lower() in question_lower else 0.0
    question_tokens = _tokenize(question_lower)
    value_tokens = _tokenize(value)
    if value_tokens:
        overlap = len(set(value_tokens) & set(question_tokens)) / len(set(value_tokens))
    else:
        overlap = 0.0
    question_len_norm = min(len(question_tokens) / 20.0, 1.0)
    value_len_norm = min(len(value_tokens) / 10.0, 1.0)
    is_note = 1.0 if op == "NOTE" else 0.0
    is_authoritative = 0.0 if op == "NOTE" else 1.0
    is_update = 1.0 if op in {"SET", "ADD", "REMOVE", "CLEAR"} else 0.0
    return [
        1.0,
        step_norm,
        step_delta_norm,
        is_latest_step,
        is_second_latest_step,
        recency_rank_norm,
        recency_rank_inv,
        step_gap_range_norm,
        pos_norm,
        1.0 if op == "SET" else 0.0,
        1.0 if op == "CLEAR" else 0.0,
        1.0 if op == "ADD" else 0.0,
        1.0 if op == "REMOVE" else 0.0,
        is_note,
        is_authoritative,
        is_update,
        key_in_question,
        value_in_question,
        overlap,
        question_len_norm,
        value_len_norm,
    ]


def _rerank_linear(
    entries: list[dict[str, Any]],
    model: LinearSelectorModel,
    *,
    question: str,
    key: str,
    step_bucket: int = 1,
    linear_tie_break: str = "none",
    linear_tie_eps: float = 0.0,
) -> dict[str, Any] | None:
    if not entries:
        return None
    if model.feature_order != _LINEAR_FEATURE_ORDER:
        model = _align_linear_model(model)
    step_bucket = max(1, int(step_bucket))
    max_step = max(int(entry.get("step", 0)) // step_bucket for entry in entries)
    scores: list[tuple[float, dict[str, Any]]] = []
    for index, entry in enumerate(entries):
        features = _linear_features(
            entry=entry,
            entries=entries,
            index=index,
            total=len(entries),
            max_step=max_step,
            step_bucket=step_bucket,
            question=question,
            key=key,
        )
        score = sum(weight * feature for weight, feature in zip(model.weights, features))
        scores.append((score, entry))
    scores.sort(key=lambda item: item[0], reverse=True)
    if linear_tie_break == "latest_step" and scores:
        max_score = scores[0][0]
        cutoff = max_score - max(0.0, linear_tie_eps)
        tied = [entry for score, entry in scores if score >= cutoff]
        if len(tied) > 1:
            return max(tied, key=lambda e: int(e.get("step", -1)))
    return scores[0][1]



def _align_linear_model(model: LinearSelectorModel) -> LinearSelectorModel:
    if model.feature_order == _LINEAR_FEATURE_ORDER:
        return model
    extra = [feat for feat in model.feature_order if feat not in _LINEAR_FEATURE_ORDER]
    if extra:
        raise ValueError(f"Linear selector feature_order mismatch (extra features: {extra})")
    index = {feat: idx for idx, feat in enumerate(model.feature_order)}
    weights = [model.weights[index[feat]] if feat in index else 0.0 for feat in _LINEAR_FEATURE_ORDER]
    return LinearSelectorModel(feature_order=list(_LINEAR_FEATURE_ORDER), weights=weights)

def _load_linear_model(path: str) -> LinearSelectorModel:
    payload = json.loads(open(path, "r", encoding="utf-8").read())
    feature_order = payload.get("feature_order")
    weights = payload.get("weights")
    if not isinstance(feature_order, list) or not isinstance(weights, list):
        raise ValueError("Invalid linear selector model format.")
    if len(weights) != len(feature_order):
        raise ValueError("Linear selector weights length mismatch.")
    model = LinearSelectorModel(
        feature_order=[str(item) for item in feature_order],
        weights=[float(item) for item in weights],
    )
    return _align_linear_model(model)


def _build_min_book(*, entry: dict[str, Any], key: str, episode_id: str) -> str:
    ledger = [
        LedgerEntry(
            uid=entry["uid"],
            step=entry["step"],
            op=entry["op"],
            key=entry["key"],
            value=entry["value"],
        )
    ]
    glossary = {key: f"Synthetic tag {key} used for state-tracking."}
    return render_book(
        title=f"GoldEvidenceBench Retrieval {episode_id}",
        chapters=[""],
        glossary=glossary,
        ledger=ledger,
    )


def _build_multi_book(*, entries: list[dict[str, Any]], episode_id: str) -> str:
    ledger = [
        LedgerEntry(
            uid=entry["uid"],
            step=entry["step"],
            op=entry["op"],
            key=entry["key"],
            value=entry["value"],
        )
        for entry in entries
    ]
    keys = sorted({entry["key"] for entry in entries})
    glossary = {k: f"Synthetic tag {k} used for state-tracking." for k in keys}
    return render_book(
        title=f"GoldEvidenceBench Retrieval {episode_id}",
        chapters=[""],
        glossary=glossary,
        ledger=ledger,
    )


def _selection_question(question: str, key: str) -> str:
    return (
        f"{question}\n"
        f"Select the single correct support_id for {key} from the ledger above. "
        "Return value null."
    )


def _norm_support_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        out: list[str] = []
        for item in value:
            if item is None:
                continue
            s = str(item).strip()
            if s:
                out.append(s)
        return out
    s = str(value).strip()
    return [s] if s else []



def _norm_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None


def _value_is_substring(*, predicted: Any, entry_value: Any) -> bool:
    predicted_text = _norm_text(predicted)
    entry_text = _norm_text(entry_value)
    if predicted_text is None:
        return entry_text is None
    if entry_text is None:
        return False
    return predicted_text in entry_text


class RetrievalLlamaCppAdapter:
    """
    Retrieval-first adapter:
    - Select latest ledger entry for the question key.
    - Build a minimal book with only that entry.
    - Answer using the standard Llama adapter on the tiny book.
    """

    def __init__(
        self,
        *,
        model_path: str | None = None,
        n_ctx: int = 2048,
        n_threads: int | None = None,
        max_book_tokens: int = 1600,
    ) -> None:
        include_clear_env = get_env("RETRIEVAL_INCLUDE_CLEAR", "1").strip().lower()
        k_env = get_env("RETRIEVAL_K", "1").strip()
        wrong_type = get_env("RETRIEVAL_WRONG_TYPE", "none").strip().lower()
        drop_env = get_env("RETRIEVAL_DROP_PROB", "0").strip()
        drop_seed_env = get_env("RETRIEVAL_DROP_SEED", "0").strip()
        authority_spoof_rate_env = get_env("RETRIEVAL_AUTHORITY_SPOOF_RATE", "0").strip()
        authority_spoof_seed_env = get_env("RETRIEVAL_AUTHORITY_SPOOF_SEED", "0").strip()
        order_env = get_env("RETRIEVAL_ORDER", "shuffle").strip().lower()
        order_seed_env = get_env("RETRIEVAL_ORDER_SEED", "0").strip()
        retriever_env = get_env("RETRIEVAL_RETRIEVER", "key").strip().lower()
        sandwich_env = get_env("RETRIEVAL_QUERY_SANDWICH", "0").strip().lower()
        pick_env = get_env("RETRIEVAL_PICK_THEN_ANSWER", "0").strip().lower()
        deterministic_env = get_env("RETRIEVAL_DETERMINISTIC_ANSWER", "0").strip().lower()
        copy_clamp_env = get_env("RETRIEVAL_COPY_CLAMP", "0").strip().lower()
        rerank_env = get_env("RETRIEVAL_RERANK", "none").strip().lower()
        selection_only_env = get_env("RETRIEVAL_SELECTOR_ONLY", "0").strip().lower()
        selection_value_env = get_env("RETRIEVAL_SELECTOR_VALUE", "0").strip().lower()
        authority_filter_env = get_env("RETRIEVAL_AUTHORITY_FILTER", "0").strip().lower()
        abstain_env = get_env("RETRIEVAL_ABSTAIN_ON_MISSING", "0").strip().lower()
        linear_model_env = get_env("RETRIEVAL_LINEAR_MODEL", "").strip()
        step_bucket_env = get_env("RETRIEVAL_STEP_BUCKET", "1").strip()
        linear_tie_break_env = get_env("RETRIEVAL_LINEAR_TIE_BREAK", "none").strip().lower()
        linear_tie_eps_env = get_env("RETRIEVAL_LINEAR_TIE_EPS", "0").strip()
        try:
            k_val = int(k_env)
        except ValueError:
            k_val = 1
        try:
            drop_prob = float(drop_env)
        except ValueError:
            drop_prob = 0.0
        try:
            drop_seed = int(drop_seed_env)
        except ValueError:
            drop_seed = 0
        try:
            authority_spoof_rate = float(authority_spoof_rate_env)
        except ValueError:
            authority_spoof_rate = 0.0
        try:
            authority_spoof_seed = int(authority_spoof_seed_env)
        except ValueError:
            authority_spoof_seed = 0
        if order_env not in {"shuffle", "gold_first", "gold_middle", "gold_last"}:
            order_env = "shuffle"
        if retriever_env not in {"key", "bm25", "tfidf", "dense"}:
            retriever_env = "key"
        try:
            order_seed = int(order_seed_env)
        except ValueError:
            order_seed = 0
        try:
            step_bucket = int(step_bucket_env)
        except ValueError:
            step_bucket = 1
        step_bucket = max(1, step_bucket)
        if linear_tie_break_env not in {"none", "latest_step"}:
            linear_tie_break_env = "none"
        try:
            linear_tie_eps = float(linear_tie_eps_env)
        except ValueError:
            linear_tie_eps = 0.0
        self.cfg = RetrievalConfig(
            include_clear=include_clear_env not in {"0", "false", "no"},
            k=max(1, k_val),
            wrong_type=wrong_type,
            retriever_mode=retriever_env,
            drop_prob=max(0.0, min(1.0, drop_prob)),
            drop_seed=drop_seed,
            authority_spoof_rate=max(0.0, min(1.0, authority_spoof_rate)),
            authority_spoof_seed=authority_spoof_seed,
            order=order_env,
            order_seed=order_seed,
            query_sandwich=sandwich_env in {"1", "true", "yes"},
            pick_then_answer=pick_env in {"1", "true", "yes"},
            deterministic_answerer=deterministic_env in {"1", "true", "yes"},
            copy_clamp=copy_clamp_env in {"1", "true", "yes"},
            abstain_on_missing=abstain_env in {"1", "true", "yes"},
            rerank_mode=(
                rerank_env
                if rerank_env
                in {"none", "latest_step", "last_occurrence", "prefer_set_latest", "prefer_update_latest", "linear"}
                else "none"
            ),
            selection_only=selection_only_env in {"1", "true", "yes"},
            selection_value=selection_value_env in {"1", "true", "yes"},
            authority_filter=authority_filter_env in {"1", "true", "yes"},
            step_bucket=step_bucket,
            linear_tie_break=linear_tie_break_env,
            linear_tie_eps=max(0.0, linear_tie_eps),
        )
        if self.cfg.selection_only:
            self.cfg = RetrievalConfig(
                include_clear=self.cfg.include_clear,
                k=self.cfg.k,
                wrong_type=self.cfg.wrong_type,
                retriever_mode=self.cfg.retriever_mode,
                drop_prob=self.cfg.drop_prob,
                drop_seed=self.cfg.drop_seed,
                authority_spoof_rate=self.cfg.authority_spoof_rate,
                authority_spoof_seed=self.cfg.authority_spoof_seed,
                order=self.cfg.order,
                order_seed=self.cfg.order_seed,
                query_sandwich=self.cfg.query_sandwich,
                pick_then_answer=False,
                deterministic_answerer=False,
                copy_clamp=False,
                abstain_on_missing=self.cfg.abstain_on_missing,
                rerank_mode=self.cfg.rerank_mode,
                selection_only=True,
                selection_value=self.cfg.selection_value,
                authority_filter=self.cfg.authority_filter,
                step_bucket=self.cfg.step_bucket,
                linear_tie_break=self.cfg.linear_tie_break,
                linear_tie_eps=self.cfg.linear_tie_eps,
            )
        self._linear_model: LinearSelectorModel | None = None
        if self.cfg.rerank_mode == "linear":
            if not linear_model_env:
                raise ValueError("RETRIEVAL_LINEAR_MODEL is required for rerank_mode=linear.")
            self._linear_model = _load_linear_model(linear_model_env)

        self._answerer = None
        if not self.cfg.selection_only:
            from goldevidencebench.adapters.llama_cpp_adapter import LlamaCppAdapter

            self._answerer = LlamaCppAdapter(
                model_path=model_path,
                n_ctx=n_ctx,
                n_threads=n_threads,
                max_book_tokens=max_book_tokens,
                query_sandwich=self.cfg.query_sandwich,
            )
        self._last_diag: dict[str, Any] | None = None

    @property
    def max_book_tokens(self) -> int:
        if self._answerer is None:
            return 0
        return self._answerer.max_book_tokens

    @max_book_tokens.setter
    def max_book_tokens(self, value: int) -> None:
        if self._answerer is None:
            return
        self._answerer.max_book_tokens = value

    def _empty_output(self) -> dict[str, Any]:
        return {"value": "", "support_ids": []}

    def _predict_selection_only(self, row: dict[str, Any]) -> dict[str, Any]:
        book = row.get("book") or row.get("artifact")
        if not book:
            return self._empty_output()
        key = row.get("meta", {}).get("key")
        query_type = row.get("meta", {}).get("query_type")
        if query_type and query_type != "direct":
            return self._empty_output()
        if not key:
            return self._empty_output()
        entries = parse_book_ledger(book)
        if not entries:
            return self._empty_output()
        if self.cfg.authority_filter:
            entries = _filter_authoritative(entries)
            if not entries:
                return self._empty_output()
        if self.cfg.retriever_mode == "bm25":
            selected, diag, wrong_entry = _select_entries_bm25(
                entries=entries, question=row.get("question", ""), key=key, k=self.cfg.k
            )
        elif self.cfg.retriever_mode == "tfidf":
            selected, diag, wrong_entry = _select_entries_tfidf(
                entries=entries, question=row.get("question", ""), key=key, k=self.cfg.k
            )
        else:
            selected, diag, wrong_entry = _select_entries_for_key(
                entries=entries, key=key, k=self.cfg.k, wrong_type=self.cfg.wrong_type
            )
        rng = random.Random(self.cfg.drop_seed ^ hash(row.get("id", "")))
        selected, dropped = _apply_drop_with_rng(
            selected=selected,
            correct_uid=diag.get("correct_uid"),
            wrong_entry=wrong_entry,
            drop_prob=self.cfg.drop_prob,
            rng=rng,
        )
        gold_missing = dropped or diag.get("correct_included") is not True
        if self.cfg.abstain_on_missing and gold_missing:
            self._last_diag = {
                "id": row.get("id"),
                "key": key,
                **diag,
                "drop_prob": self.cfg.drop_prob,
                "dropped_correct": dropped,
                "order": None,
                "authority_spoof_rate": self.cfg.authority_spoof_rate,
                "authority_spoof_count": 0,
                "gold_missing": True,
                "abstained": True,
            }
            return self._empty_output()
        order_applied = None
        if self.cfg.order == "shuffle" and len(selected) > 1:
            shuffle_rng = random.Random(self.cfg.order_seed ^ hash(row.get("id", "")))
            shuffle_rng.shuffle(selected)
            order_applied = "shuffle"
        elif self.cfg.order in {"gold_first", "gold_middle", "gold_last"} and selected:
            selected, order_applied = _apply_order(
                selected=selected, correct_uid=diag.get("correct_uid"), order=self.cfg.order
            )
        spoofed_count = 0
        if self.cfg.authority_spoof_rate > 0.0 and selected:
            spoof_rng = random.Random(self.cfg.authority_spoof_seed ^ hash(row.get("id", "")))
            selected, spoofed_count = _apply_authority_spoof(
                selected=selected, rate=self.cfg.authority_spoof_rate, rng=spoof_rng
            )
        self._last_diag = {
            "id": row.get("id"),
            "key": key,
            **diag,
            "drop_prob": self.cfg.drop_prob,
            "dropped_correct": dropped,
            "order": order_applied,
            "authority_spoof_rate": self.cfg.authority_spoof_rate,
            "authority_spoof_count": spoofed_count,
            "gold_missing": gold_missing,
            "abstained": False,
        }
        if not selected:
            return self._empty_output()
        if self.cfg.rerank_mode != "none":
            if self.cfg.rerank_mode == "latest_step":
                chosen = _rerank_latest_step(selected)
            elif self.cfg.rerank_mode == "last_occurrence":
                chosen = _rerank_last_occurrence(selected)
            elif self.cfg.rerank_mode == "prefer_set_latest":
                chosen = _rerank_prefer_set_latest(selected)
            elif self.cfg.rerank_mode == "prefer_update_latest":
                chosen = _rerank_prefer_update_latest(selected)
            elif self.cfg.rerank_mode == "linear":
                chosen = (
                    _rerank_linear(
                        selected,
                        self._linear_model,
                        question=row.get("question", ""),
                        key=key,
                        step_bucket=self.cfg.step_bucket,
                        linear_tie_break=self.cfg.linear_tie_break,
                        linear_tie_eps=self.cfg.linear_tie_eps,
                    )
                    if self._linear_model is not None
                    else None
                )
            else:
                chosen = None
            self._last_diag = {
                **(self._last_diag or {}),
                "rerank_mode": self.cfg.rerank_mode,
                "reranked_uid": chosen.get("uid") if chosen else None,
            }
        else:
            chosen = selected[0] if selected else None
            self._last_diag = {
                **(self._last_diag or {}),
                "rerank_mode": "none",
                "reranked_uid": chosen.get("uid") if chosen else None,
            }
        if self._last_diag is not None:
            selected_spoofed = None
            if chosen is not None and "authority_spoofed" in chosen:
                selected_spoofed = bool(chosen.get("authority_spoofed"))
            self._last_diag = {
                **self._last_diag,
                "selected_uid": chosen.get("uid") if chosen else None,
                "selected_spoofed": selected_spoofed,
            }
        support_ids = [chosen["uid"]] if chosen else []
        if not self.cfg.selection_value:
            return {"value": "", "support_ids": support_ids}
        selected_value = None
        if chosen is not None:
            op = str(chosen.get("op", "")).upper()
            if op != "CLEAR":
                selected_value = chosen.get("value")
        return {"value": selected_value, "support_ids": support_ids}

    def predict(self, row: dict[str, Any], *, protocol: str = "open_book") -> dict[str, Any]:
        if protocol != "closed_book":
            raise ValueError("RetrievalLlamaCppAdapter supports closed_book only.")
        if self.cfg.selection_only:
            return self._predict_selection_only(row)
        book = row.get("book") or row.get("artifact")
        if not book:
            raise ValueError("book/artifact required for closed_book inference.")
        key = row.get("meta", {}).get("key")
        query_type = row.get("meta", {}).get("query_type")
        if query_type and query_type != "direct":
            return self._answerer.predict(row, protocol=protocol)
        if not key:
            return self._answerer.predict(row, protocol=protocol)
        entries = parse_book_ledger(book)
        if not entries:
            return self._answerer.predict(row, protocol=protocol)
        if self.cfg.authority_filter:
            entries = _filter_authoritative(entries)
            if not entries:
                return self._answerer.predict(row, protocol=protocol)
        if self.cfg.retriever_mode == "bm25":
            selected, diag, wrong_entry = _select_entries_bm25(
                entries=entries, question=row.get("question", ""), key=key, k=self.cfg.k
            )
        elif self.cfg.retriever_mode == "tfidf":
            selected, diag, wrong_entry = _select_entries_tfidf(
                entries=entries, question=row.get("question", ""), key=key, k=self.cfg.k
            )
        else:
            selected, diag, wrong_entry = _select_entries_for_key(
                entries=entries, key=key, k=self.cfg.k, wrong_type=self.cfg.wrong_type
            )
        rng = random.Random(self.cfg.drop_seed ^ hash(row.get("id", "")))
        selected, dropped = _apply_drop_with_rng(
            selected=selected,
            correct_uid=diag.get("correct_uid"),
            wrong_entry=wrong_entry,
            drop_prob=self.cfg.drop_prob,
            rng=rng,
        )
        gold_missing = dropped or diag.get("correct_included") is not True
        if self.cfg.abstain_on_missing and gold_missing:
            self._last_diag = {
                "id": row.get("id"),
                "key": key,
                **diag,
                "drop_prob": self.cfg.drop_prob,
                "dropped_correct": dropped,
                "order": None,
                "authority_spoof_rate": self.cfg.authority_spoof_rate,
                "authority_spoof_count": 0,
                "gold_missing": True,
                "abstained": True,
            }
            return self._empty_output()
        order_applied = None
        if self.cfg.order == "shuffle" and len(selected) > 1:
            shuffle_rng = random.Random(self.cfg.order_seed ^ hash(row.get("id", "")))
            shuffle_rng.shuffle(selected)
            order_applied = "shuffle"
        elif self.cfg.order in {"gold_first", "gold_middle", "gold_last"} and selected:
            selected, order_applied = _apply_order(
                selected=selected, correct_uid=diag.get("correct_uid"), order=self.cfg.order
            )
        spoofed_count = 0
        if self.cfg.authority_spoof_rate > 0.0 and selected:
            spoof_rng = random.Random(self.cfg.authority_spoof_seed ^ hash(row.get("id", "")))
            selected, spoofed_count = _apply_authority_spoof(
                selected=selected, rate=self.cfg.authority_spoof_rate, rng=spoof_rng
            )
        self._last_diag = {
            "id": row.get("id"),
            "key": key,
            **diag,
            "drop_prob": self.cfg.drop_prob,
            "dropped_correct": dropped,
            "order": order_applied,
            "authority_spoof_rate": self.cfg.authority_spoof_rate,
            "authority_spoof_count": spoofed_count,
            "gold_missing": gold_missing,
            "abstained": False,
        }
        if not selected:
            return self._answerer.predict(row, protocol=protocol)
        selected_entry: dict[str, Any] | None = None
        if len(selected) == 1:
            entry = selected[0]
            if entry.get("op") == "CLEAR" and not self.cfg.include_clear:
                return self._answerer.predict(row, protocol=protocol)
            mini_book = _build_min_book(entry=entry, key=key, episode_id=row.get("episode_id", "E0000"))
            selected_entry = entry
        else:
            mini_book = _build_multi_book(entries=selected, episode_id=row.get("episode_id", "E0000"))
        if self.cfg.rerank_mode != "none":
            if self.cfg.rerank_mode == "latest_step":
                chosen = _rerank_latest_step(selected)
            elif self.cfg.rerank_mode == "last_occurrence":
                chosen = _rerank_last_occurrence(selected)
            elif self.cfg.rerank_mode == "prefer_set_latest":
                chosen = _rerank_prefer_set_latest(selected)
            elif self.cfg.rerank_mode == "prefer_update_latest":
                chosen = _rerank_prefer_update_latest(selected)
            elif self.cfg.rerank_mode == "linear":
                chosen = (
                    _rerank_linear(
                        selected,
                        self._linear_model,
                        question=row.get("question", ""),
                        key=key,
                        step_bucket=self.cfg.step_bucket,
                        linear_tie_break=self.cfg.linear_tie_break,
                        linear_tie_eps=self.cfg.linear_tie_eps,
                    )
                    if self._linear_model is not None
                    else None
                )
            else:
                chosen = None
            self._last_diag = {
                **(self._last_diag or {}),
                "rerank_mode": self.cfg.rerank_mode,
                "reranked_uid": chosen.get("uid") if chosen else None,
            }
            if chosen:
                mini_book = _build_min_book(
                    entry=chosen,
                    key=chosen["key"],
                    episode_id=row.get("episode_id", "E0000"),
                )
                selected_entry = chosen
        elif self.cfg.pick_then_answer and len(selected) > 1:
            ledger = extract_ledger(mini_book)
            ledger = truncate_tokens(
                ledger,
                self.max_book_tokens,
                tokenize=getattr(self._answerer.llm, "tokenize", None),
                detokenize=getattr(self._answerer.llm, "detokenize", None),
            )
            pick_prompt = build_prompt(
                ledger=ledger,
                question=_selection_question(row["question"], key),
                require_citations=True,
                query_sandwich=self.cfg.query_sandwich,
            )
            picked = self._answerer.predict_raw_from_prompt(
                prompt=pick_prompt, require_citations=True
            )
            picked_ids = _norm_support_list(
                (picked or {}).get("support_ids") or (picked or {}).get("support_id")
            )
            chosen = picked_ids[0] if picked_ids else None
            self._last_diag = {
                **(self._last_diag or {}),
                "pick_then_answer": True,
                "picked_support_id": chosen,
            }
            if chosen:
                chosen_entry = next((e for e in selected if e.get("uid") == chosen), None)
                if chosen_entry:
                    mini_book = _build_min_book(
                        entry=chosen_entry,
                        key=chosen_entry["key"],
                        episode_id=row.get("episode_id", "E0000"),
                    )
                    selected_entry = chosen_entry
        if self._last_diag is not None:
            try:
                answer_entries = parse_book_ledger(mini_book)
            except Exception:
                answer_entries = []
            selected_spoofed = None
            if selected_entry is not None and "authority_spoofed" in selected_entry:
                selected_spoofed = bool(selected_entry.get("authority_spoofed"))
            self._last_diag = {
                **self._last_diag,
                "answer_ledger_entries": len(answer_entries),
                "selected_uid": selected_entry.get("uid") if selected_entry else None,
                "selected_spoofed": selected_spoofed,
            }
        if self.cfg.deterministic_answerer and selected_entry is not None:
            if self._last_diag is not None:
                self._last_diag = {**self._last_diag, "deterministic_answerer": True}
            value = selected_entry.get("value")
            return {"value": value, "support_ids": [selected_entry["uid"]]}
        row_for_adapter = {**row, "book": mini_book}
        pred = self._answerer.predict(row_for_adapter, protocol=protocol)
        if not isinstance(pred, dict):
            return pred
        if self.cfg.copy_clamp and selected_entry is not None:
            matches = _value_is_substring(
                predicted=pred.get("value"),
                entry_value=selected_entry.get("value"),
            )
            if not matches:
                pred = {**pred, "value": None}
            if self._last_diag is not None:
                self._last_diag = {
                    **self._last_diag,
                    "copy_clamp": True,
                    "copy_clamped": not matches,
                }
        return pred

    def take_perf(self) -> dict[str, Any] | None:
        if self._answerer is None:
            return None
        return self._answerer.take_perf()

    def take_raw(self) -> dict[str, Any] | None:
        if self._answerer is None:
            return None
        return self._answerer.take_raw()

    def take_diag(self) -> dict[str, Any] | None:
        diag = self._last_diag
        self._last_diag = None
        return diag


def create_adapter():
    return RetrievalLlamaCppAdapter()
