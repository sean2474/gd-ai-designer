"""Stage 2 converter: RawLevel (raw k:v dicts) → ParsedLevel (typed fields).

Also provides the reverse encoder (`encode_level_string`) used by export tools
that need to round-trip a modified level back into GD's compressed format.
"""
from __future__ import annotations

import base64
import gzip

from .gd_keys import (
    KEY_COLOR_CHANNEL,
    KEY_COLOR_CHANNEL_2,
    KEY_EDITOR_LAYER,
    KEY_EDITOR_LAYER_2,
    KEY_FLIP_X,
    KEY_FLIP_Y,
    KEY_GROUP_IDS,
    KEY_OBJECT_ID,
    KEY_ROTATION,
    KEY_SCALE,
    KEY_X,
    KEY_Y,
    KEY_Z_LAYER,
    KEY_Z_ORDER,
    KNOWN_KEYS,
)
from .schema import ParsedLevel, ParsedObject, RawLevel


# ---------- scalar coercions ----------


def _as_int(v: str, default: int = 0) -> int:
    if not v:
        return default
    try:
        return int(v)
    except ValueError:
        try:
            return int(float(v))
        except ValueError:
            return default


def _as_float(v: str, default: float = 0.0) -> float:
    if not v:
        return default
    try:
        return float(v)
    except ValueError:
        return default


def _as_bool(v: str) -> bool:
    return v not in ("", "0")


def _parse_groups(v: str) -> list[int]:
    """Group IDs come as dot-separated ints: "1.2.3"."""
    if not v:
        return []
    out: list[int] = []
    for g in v.split("."):
        if g.isdigit():
            out.append(int(g))
    return out


def _encode_groups(ids: list[int]) -> str:
    return ".".join(str(i) for i in ids)


# ---------- convert ----------


def convert_object(kv: dict[str, str]) -> ParsedObject:
    extra = {k: val for k, val in kv.items() if k not in KNOWN_KEYS}
    return ParsedObject(
        object_id=_as_int(kv.get(KEY_OBJECT_ID, "")),
        x=_as_float(kv.get(KEY_X, "")),
        y=_as_float(kv.get(KEY_Y, "")),
        flip_x=_as_bool(kv.get(KEY_FLIP_X, "")),
        flip_y=_as_bool(kv.get(KEY_FLIP_Y, "")),
        rotation=_as_float(kv.get(KEY_ROTATION, "")),
        editor_layer=_as_int(kv.get(KEY_EDITOR_LAYER, "")),
        editor_layer_2=_as_int(kv.get(KEY_EDITOR_LAYER_2, "")),
        color_channel=_as_int(kv.get(KEY_COLOR_CHANNEL, "")),
        color_channel_2=_as_int(kv.get(KEY_COLOR_CHANNEL_2, "")),
        z_layer=_as_int(kv.get(KEY_Z_LAYER, "")),
        z_order=_as_int(kv.get(KEY_Z_ORDER, "")),
        scale=_as_float(kv.get(KEY_SCALE, "1"), default=1.0),
        group_ids=_parse_groups(kv.get(KEY_GROUP_IDS, "")),
        extra=extra,
    )


def convert_level(raw: RawLevel) -> ParsedLevel:
    """Decode the raw blob and produce a fully-typed ParsedLevel."""
    from .fetch import decode_level_string  # local import to avoid cycle

    header, raw_objects = decode_level_string(raw.level_string_raw)
    parsed = [convert_object(o) for o in raw_objects]
    if parsed:
        xs = [o.x for o in parsed]
        ys = [o.y for o in parsed]
        bbox = (min(xs), min(ys), max(xs), max(ys))
    else:
        bbox = (0.0, 0.0, 0.0, 0.0)
    return ParsedLevel(
        level_id=raw.level_id,
        name=raw.name,
        creator=raw.creator,
        rating=raw.rating,
        length=raw.length,
        game_version=raw.game_version,
        object_count=len(parsed),
        header=header,
        objects=parsed,
        bbox_min_x=bbox[0],
        bbox_min_y=bbox[1],
        bbox_max_x=bbox[2],
        bbox_max_y=bbox[3],
    )


# ---------- reverse: ParsedObject/raw-dict → GD level string ----------


def _fmt_float(v: float) -> str:
    """GD keeps trailing-zero ints (e.g. '45' not '45.0'). Match that."""
    if v == int(v):
        return str(int(v))
    return format(v, "g")


def _parsed_object_to_kv(obj: ParsedObject) -> dict[str, str]:
    kv: dict[str, str] = {
        KEY_OBJECT_ID: str(obj.object_id),
        KEY_X: _fmt_float(obj.x),
        KEY_Y: _fmt_float(obj.y),
    }
    if obj.flip_x:
        kv[KEY_FLIP_X] = "1"
    if obj.flip_y:
        kv[KEY_FLIP_Y] = "1"
    if obj.rotation:
        kv[KEY_ROTATION] = _fmt_float(obj.rotation)
    if obj.editor_layer:
        kv[KEY_EDITOR_LAYER] = str(obj.editor_layer)
    if obj.editor_layer_2:
        kv[KEY_EDITOR_LAYER_2] = str(obj.editor_layer_2)
    if obj.color_channel:
        kv[KEY_COLOR_CHANNEL] = str(obj.color_channel)
    if obj.color_channel_2:
        kv[KEY_COLOR_CHANNEL_2] = str(obj.color_channel_2)
    if obj.z_layer:
        kv[KEY_Z_LAYER] = str(obj.z_layer)
    if obj.z_order:
        kv[KEY_Z_ORDER] = str(obj.z_order)
    if obj.scale != 1.0:
        kv[KEY_SCALE] = _fmt_float(obj.scale)
    if obj.group_ids:
        kv[KEY_GROUP_IDS] = _encode_groups(obj.group_ids)
    kv.update(obj.extra)
    return kv


def _kv_to_comma(kv: dict[str, str]) -> str:
    parts: list[str] = []
    for k, v in kv.items():
        parts.append(k)
        parts.append(v)
    return ",".join(parts)


def encode_level_string(
    header: dict[str, str], objects: list[dict[str, str]]
) -> str:
    """Inverse of fetch.decode_level_string. Output matches GD's exact byte
    format: base64(url-safe) + gzip(compresslevel=6, mtime=0, XFL=0, OS=03).

    GD's parser is byte-strict; level 9 (Python's default) produces a different
    deflate stream and GD silently loads an empty level.
    """
    header_part = _kv_to_comma(header)
    object_parts = [_kv_to_comma(o) for o in objects]
    joined = header_part + ";" + ";".join(object_parts) + ";"
    compressed = bytearray(
        gzip.compress(joined.encode("utf-8"), compresslevel=6, mtime=0)
    )
    compressed[8] = 0
    compressed[9] = 0x03
    return base64.urlsafe_b64encode(bytes(compressed)).decode("ascii")
