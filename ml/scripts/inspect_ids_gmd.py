"""Build a tiny GD level containing only the mystery object IDs from
strip_decoration_test (1220, 1722, 1582, 1202, 1716) so we can import it
and visually identify what each one is.

Layout:
  - basic blocks (id=1) along the ground for visual reference / floor
  - 3 instances of each mystery ID at y=45 (one block above the ground),
    spaced 30 units apart, with a 90-unit gap between different IDs
  - prints the x→ID legend so you know which span is which
"""
from __future__ import annotations

import base64
import gzip
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape


MYSTERY_IDS: list[int] = [1220, 1722, 1582, 1202, 1716]
INSTANCES_PER_ID = 3
INSTANCE_SPACING = 30
ID_GAP = 90
GROUND_Y = 15
ABOVE_GROUND_Y = 45
START_PADDING_BLOCKS = 4  # ground blocks before the first mystery object

OUT = Path("/Users/sean2474/Desktop/project/gd-design-ai/data/mystery_ids_test.gmd")

# Minimal level header — defaults for color/ground/bg, no triggers, classic mode.
HEADER = "kA13,0,kA15,0,kA16,0,kA14,,kA6,0,kA7,1,kA17,2"


def _encode(plaintext: str) -> str:
    """GD's exact byte format: gzip(level=6, mtime=0, XFL=0, OS=03) → urlsafe-b64."""
    compressed = bytearray(gzip.compress(plaintext.encode("utf-8"), compresslevel=6, mtime=0))
    compressed[8] = 0
    compressed[9] = 0x03
    return base64.urlsafe_b64encode(bytes(compressed)).decode("ascii")


def _make_gmd(name: str, encoded: str) -> str:
    return (
        '<?xml version="1.0"?>\n'
        '<plist version="1.0" gjver="2.0">\n<dict>\n'
        "\t<k>kCEK</k><i>4</i>\n"
        f"\t<k>k2</k><s>{xml_escape(name)}</s>\n"
        f"\t<k>k4</k><s>{encoded}</s>\n"
        "\t<k>k5</k><s>gd-design-ai</s>\n"
        "\t<k>k13</k><t/>\n"
        "\t<k>k21</k><i>2</i>\n"
        "\t<k>k50</k><i>35</i>\n"
        "</dict>\n</plist>\n"
    )


def main() -> None:
    segments: list[str] = []
    legend: list[tuple[int, int, int]] = []  # (id, x_start, x_end_inclusive)

    # Spawn-area floor.
    for i in range(START_PADDING_BLOCKS):
        segments.append(f"1,1,2,{i * 30},3,{GROUND_Y}")

    x = START_PADDING_BLOCKS * 30 + 30
    for oid in MYSTERY_IDS:
        x_start = x
        for _ in range(INSTANCES_PER_ID):
            # Mystery object floating just above ground level.
            segments.append(f"1,{oid},2,{x},3,{ABOVE_GROUND_Y}")
            # Ground block underneath for reference.
            segments.append(f"1,1,2,{x},3,{GROUND_Y}")
            x += INSTANCE_SPACING
        legend.append((oid, x_start, x - INSTANCE_SPACING))
        x += ID_GAP

    plaintext = HEADER + ";" + ";".join(segments) + ";"
    encoded = _encode(plaintext)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(_make_gmd("Mystery IDs Test", encoded), encoding="utf-8")

    print(f"wrote {OUT}")
    print(f"name in GD: 'Mystery IDs Test'")
    print(f"objects placed: {len(segments)}")
    print()
    print("x range → id:")
    for oid, x_start, x_end in legend:
        print(f"  x = {x_start:>4} .. {x_end:<4}  →  id {oid}")


if __name__ == "__main__":
    main()
