"""Lightweight RAG layer for competitive-exam difficulty calibration.

Design goals (MVP):
- No model downloads / no torch / no GPU.
- Embed questions on the fly with sklearn TF-IDF, retrieve top-K via cosine.
- O(N) brute force is fine for <5000 past questions per exam (sub-100ms).
- Architecture point of replacement: swap `embed_query` + `top_k_similar`
  with FAISS + real embeddings (OpenAI text-embedding-3-small or
  sentence-transformers) when scale demands.
"""
from __future__ import annotations

import re
from collections import Counter
from typing import Iterable

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


_TOK_RE = re.compile(r"[A-Za-z0-9]+")


def _normalise(text: str) -> str:
    """Strip LaTeX delimiters and noise so TF-IDF tokens align across the
    corpus regardless of math formatting."""
    if not text:
        return ""
    # Drop block + inline math wrappers but keep their inner tokens.
    text = re.sub(r"\$\$(.+?)\$\$", r" \1 ", text, flags=re.DOTALL)
    text = re.sub(r"\$(.+?)\$", r" \1 ", text)
    # Strip common LaTeX commands.
    text = re.sub(r"\\[a-zA-Z]+\{([^{}]*)\}", r"\1", text)
    text = re.sub(r"\\[a-zA-Z]+", " ", text)
    return text.lower()


def top_k_similar(
    query_text: str, corpus: list[dict], k: int = 6
) -> list[dict]:
    """Return up to k corpus entries most similar to the query.

    `corpus` items must each have a `text` field; any other fields are
    preserved on the returned dicts plus an added `_score` (0..1)."""
    if not corpus:
        return []
    # Vectorize topic + text so a topic-query ("Projectile Motion") matches
    # both questions whose text mentions projectile AND questions tagged
    # with that topic but not lexically similar.
    docs = [
        _normalise(((c.get("topic") or "") + " . ") + c.get("text", ""))
        for c in corpus
    ]
    q = _normalise(query_text)
    if not q.strip():
        return []
    try:
        vec = TfidfVectorizer(
            stop_words="english",
            ngram_range=(1, 2),
            min_df=1,
            max_features=4096,
        )
        mat = vec.fit_transform(docs + [q])
        sims = cosine_similarity(mat[-1], mat[:-1]).ravel()
    except ValueError:
        # corpus too small / all-stopwords — fall back to lexical overlap.
        q_tokens = set(_TOK_RE.findall(q))
        sims = np.array(
            [
                len(q_tokens & set(_TOK_RE.findall(d))) / max(1, len(q_tokens))
                for d in docs
            ]
        )
    order = np.argsort(-sims)[:k]
    out = []
    for i in order:
        if sims[i] <= 0:
            continue
        item = {**corpus[int(i)], "_score": round(float(sims[i]), 3)}
        out.append(item)
    return out


def difficulty_distribution(items: Iterable[dict]) -> dict:
    """Return {easy:int, medium:int, hard:int} counts for retrieved items."""
    counts = Counter()
    for it in items:
        d = (it.get("difficulty") or "").lower()
        if d in ("easy", "medium", "hard"):
            counts[d] += 1
    return {"easy": counts["easy"], "medium": counts["medium"], "hard": counts["hard"]}
