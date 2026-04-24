"""Symbolic tokenization (ENCODER.md §11).

Converts a SymbolicWindow (window of objects) into a flat token id sequence
that the transformer consumes. Reverse direction exists for aux reconstruction
and sample inspection.

All buckets are deterministic, so a window → token sequence round-trip is
exact except for object truncation (§11.3).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable

# Token groups live at contiguous id ranges within a single shared vocab
# (§11.4 MVP decision). If we later switch to group-embeddings, only this file
# and model.py need to change.

# ---- special tokens ----
TOK_PAD = 0
TOK_CLS = 1
TOK_WINDOW = 2
TOK_WINDOW_END = 3
TOK_OBJ_BEGIN = 4
TOK_OBJ_END = 5
TOK_MASK = 6
N_SPECIAL = 7

# ---- offset ranges (see config.py for cardinalities) ----
# Layout:
#   special [0, 7)
#   kind    [7, 7+K_KIND)
#   x_rel   [..., ...)   relative x bucket in [0, 2c) where c = radius
#   y       [...]
#   rot     [...]
#   scale   [...]
#   color   [...]

from ..data.schema import SCHEMA_VERSION  # noqa: F401  (re-exported for consumers)

# Kind range matches ObjectKind values in core::Layout (INTERFACES.md §1).
KIND_OFFSET = N_SPECIAL
N_KIND = 10  # UNKNOWN..DECORATION + room for 1 future kind


def _next_offset(start: int, count: int) -> tuple[int, int]:
    return start, start + count


KIND_START, KIND_END = _next_offset(KIND_OFFSET, N_KIND)


@dataclass(frozen=True)
class TokenizerSpec:
    radius: int          # window radius in units (= c)
    y_buckets: int
    rot_buckets: int
    scale_buckets: int
    color_buckets: int

    @property
    def x_buckets(self) -> int:
        return self.radius * 2   # bucket per unit over [-c, +c)

    # ---- computed offset ranges ----
    @property
    def x_start(self) -> int:
        return KIND_END

    @property
    def x_end(self) -> int:
        return self.x_start + self.x_buckets

    @property
    def y_start(self) -> int:
        return self.x_end

    @property
    def y_end(self) -> int:
        return self.y_start + self.y_buckets

    @property
    def rot_start(self) -> int:
        return self.y_end

    @property
    def rot_end(self) -> int:
        return self.rot_start + self.rot_buckets

    @property
    def scale_start(self) -> int:
        return self.rot_end

    @property
    def scale_end(self) -> int:
        return self.scale_start + self.scale_buckets

    @property
    def color_start(self) -> int:
        return self.scale_end

    @property
    def color_end(self) -> int:
        return self.color_start + self.color_buckets

    @property
    def vocab_size(self) -> int:
        return self.color_end


# ---- bucketing helpers ----

_SCALE_BREAKPOINTS = (0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 4.0)   # 8 buckets


def bucket_x_rel(rel_x: float, radius: int) -> int:
    """Map rel_x ∈ [-radius, +radius] to [0, 2*radius).

    Values outside the window are clipped; pre-filter before calling.
    """
    b = int(math.floor(rel_x + radius))
    return max(0, min(radius * 2 - 1, b))


def bucket_y(y: float, y_buckets: int) -> int:
    """GD levels almost never exceed y=32 units. Linear bins over [0, 32]."""
    b = int(math.floor(y))
    return max(0, min(y_buckets - 1, b))


def bucket_rotation(rot_deg: float, rot_buckets: int) -> int:
    """Normalize rotation into [0, 360) then bucketize."""
    rot = rot_deg % 360.0
    step = 360.0 / rot_buckets
    return int(rot // step) % rot_buckets


def bucket_scale(scale: float) -> int:
    for i, bp in enumerate(_SCALE_BREAKPOINTS):
        if scale <= bp * 1.001:   # tolerance
            return i
    return len(_SCALE_BREAKPOINTS) - 1


def bucket_color(color_channel: int, color_buckets: int) -> int:
    if color_channel < 0:
        return color_buckets - 1  # "custom" sentinel
    return max(0, min(color_buckets - 2, color_channel))


# ---- encode / decode ----


@dataclass
class ObjectTokens:
    kind: int
    rel_x: float
    y: float
    rotation: float
    scale: float
    color_channel: int


def encode_window(objects: Iterable[ObjectTokens], spec: TokenizerSpec) -> list[int]:
    """Return token id sequence for a window. Layout:

        [WINDOW] [OBJ_BEGIN] kind x y rot scale color [OBJ_END] … [WINDOW_END] [CLS]
    """
    tokens: list[int] = [TOK_WINDOW]
    for obj in objects:
        tokens.append(TOK_OBJ_BEGIN)
        tokens.append(KIND_OFFSET + obj.kind)
        tokens.append(spec.x_start + bucket_x_rel(obj.rel_x, spec.radius))
        tokens.append(spec.y_start + bucket_y(obj.y, spec.y_buckets))
        tokens.append(spec.rot_start + bucket_rotation(obj.rotation, spec.rot_buckets))
        tokens.append(spec.scale_start + bucket_scale(obj.scale))
        tokens.append(spec.color_start + bucket_color(obj.color_channel, spec.color_buckets))
        tokens.append(TOK_OBJ_END)
    tokens.append(TOK_WINDOW_END)
    tokens.append(TOK_CLS)
    return tokens


def pad_to(tokens: list[int], length: int) -> list[int]:
    """Right-pad with TOK_PAD up to `length`. Caller ensures length ≥ len(tokens)."""
    pad_n = length - len(tokens)
    if pad_n < 0:
        raise ValueError(f"sequence too long: {len(tokens)} > {length}")
    return tokens + [TOK_PAD] * pad_n
