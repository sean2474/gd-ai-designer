"""Export one downloaded level as a .gmd file with the first N leftmost objects removed.

Inputs (all from config.py):
    TEST_EXPORT_LEVEL_ID     — which raw JSON to load
    TEST_EXPORT_DROP_LEADING — how many lowest-x objects to drop
    TEST_EXPORT_GMD_PATH     — where to write the .gmd

After this runs, import the .gmd via Geode's gdshare mod to load it in GD.
"""
from __future__ import annotations

import base64
import gzip
import logging
import sys
from xml.sax.saxutils import escape as xml_escape

from gd_designer.data.config import (
    LOG_VERBOSITY,
    RAW_DIR,
    TEST_EXPORT_DROP_X_BELOW,
    TEST_EXPORT_GMD_PATH,
    TEST_EXPORT_LEVEL_ID,
)
from gd_designer.data.schema import RawLevel

log = logging.getLogger(__name__)


def _configure_logging(verbose: int) -> None:
    level = logging.WARNING
    if verbose >= 1:
        level = logging.INFO
    if verbose >= 2:
        level = logging.DEBUG
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def _make_gmd(name: str, creator: str, encoded_level: str) -> str:
    """Build a GD .gmd plist (short-tag variant RobTop uses)."""
    return (
        '<?xml version="1.0"?>\n'
        '<plist version="1.0" gjver="2.0">\n'
        "<dict>\n"
        "\t<k>kCEK</k><i>4</i>\n"
        f"\t<k>k2</k><s>{xml_escape(name)}</s>\n"
        f"\t<k>k4</k><s>{encoded_level}</s>\n"
        f"\t<k>k5</k><s>{xml_escape(creator)}</s>\n"
        "\t<k>k13</k><t/>\n"
        "\t<k>k21</k><i>2</i>\n"
        "\t<k>k50</k><i>35</i>\n"
        "</dict>\n"
        "</plist>\n"
    )


def _decompress_level_string(encoded: str) -> str:
    """Invert the base64(url-safe) + gzip wrapping GD uses."""
    padded = encoded + "=" * (-len(encoded) % 4)
    return gzip.decompress(base64.urlsafe_b64decode(padded)).decode("utf-8", errors="replace")


def _recompress_level_string(plaintext: str) -> str:
    """Re-apply GD's url-safe base64 + gzip wrapping.

    GD's parser is byte-pattern strict (not a real gzip decoder): emits/expects
    `mtime=0, XFL=0, OS=03 (Unix)` AND zlib compression level 6. Python defaults
    to level 9 which produces a valid-but-different deflate stream that GD
    rejects (loads as an empty level). Force the exact byte format.
    """
    compressed = bytearray(
        gzip.compress(plaintext.encode("utf-8"), compresslevel=6, mtime=0)
    )
    compressed[8] = 0      # XFL: no extra flags
    compressed[9] = 0x03   # OS: Unix
    return base64.urlsafe_b64encode(bytes(compressed)).decode("ascii")


def _x_from_segment(seg: str) -> float:
    """Extract key 2 (x) from a comma-separated `k,v,k,v,...` object segment
    without fully parsing into a dict (which would drop duplicate keys)."""
    parts = seg.split(",")
    for i in range(0, len(parts) - 1, 2):
        if parts[i] == "2":
            try:
                return float(parts[i + 1])
            except ValueError:
                return 0.0
    return 0.0


def main() -> int:
    _configure_logging(LOG_VERBOSITY)

    raw_path = RAW_DIR / f"{TEST_EXPORT_LEVEL_ID}.json"
    if not raw_path.exists():
        log.error("raw file not found: %s", raw_path)
        return 1

    raw = RawLevel.model_validate_json(raw_path.read_text(encoding="utf-8"))

    # Work from the string form directly — preserves duplicate keys and exact
    # formatting that a dict round-trip would lose.
    plaintext = _decompress_level_string(raw.level_string_raw)
    sections = plaintext.split(";")
    if not sections:
        log.error("empty level string after decompress")
        return 1
    header_str = sections[0]
    object_segs = [s for s in sections[1:] if s]  # drop trailing empty from final `;`

    log.info(
        "loaded %d (%s) — %d object segments", raw.level_id, raw.name, len(object_segs)
    )

    kept: list[str] = []
    dropped_xs: list[float] = []
    for seg in object_segs:
        x = _x_from_segment(seg)
        if x < TEST_EXPORT_DROP_X_BELOW:
            dropped_xs.append(x)
        else:
            kept.append(seg)

    log.info(
        "dropped %d objects with x < %g (x ∈ [%.1f, %.1f]); %d remain",
        len(dropped_xs),
        TEST_EXPORT_DROP_X_BELOW,
        min(dropped_xs) if dropped_xs else 0,
        max(dropped_xs) if dropped_xs else 0,
        len(kept),
    )

    new_plaintext = header_str + ";" + ";".join(kept) + ";"
    encoded = _recompress_level_string(new_plaintext)

    blocks = int(TEST_EXPORT_DROP_X_BELOW // 30)
    modified_name = f"{raw.name} (-{blocks}b)"
    gmd_xml = _make_gmd(modified_name, raw.creator, encoded)

    TEST_EXPORT_GMD_PATH.parent.mkdir(parents=True, exist_ok=True)
    TEST_EXPORT_GMD_PATH.write_text(gmd_xml, encoding="utf-8")

    print(
        f"wrote {TEST_EXPORT_GMD_PATH}  "
        f"(level_id={raw.level_id}, name={modified_name!r}, objects={len(kept)})"
    )
    print("import via Geode's gdshare mod to load in GD.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
