"""Standalone test: download Future Funk via GDHistory, drop everything that
isn't a "user-interaction" gameplay object, write a .gmd that still has the
song / metadata of the original.

Classification source: data/object_ids.json (dumped by the Geode mod's
"Dump IDs" button — runs GD's own GameObject classifier per-id).

Independent of the running crawler — issues its own HTTP calls.
"""
from __future__ import annotations

import asyncio
import base64
import gzip
import json
import logging
import re
import sys
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape

import httpx


# ---- config ----
LEVEL_ID = 44062068  # Future Funk by JonathanGD
GDHISTORY_BASE = "https://history.geometrydash.eu"
USER_AGENT = "GDDesignAI-Crawler/0.1.0 (+https://github.com/sean2474/gd-ai-designer)"
DATA_DIR = Path("/Users/sean2474/Desktop/project/gd-design-ai/data")
OBJECT_IDS_JSON = DATA_DIR / "object_ids.json"
OUT_PATH = DATA_DIR / "test_future_funk_layout.gmd"

# ObjectKind values that count as "user-interactive gameplay" — kept.
# Mirrors mod/src/core/Layout.hpp ObjectKind enum.
GAMEPLAY_KINDS: frozenset[int] = frozenset(
    {
        1,   # BLOCK_SOLID
        2,   # BLOCK_HALF
        3,   # SPIKE
        4,   # ORB
        5,   # PAD
        6,   # PORTAL
        7,   # SLOPE
        9,   # TRIGGER_GAMEPLAY  (move/spawn/toggle/...)
        11,  # COLLECTIBLE       (coins/keys)
        12,  # SPECIAL           (boost arrows / teleport orbs / ...)
    }
)

# Dropped: 0 (UNKNOWN — uncategorized after all fallbacks),
# 8 (DECORATION), 10 (TRIGGER_VISUAL — color/bg/pulse).

_GMD_K_RE = re.compile(r"<k>(k\d+)</k>\s*<([isr])>([^<]*)</[isr]>")
_BOOL_K_RE = re.compile(r"<k>(k\d+)</k>\s*<t/>")

log = logging.getLogger(__name__)


def _decompress(encoded: str) -> str:
    padded = encoded + "=" * (-len(encoded) % 4)
    return gzip.decompress(base64.urlsafe_b64decode(padded)).decode("utf-8", errors="replace")


def _recompress(plaintext: str) -> str:
    """Match GD's exact byte format (compresslevel=6, mtime=0, XFL=0, OS=03)."""
    compressed = bytearray(gzip.compress(plaintext.encode("utf-8"), compresslevel=6, mtime=0))
    compressed[8] = 0
    compressed[9] = 0x03
    return base64.urlsafe_b64encode(bytes(compressed)).decode("ascii")


def _id_of_segment(seg: str) -> int:
    parts = seg.split(",")
    for i in range(0, len(parts) - 1, 2):
        if parts[i] == "1":
            try:
                return int(parts[i + 1])
            except ValueError:
                return 0
    return 0


# Keys that depend on visual triggers we dropped:
#   35 = per-object alpha (object initial alpha; meant to be ramped up by
#        an Alpha/Pulse trigger that we removed)
#   21 = main color channel (a custom channel may be initialised invisible
#        in kS38 and brought up by a Color trigger we removed)
#   22 = secondary color channel
# Forcing these out of the segment makes the object render with engine
# defaults instead of waiting for a trigger that will never fire.
_DROP_KEYS_FOR_VISIBILITY = frozenset({"35", "21", "22"})


def _force_visible(seg: str) -> str:
    parts = seg.split(",")
    out: list[str] = []
    i = 0
    while i + 1 < len(parts):
        if parts[i] in _DROP_KEYS_FOR_VISIBILITY:
            i += 2
            continue
        out.append(parts[i])
        out.append(parts[i + 1])
        i += 2
    # If there's a trailing key with no value (shouldn't normally happen), keep it.
    if i < len(parts):
        out.append(parts[i])
    return ",".join(out)


# Per-segment helpers for orphan-trigger filtering.

def _groups_of_segment(seg: str) -> list[int]:
    """Return the group IDs an object belongs to (key 57)."""
    parts = seg.split(",")
    for i in range(0, len(parts) - 1, 2):
        if parts[i] == "57":
            return [int(g) for g in parts[i + 1].split(".") if g.lstrip("-").isdigit()]
    return []


# Keys triggers use to address a target group of objects. Most movement /
# toggle / spawn / rotate / animate / scale / follow triggers use 51. Some
# triggers (collision, count) use other keys — they're rarely orphan-prone.
_TRIGGER_TARGET_KEYS = ("51",)


def _orphan_target(seg: str, groups: set[int]) -> bool:
    """True if the segment is a trigger whose target group ID isn't owned by
    any kept object."""
    parts = seg.split(",")
    for i in range(0, len(parts) - 1, 2):
        if parts[i] in _TRIGGER_TARGET_KEYS:
            try:
                t = int(parts[i + 1])
            except ValueError:
                continue
            if t > 0 and t not in groups:
                return True
    return False


def _parse_gmd(gmd_text: str) -> tuple[dict[str, tuple[str, str]], set[str]]:
    """Returns (typed_kvs, bool_keys).
    typed_kvs: {key: (typetag, value)} for <s>/<i>/<r> entries
    bool_keys: {key, ...} for <t/> entries
    """
    typed: dict[str, tuple[str, str]] = {
        k: (tag, v) for k, tag, v in _GMD_K_RE.findall(gmd_text)
    }
    bools: set[str] = set(_BOOL_K_RE.findall(gmd_text))
    return typed, bools


