"""Deterministic, corpus-trained latent semantic analysis plus lexical features.

No remote provider or downloaded model is used. Expansion rules are deliberately
small and inspectable; they add search terms, never policy facts or decisions.
"""

import hashlib
import json
import re
from collections import Counter

import numpy as np

MODEL_ID = "northstar-lsa-hybrid-v1"
STOP_WORDS = set(
    """a an the i me my we our you your it its is are was were be been being
and or of to for in on at by with from this that these those do does did can could
would should will may please help want need how what when where which who why have
has had am about as if then than so get any some tell know policy policies request""".split()
)
# Inflections are explicit rather than aggressive stemming that conflates paid/unpaid.
ALIASES = {
    "refunds": "refund",
    "refunded": "refund",
    "reimbursement": "refund",
    "reimburse": "refund",
    "reimbursed": "refund",
    "moneyback": "refund",
    "cancelled": "cancel",
    "canceled": "cancel",
    "cancellation": "cancel",
    "cancelling": "cancel",
    "canceling": "cancel",
    "terminate": "cancel",
    "invoices": "invoice",
    "receipts": "invoice",
    "receipt": "invoice",
    "subscriptions": "subscription",
    "plans": "plan",
    "payments": "payment",
    "passwords": "password",
    "credentials": "password",
    "signin": "login",
    "outages": "outage",
    "downtime": "outage",
    "unavailable": "outage",
    "exports": "export",
    "exporting": "export",
    "deleted": "delete",
    "deletion": "delete",
    "erasure": "delete",
    "upgrades": "upgrade",
    "upgrading": "upgrade",
    "days": "day",
}
PHRASES = {
    "money back": "refund",
    "charged twice": "duplicate payment",
    "stop paying": "cancel subscription",
    "stop billing": "cancel subscription",
    "shut down my subscription": "cancel subscription",
    "locked out": "login password",
    "cannot sign in": "login password",
    "can't sign in": "login password",
    "move my data": "export data",
    "service is down": "outage",
}


def tokens(text: str) -> list[str]:
    return [
        ALIASES.get(word, word)
        for word in re.findall(r"[a-z0-9]+", text.casefold())
        if word not in STOP_WORDS
    ]


def reformulate(query: str) -> tuple[list[str], list[str]]:
    expanded = " ".join(query.casefold().split())
    additions = []
    for phrase, replacement in sorted(PHRASES.items(), key=lambda item: -len(item[0])):
        pattern = r"(?<!\w)" + re.escape(phrase) + r"(?!\w)"
        if re.search(pattern, expanded):
            expanded = re.sub(pattern, replacement, expanded)
            additions.append(replacement)
    return tokens(expanded), additions


def digest(value) -> str:
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        ).encode()
    ).hexdigest()


def normalize_rows(matrix):
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    return matrix / np.where(norms > 0, norms, 1)


def lexical_matrix(texts: list[str], vocabulary: list[str], idf):
    positions = {word: i for i, word in enumerate(vocabulary)}
    matrix = np.zeros((len(texts), len(vocabulary)))
    for row, text in enumerate(texts):
        for word, count in Counter(tokens(text)).items():
            if word in positions:
                matrix[row, positions[word]] = (1 + np.log(count)) * idf[positions[word]]
    return normalize_rows(matrix)


def train(texts: list[str], section_ids: list[str], dimensions: int, max_vocabulary: int) -> dict:
    frequencies = Counter(word for text in texts for word in set(tokens(text)))
    vocabulary = sorted(sorted(frequencies, key=lambda w: (-frequencies[w], w))[:max_vocabulary])
    if not vocabulary:
        # A valid empty projection still preserves every source section's identity.
        return {
            "section_ids": section_ids,
            "vocabulary": [],
            "idf": [],
            "components": [],
            "embeddings": [[] for _ in texts],
        }
    idf = np.array([np.log((1 + len(texts)) / (1 + frequencies[w])) + 1 for w in vocabulary])
    matrix = lexical_matrix(texts, vocabulary, idf)
    _, singular, components = np.linalg.svd(matrix, full_matrices=False)
    rank = min(dimensions, max(1, int(np.count_nonzero(singular > 1e-10))))
    components = components[:rank]
    # Fix SVD sign indeterminacy for reproducible stored representations.
    for component in components:
        if component[np.argmax(np.abs(component))] < 0:
            component *= -1
    embeddings = normalize_rows(matrix @ components.T)
    return {
        "section_ids": section_ids,
        "vocabulary": vocabulary,
        "idf": idf.tolist(),
        "components": components.tolist(),
        "embeddings": embeddings.tolist(),
    }


def validate(payload: dict, section_ids: list[str]):
    if payload["section_ids"] != section_ids:
        raise ValueError("Index section coverage mismatch")
    vocabulary = payload["vocabulary"]
    if len(set(vocabulary)) != len(vocabulary) or not all(isinstance(w, str) for w in vocabulary):
        raise ValueError("Invalid vocabulary")
    idf = np.array(payload["idf"], dtype=float)
    components = np.array(payload["components"], dtype=float)
    embeddings = np.array(payload["embeddings"], dtype=float)
    if not vocabulary:
        if (
            payload["idf"]
            or payload["components"]
            or payload["embeddings"] != [[] for _ in section_ids]
        ):
            raise ValueError("Invalid empty projection")
        return
    if (
        idf.shape != (len(vocabulary),)
        or components.ndim != 2
        or components.shape[1] != len(vocabulary)
        or components.shape[0] < 1
        or embeddings.shape != (len(section_ids), components.shape[0])
    ):
        raise ValueError("Invalid representation dimensions")
    if not all(np.isfinite(array).all() for array in (idf, components, embeddings)):
        raise ValueError("Nonfinite representation")


def rank(query: str, texts: list[str], payload: dict, candidate_limit: int):
    expanded, additions = reformulate(query)
    if not expanded or not payload["vocabulary"]:
        return [], additions
    vocabulary = payload["vocabulary"]
    lexical = lexical_matrix(texts, vocabulary, payload["idf"])
    query_vector = lexical_matrix([" ".join(expanded)], vocabulary, payload["idf"])[0]
    if not np.any(query_vector):
        return [], additions
    projected = normalize_rows((query_vector @ np.array(payload["components"]).T)[None, :])[0]
    semantic = np.clip(np.array(payload["embeddings"]) @ projected, 0, 1)
    keyword = lexical @ query_vector
    hybrid = 0.55 * keyword + 0.45 * semantic
    # Broad latent association alone is not evidence: require an actual matched concept.
    candidates = sorted(range(len(texts)), key=lambda i: (-round(float(hybrid[i]), 12), i))[
        :candidate_limit
    ]
    results = []
    query_terms = set(expanded)
    for i in candidates:
        terms = set(tokens(texts[i]))
        coverage = len(query_terms & terms) / len(query_terms)
        if not coverage or keyword[i] <= 0:
            continue
        # Rerank with explicit query coverage to demote plausible but off-topic neighbors.
        score = 0.8 * float(hybrid[i]) + 0.2 * coverage
        results.append(
            {
                "position": i,
                "score": round(score, 6),
                "semantic_score": round(float(semantic[i]), 6),
                "keyword_score": round(float(keyword[i]), 6),
                "coverage": round(coverage, 6),
            }
        )
    return sorted(results, key=lambda r: (-r["score"], r["position"])), additions
