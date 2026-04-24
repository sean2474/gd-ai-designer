"""Quality / diagnostic metrics for the encoder (ENCODER.md §7).

All functions are numpy-only so they can be called from the boundary pass
without any torch dependency.
"""
from __future__ import annotations

import numpy as np
from sklearn.metrics import silhouette_score


def level_silhouette(
    embeddings: np.ndarray,
    assignments: np.ndarray,
) -> float:
    """Mean silhouette over one level. Returns NaN if fewer than 2 clusters."""
    if len(np.unique(assignments)) < 2:
        return float("nan")
    if len(embeddings) > 5000:
        # Sub-sample for speed; silhouette is O(n^2).
        rng = np.random.default_rng(0)
        idx = rng.choice(len(embeddings), 5000, replace=False)
        embeddings = embeddings[idx]
        assignments = assignments[idx]
    return float(silhouette_score(embeddings, assignments, metric="cosine"))


def collapse_ratio(embeddings: np.ndarray, eps: float = 1e-6) -> float:
    """Fraction of the embedding variance explained by the dominant singular
    value. Close to 1.0 = collapsed to a line / point. Close to 1/d = healthy."""
    centered = embeddings - embeddings.mean(axis=0, keepdims=True)
    if np.linalg.norm(centered) < eps:
        return 1.0
    _, s, _ = np.linalg.svd(centered, full_matrices=False)
    total = float(np.sum(s ** 2))
    if total < eps:
        return 1.0
    return float(s[0] ** 2 / total)


def interval_iou(
    intervals_a: list[tuple[float, float]],
    intervals_b: list[tuple[float, float]],
) -> float:
    """Union/intersection length ratio for two sets of closed intervals on ℝ.

    Used as a secondary convergence signal alongside boundary_iou
    (ENCODER.md §9 "IoU_interval").
    """
    def total_length(iv: list[tuple[float, float]]) -> float:
        return sum(max(0.0, hi - lo) for lo, hi in iv)

    if not intervals_a and not intervals_b:
        return 1.0

    # Build event list to compute union/intersection without sorting by hand.
    def clip(intervals: list[tuple[float, float]]) -> list[tuple[float, float]]:
        return [(lo, hi) for lo, hi in intervals if hi > lo]

    a = clip(intervals_a)
    b = clip(intervals_b)

    inter_len = 0.0
    for la, ha in a:
        for lb, hb in b:
            lo = max(la, lb)
            hi = min(ha, hb)
            if hi > lo:
                inter_len += hi - lo

    union_len = total_length(a) + total_length(b) - inter_len
    return inter_len / union_len if union_len > 0 else 0.0