def _make_gmd_preserving(
    typed: dict[str, tuple[str, str]], bools: set[str]
) -> str:
    """Reassemble a GMD plist preserving every k* field (so the song / settings
    survive the round-trip). Caller is expected to have already mutated `typed`
    (e.g. replacing k4 with the modified level data)."""
    parts: list[str] = ['<?xml version="1.0"?>',
                        '<plist version="1.0" gjver="2.0">',
                        '<dict>']
    for k, (tag, v) in typed.items():
        parts.append(f"\t<k>{k}</k><{tag}>{xml_escape(v)}</{tag}>")
    for k in bools:
        parts.append(f"\t<k>{k}</k><t/>")
    parts.append("</dict>")
    parts.append("</plist>")
    return "\n".join(parts) + "\n"


def _load_kind_map() -> dict[int, int]:
    """Load id → kind from the C++-dumped JSON. Returns {} if not present."""
    if not OBJECT_IDS_JSON.exists():
        return {}
    data = json.loads(OBJECT_IDS_JSON.read_text(encoding="utf-8"))
    out: dict[int, int] = {}
    for k, v in data.get("ids", {}).items():
        try:
            out[int(k)] = int(v["kind"]) if isinstance(v, dict) else int(v)
        except (KeyError, TypeError, ValueError):
            continue
    return out


async def _run() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    kind_map = _load_kind_map()
    if not kind_map:
        log.error(
            "%s missing — launch GD, open the editor, and click 'Dump IDs' first",
            OBJECT_IDS_JSON,
        )
        return 1
    log.info("loaded %d id→kind entries", len(kind_map))

    async with httpx.AsyncClient(
        headers={"User-Agent": USER_AGENT}, timeout=60.0, follow_redirects=True
    ) as http:
        log.info("fetching meta for level %d", LEVEL_ID)
        meta = (await http.get(f"{GDHISTORY_BASE}/api/v1/level/{LEVEL_ID}/")).json()
        records = meta.get("records") or []
        avail = [r for r in records if r.get("level_string_available")]
        if not avail:
            log.error("no level_string_available record for %d", LEVEL_ID)
            return 1
        avail.sort(key=lambda r: r.get("cache_real_date", "") or "", reverse=True)
        rec_id = int(avail[0]["id"])
        log.info("using record %d (%s)", rec_id, avail[0].get("cache_real_date"))

        log.info("downloading gmd...")
        gmd_text = (
            await http.get(f"{GDHISTORY_BASE}/level/{LEVEL_ID}/{rec_id}/download/")
        ).text

    typed, bools = _parse_gmd(gmd_text)
    if "k4" not in typed:
        log.error("k4 missing in gmd")
        return 1
    name = typed.get("k2", ("s", "Future Funk"))[1]

    plaintext = _decompress(typed["k4"][1])
    sections = plaintext.split(";")
    header_str = sections[0]
    object_segs = [s for s in sections[1:] if s]

    # First pass: kind-based filter.
    kept_typed: list[tuple[str, int, int]] = []  # (segment, kind, object_id)
    drop_count: dict[int, int] = {}
    keep_count: dict[int, int] = {}
    unknown_id_count = 0
    for seg in object_segs:
        oid = _id_of_segment(seg)
        kind = kind_map.get(oid, -1)
        if kind == -1:
            unknown_id_count += 1
        if kind in GAMEPLAY_KINDS:
            kept_typed.append((_force_visible(seg), kind, oid))
            keep_count[oid] = keep_count.get(oid, 0) + 1
        else:
            drop_count[oid] = drop_count.get(oid, 0) + 1

    # Second pass: drop triggers whose target group has no surviving members.
    # Iterate to chain-prune (drop A→B→C when C is orphan, then B, then A).
    TRIGGER_GAMEPLAY_KIND = 9
    orphan_dropped_total = 0
    while True:
        existing_groups: set[int] = set()
        for seg, _kind, _oid in kept_typed:
            for g in _groups_of_segment(seg):
                existing_groups.add(g)
        new_kept: list[tuple[str, int, int]] = []
        dropped_this_pass = 0
        for seg, kind, oid in kept_typed:
            if kind == TRIGGER_GAMEPLAY_KIND and _orphan_target(seg, existing_groups):
                drop_count[oid] = drop_count.get(oid, 0) + 1
                keep_count[oid] = max(0, keep_count.get(oid, 0) - 1)
                dropped_this_pass += 1
                continue
            new_kept.append((seg, kind, oid))
        kept_typed = new_kept
        orphan_dropped_total += dropped_this_pass
        if dropped_this_pass == 0:
            break

    kept = [seg for seg, _k, _o in kept_typed]

    log.info(
        "%d objects total → kept %d (gameplay) / dropped %d / orphan-trigger %d / unknown-id %d",
        len(object_segs),
        len(kept),
        len(object_segs) - len(kept),
        orphan_dropped_total,
        unknown_id_count,
    )
    log.info("top kept ids: %s", sorted(keep_count.items(), key=lambda kv: -kv[1])[:8])
    log.info("top dropped ids: %s", sorted(drop_count.items(), key=lambda kv: -kv[1])[:8])

    new_plaintext = header_str + ";" + ";".join(kept) + ";"
    new_encoded = _recompress(new_plaintext)

    # Mutate only the fields we want to change. Keep song (k8/k45/k46) etc.
    typed["k4"] = ("s", new_encoded)
    typed["k2"] = ("s", f"{name} (layout)")

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(_make_gmd_preserving(typed, bools), encoding="utf-8")

    print(f"\nwrote {OUT_PATH}")
    print(f"name in GD: {typed['k2'][1]!r}")
    print(f"objects: {len(object_segs)} → {len(kept)}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(_run()))
