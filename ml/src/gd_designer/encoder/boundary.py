"""Transition / boundary extraction from per-window scores (ENCODER.md §5, §6, §8).

Two outputs:
    B : list of "sharpened" boundary point coordinates (local maxima of s_final)
    Transition : list of (start_x, end_x) intervals where s_final > threshold

The caller owns x-axis indexing: `xs[i]` is the level-absolute x coordinate
of the i-th window center, and `scores[i]` is its s_final value.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class BoundaryResult:
    boundary_xs: list[float]                 # B
    transition_intervals: list[tuple[float, float]]  # Transition


def morphological_close(
    mask: np.ndarray,
    xs: np.ndarray,
    merge_gap_units: float,
) -> list[tuple[int, int]]:
    """Merge runs of True in `mask` if the gap between them (in xs units) ≤ merge_gap.

    Returns list of (i_start, i_end) index ranges (half-open).
    """
    intervals: list[tuple[int, int]] = []
    n = len(mask)
    i = 0
    while i < n:
        if not mask[i]:
            i += 1
            continue
        j = i
        while j < n and mask[j]:
            j += 1
        intervals.append((i, j))
        i = j

    # Merge neighbours if gap small in xs
    merged: list[tuple[int, int]] = []
    for interval in intervals:
        if not merged:
            merged.append(interval)
            continue
        prev_end_i = merged[-1][1] - 1
        curr_start_i = interval[0]
        gap_x = xs[curr_start_i] - xs[prev_end_i] if prev_end_i < len(xs) else float("inf")
        if gap_x <= merge_gap_units:
            merged[-1] = (merged[-1][0], interval[1])
        else:
            merged.append(interval)
    return merged


def local_maxima(
    xs: np.ndarray,
    scores: np.ndarray,
    *,
    threshold: float,
    min_separation_units: float,
) -> list[int]:
    """Return indices of local maxima above `threshold`, at least
    `min_separation_units` apart along xs."""
    n = len(scores)
    if n < 3:
        return []
    cand: list[tuple[float, int]] = []
    for i in range(1, n - 1):
        if scores[i] < threshold:
            continue
        if scores[i] > scores[i - 1] and scores[i] >= scores[i + 1]:
            cand.append((scores[i], i))
    # Greedy non-max suppression in x-space, highest score first.
    cand.sort(reverse=True)
    chosen: list[int] = []
    for _, i in cand:
        if all(abs(xs[i] - xs[j]) >= min_separation_units for j in chosen):
            chosen.append(i)
    chosen.sort()
    return chosen


def extract_boundaries(
    xs: np.ndarray,
    scores: np.ndarray,
    *,
    threshold: float,
    merge_gap_units: float,
    local_maxima_delta_units: float,
) -> BoundaryResult:
    """One call that does the §5-§6 pipeline.

    xs      : (N,) float — absolute x of each window center
    scores  : (N,) float — s_final(n)  in [0, 1]
    """
    if len(xs) == 0:
        return BoundaryResult([], [])

    mask = scores > threshold
    intervals_idx = morphological_close(mask, xs, merge_gap_units)
    transitions: list[tuple[float, float]] = [
        (float(xs[i0]), float(xs[i1 - 1])) for (i0, i1) in intervals_idx if i1 > i0
    ]

    peak_idx = local_maxima(
        xs,
        scores,
        threshold=threshold,
        min_separation_units=local_maxima_delta_units,
    )
    boundaries: list[float] = [float(xs[i]) for i in peak_idx]

    return BoundaryResult(boundaries, transitions)


def buffer_transition(
    intervals: list[tuple[float, float]],
    buffer_units: float,
) -> list[tuple[float, float]]:
    """Expand each interval by ±buffer. Callers use this result to mark
    windows to exclude from v_{t+1} training (Pure set, §8)."""
    return [(lo - buffer_units, hi + buffer_units) for (lo, hi) in intervals]


def pure_mask(
    xs: np.ndarray,
    buffered: list[tuple[float, float]],
) -> np.ndarray:
    """True where `xs` is outside every buffered interval."""
    keep = np.ones(len(xs), dtype=bool)
    for lo, hi in buffered:
        keep &= ~((xs >= lo) & (xs <= hi))
    return keep


def boundary_iou(
    b_t: list[float],
    b_prev: list[float],
    tolerance_units: float,
) -> float:
    """Tolerance-aware boundary set IoU (ENCODER.md §9).

    match(n, B) ⇔ ∃ m ∈ B with |n - m| ≤ tolerance.
    IoU = TP / (TP + FP + FN) where
        TP = |{ n ∈ B_t : match(n, B_prev) }|
        FP = |B_t| - TP
        FN = |{ m ∈ B_prev : ¬match(m, B_t) }|
    """
    if not b_t and not b_prev:
        return 1.0
    if not b_t or not b_prev:
        return 0.0

    tp = sum(
        1
        for n in b_t
        if any(abs(n - m) <= tolerance_units for m in b_prev)
    )
    fp = len(b_t) - tp
    fn = sum(
        1
        for m in b_prev
        if not any(abs(m - n) <= tolerance_units for n in b_t)
    )
    denom = tp + fp + fn
    return tp / denom if denom else 0.0
