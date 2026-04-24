"""Level → list of SymbolicWindow (ENCODER.md §1).

A level is represented by its parsed object list. We slide a window of width
2c along the x-axis with stride s, collect objects whose x falls inside each
window, and emit one record per window position.

This file is pure (no torch), so it can run inside Stage-2 data prep and tests.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Iterator

from .tokenizer import ObjectTokens


@dataclass
class ParsedObject:
    """One object parsed from a level string. Subset of LayoutObject but with
    decoration kind allowed (encoder may condition on decorations too, unlike
    the runtime LayoutReader in mod/gd/)."""
    kind: int
    x: float            # absolute x in units
    y: float            # absolute y in units
    rotation: float
    scale: float = 1.0
    color_channel: int = 0
    # Optional: carry game_object_id for debugging
    game_object_id: int = 0


@dataclass
class Window:
    level_id: int
    center_x: float
    radius: int
    objects: list[ObjectTokens]


def windows_for_level(
    level_id: int,
    objects: list[ParsedObject],
    *,
    radius: int,
    stride: int,
    include_decoration: bool = True,
    min_x: float | None = None,
    max_x: float | None = None,
    n_obj_max: int = 128,
) -> Iterator[Window]:
    """Yield Window records as the window slides across the level.

    - `include_decoration=True` is the encoder default (we train on both layout
      and decoration so the embedding reflects stylistic choice). The Designer
      path filters to gameplay-only separately.
    - Windows that truncate due to n_obj_max still emit; a counter is tracked
      externally by the caller via _stats if desired.
    """
    if not objects:
        return
    if min_x is None:
        min_x = min(o.x for o in objects)
    if max_x is None:
        max_x = max(o.x for o in objects)

    # Walk centers from min_x + radius to max_x - radius so the full window
    # overlaps the level (avoid partial windows at edges — MVP decision).
    first = min_x + radius
    last = max_x - radius
    if last < first:
        return

    # Snap to stride grid
    first = (int(first) // stride) * stride

    # Pre-sort once for efficient range scans
    sorted_objs = sorted(objects, key=lambda o: (o.x, o.y, o.game_object_id))

    center = float(first)
    i_left = 0
    while center <= last:
        lo, hi = center - radius, center + radius
        # Advance i_left past objects that dropped off the left edge
        while i_left < len(sorted_objs) and sorted_objs[i_left].x < lo:
            i_left += 1
        # Collect up to n_obj_max from i_left forward while x < hi
        winobjs: list[ObjectTokens] = []
        j = i_left
        while j < len(sorted_objs) and sorted_objs[j].x <= hi:
            o = sorted_objs[j]
            j += 1
            if not include_decoration and _is_decoration_kind(o.kind):
                continue
            winobjs.append(ObjectTokens(
                kind=o.kind,
                rel_x=o.x - center,
                y=o.y,
                rotation=o.rotation,
                scale=o.scale,
                color_channel=o.color_channel,
            ))
            if len(winobjs) >= n_obj_max:
                break

        if winobjs:
            yield Window(
                level_id=level_id,
                center_x=center,
                radius=radius,
                objects=winobjs,
            )

        center += stride


def _is_decoration_kind(kind: int) -> bool:
    # Mirrors core::ObjectKind::DECORATION = 8 from INTERFACES.md §1.1
    return kind == 8


def iter_levels_to_windows(
    levels: Iterable[tuple[int, list[ParsedObject]]],
    *,
    radius: int,
    stride: int,
    min_level_width: int,
    include_decoration: bool,
    n_obj_max: int,
) -> Iterator[Window]:
    """Thin convenience wrapper over many levels."""
    for level_id, objs in levels:
        if not objs:
            continue
        xs = [o.x for o in objs]
        if max(xs) - min(xs) < min_level_width:
            continue
        yield from windows_for_level(
            level_id,
            objs,
            radius=radius,
            stride=stride,
            include_decoration=include_decoration,
            n_obj_max=n_obj_max,
        )
