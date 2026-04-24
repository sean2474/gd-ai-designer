"""Prototype extraction + soft membership + entropy (ENCODER.md §2, §4).

Pure numpy for portability; no torch dependency. Called per level during
the boundary-extraction pass of the bootstrap loop.
"""
from __future__ import annotations

import numpy as np
from sklearn.cluster import KMeans


def extract_prototypes(
    embeddings: np.ndarray,
    k: int,
    *,
    random_state: int = 0,
) -> np.ndarray:
    """Run KMeans on a level's window embeddings and return k centroids.

    Parameters
    ----------
    embeddings : (N, d) array of per-window embeddings for one level.
    k : number of prototypes (typically 4 for MVP).

    Returns
    -------
    prototypes : (k, d) array of cluster centroids.
    """
    if len(embeddings) < k:
        # Degenerate: return the embeddings themselves (upscaled if needed).
        padded = np.concatenate([embeddings] * ((k // len(embeddings)) + 1), axis=0)[:k]
        return padded
    km = KMeans(n_clusters=k, n_init=10, random_state=random_state)
    km.fit(embeddings)
    return km.cluster_centers_.astype(np.float32)


def _cosine_distance(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Cosine distance between rows of a (N,d) and rows of b (k,d). Returns (N,k)."""
    a = a / (np.linalg.norm(a, axis=-1, keepdims=True) + 1e-8)
    b = b / (np.linalg.norm(b, axis=-1, keepdims=True) + 1e-8)
    return 1.0 - a @ b.T


def soft_membership(
    embeddings: np.ndarray,
    prototypes: np.ndarray,
    temperature: float,
) -> np.ndarray:
    """w_i(n) = softmax(-d(v_n, p_i) / T). Returns (N, k)."""
    dists = _cosine_distance(embeddings, prototypes)   # (N, k)
    scaled = -dists / max(temperature, 1e-8)
    # Numerically stable softmax
    scaled -= scaled.max(axis=-1, keepdims=True)
    exp = np.exp(scaled)
    return exp / (exp.sum(axis=-1, keepdims=True) + 1e-8)


def normalized_entropy(memberships: np.ndarray) -> np.ndarray:
    """H(n) = -Σ w_i log w_i,  normalized by log(k) into [0, 1]. Returns (N,)."""
    k = memberships.shape[-1]
    safe = np.clip(memberships, 1e-8, 1.0)
    h = -np.sum(safe * np.log(safe), axis=-1)
    return h / np.log(k)


def left_right_score(
    embeddings: np.ndarray,
    w: int,
) -> np.ndarray:
    """s_LR(n) = cosine_distance( mean(v_{n-w..n-1}), mean(v_{n+1..n+w}) ).

    Edges have no valid left/right window → score is 0.
    Returns (N,).
    """
    n = len(embeddings)
    out = np.zeros(n, dtype=np.float32)
    if n < 2 * w + 1:
        return out
    for i in range(w, n - w):
        left = embeddings[i - w:i].mean(axis=0, keepdims=True)
        right = embeddings[i + 1:i + 1 + w].mean(axis=0, keepdims=True)
        out[i] = _cosine_distance(left, right)[0, 0]
    return out


def minmax_normalize(x: np.ndarray, *, p_low: float = 0.05, p_high: float = 0.95) -> np.ndarray:
    """Clip to [p_low, p_high] percentiles then rescale into [0, 1]."""
    lo, hi = np.quantile(x, [p_low, p_high])
    if hi <= lo:
        return np.zeros_like(x)
    return np.clip((x - lo) / (hi - lo), 0.0, 1.0)


def ensemble_score(h: np.ndarray, s_lr: np.ndarray, gamma: float) -> np.ndarray:
    """s_final = γ·H + (1-γ)·minmax(s_LR)."""
    return gamma * h + (1.0 - gamma) * minmax_normalize(s_lr)
