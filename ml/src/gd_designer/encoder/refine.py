"""Bootstrap refinement loop (ENCODER.md §9, §15).

This module is the glue between trainer, tokenizer, prototypes, and boundary.
The MVP implementation here is a *structural* scaffold: it orchestrates the
iteration and convergence check, but the actual training call is delegated
so it can be tested without spinning up torch.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Protocol

import numpy as np

from .boundary import (
    BoundaryResult,
    boundary_iou,
    buffer_transition,
    extract_boundaries,
    pure_mask,
)
from .config import EncoderConfig
from .metrics import interval_iou
from .prototypes import (
    ensemble_score,
    extract_prototypes,
    left_right_score,
    normalized_entropy,
    soft_membership,
)


@dataclass
class LevelResult:
    level_id: int
    xs: np.ndarray                         # window centers
    embeddings: np.ndarray                 # (N, d)
    boundary: BoundaryResult
    silhouette: float | None = None


@dataclass
class IterationSummary:
    iteration: int
    n_levels: int
    iou_boundary_mean: float | None        # vs previous iteration
    iou_interval_mean: float | None
    converged: bool
    per_level: list[LevelResult] = field(default_factory=list)


class EncoderInterface(Protocol):
    def embed_windows(self, level_id: int) -> tuple[np.ndarray, np.ndarray]:
        """Return (xs, embeddings) for the level's sliding windows."""

    def train(self, include_mask: dict[int, np.ndarray]) -> None:
        """Train a fresh encoder on windows where `include_mask[level_id][i]` is True."""


def run_iteration(
    encoder: EncoderInterface,
    level_ids: list[int],
    cfg: EncoderConfig,
) -> list[LevelResult]:
    """For each level: embed, cluster, score, extract boundaries."""
    results: list[LevelResult] = []
    for lid in level_ids:
        xs, emb = encoder.embed_windows(lid)
        if len(emb) == 0:
            continue

        protos = extract_prototypes(emb, k=cfg.k_prototypes)
        w = soft_membership(emb, protos, cfg.softmax_T)
        h = normalized_entropy(w)
        s_lr = left_right_score(emb, w=cfg.lr_window_size)
        s_final = ensemble_score(h, s_lr, cfg.ensemble_gamma)

        boundary = extract_boundaries(
            xs,
            s_final,
            threshold=cfg.entropy_threshold,
            merge_gap_units=cfg.merge_gap,
            local_maxima_delta_units=cfg.local_maxima_delta,
        )
        results.append(LevelResult(level_id=lid, xs=xs, embeddings=emb, boundary=boundary))
    return results


def compute_pure_masks(
    results: list[LevelResult],
    cfg: EncoderConfig,
) -> dict[int, np.ndarray]:
    """Per level, return a bool array over windows marking which to keep."""
    out: dict[int, np.ndarray] = {}
    for r in results:
        buffered = buffer_transition(r.boundary.transition_intervals, cfg.transition_buffer)
        out[r.level_id] = pure_mask(r.xs, buffered)
    return out


def _summarize_iou(
    curr: list[LevelResult],
    prev: list[LevelResult],
    tolerance: float,
) -> tuple[float, float]:
    """Return (mean boundary IoU, mean interval IoU) across paired levels."""
    prev_map = {r.level_id: r for r in prev}
    b_ious: list[float] = []
    i_ious: list[float] = []
    for r in curr:
        p = prev_map.get(r.level_id)
        if p is None:
            continue
        b_ious.append(
            boundary_iou(r.boundary.boundary_xs, p.boundary.boundary_xs, tolerance)
        )
        i_ious.append(
            interval_iou(r.boundary.transition_intervals, p.boundary.transition_intervals)
        )
    if not b_ious:
        return (0.0, 0.0)
    return (float(np.mean(b_ious)), float(np.mean(i_ious)))


def bootstrap(
    encoder: EncoderInterface,
    level_ids: list[int],
    cfg: EncoderConfig,
    on_iteration: Callable[[IterationSummary], None] | None = None,
) -> list[IterationSummary]:
    """Full iterative loop. Returns per-iteration summaries.

    Convergence: IoU_boundary mean ≥ cfg.iou_target for 2 consecutive iterations.
    """
    history: list[IterationSummary] = []
    prev_results: list[LevelResult] = []
    consec_converged = 0

    for t in range(1, cfg.max_iters + 1):
        curr_results = run_iteration(encoder, level_ids, cfg)

        if t == 1:
            b_iou = i_iou = None
            converged = False
        else:
            b_iou, i_iou = _summarize_iou(curr_results, prev_results, cfg.iou_tolerance)
            converged = (b_iou is not None) and (b_iou >= cfg.iou_target)
            consec_converged = consec_converged + 1 if converged else 0

        summary = IterationSummary(
            iteration=t,
            n_levels=len(curr_results),
            iou_boundary_mean=b_iou,
            iou_interval_mean=i_iou,
            converged=(consec_converged >= 2),
            per_level=curr_results,
        )
        history.append(summary)

        if on_iteration is not None:
            on_iteration(summary)

        if summary.converged:
            break

        # Retrain on Pure set derived from this iteration's boundaries.
        include_mask = compute_pure_masks(curr_results, cfg)
        encoder.train(include_mask)
        prev_results = curr_results

    return history
