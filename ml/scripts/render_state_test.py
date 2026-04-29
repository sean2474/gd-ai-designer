"""Phase B smoke test: extract resolved-state snapshots (channels + group
states + group transforms) from GDRWeb at multiple times in Future Funk.

Output: data/renders/future_funk_state/snapshots.json — one JSON file
containing a list of per-time snapshots. The static objects already live
in the SQLite DB; combine the two for per-object resolved state.
"""
from __future__ import annotations

import asyncio
import base64
import gzip
import json
import logging
import sys
import time as time_mod
from pathlib import Path

from gd_designer.data.schema import RawLevel

from playwright.async_api import async_playwright


HARNESS_URL = "http://localhost:5173/test/harness.html"
LEVEL_ID = 44062068
RAW_PATH = Path(f"/Users/sean2474/Desktop/project/gd-design-ai/data/raw/{LEVEL_ID}.json")
OUT_DIR = Path("/Users/sean2474/Desktop/project/gd-design-ai/data/renders/future_funk_state")

# Same dense middle-section as the image test, so they're directly comparable.
TIME_POINTS_S = [round(30 + 0.5 * i, 1) for i in range(41)]


log = logging.getLogger(__name__)


def _plaintext(raw: RawLevel) -> str:
    encoded = raw.level_string_raw
    padded = encoded + "=" * (-len(encoded) % 4)
    return gzip.decompress(base64.urlsafe_b64decode(padded)).decode(
        "utf-8", errors="replace"
    )


async def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    raw = RawLevel.model_validate_json(RAW_PATH.read_text(encoding="utf-8"))
    log.info("loaded %d (%s)", raw.level_id, raw.name)
    plaintext = _plaintext(raw)

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
            args=[
                "--use-gl=swiftshader",
                "--use-angle=swiftshader",
                "--enable-webgl",
                "--ignore-gpu-blocklist",
                "--enable-unsafe-swiftshader",
            ],
        )
        context = await browser.new_context(viewport={"width": 1280, "height": 720})
        page = await context.new_page()
        page.on("pageerror", lambda exc: log.error("[browser-error] %s", exc))
        await page.goto(HARNESS_URL)
        await page.wait_for_function("() => window.gdReady === true", timeout=30000)

        loaded = await page.evaluate("(p) => window.gdLoadLevel(p)", plaintext)
        if not loaded:
            log.error("gdLoadLevel false")
            return 1

        snapshots = []
        for t in TIME_POINTS_S:
            t0 = time_mod.monotonic()
            snap = await page.evaluate(f"window.gdGetState({t})")
            elapsed = (time_mod.monotonic() - t0) * 1000
            snapshots.append(snap)
            log.info(
                "t=%5.1fs  channels=%d groups=%d  (%.1f ms)",
                t, len(snap["channels"]), len(snap["groups"]), elapsed,
            )

        await browser.close()

    out_path = OUT_DIR / "snapshots.json"
    out_path.write_text(
        json.dumps({"level_id": raw.level_id, "snapshots": snapshots}),
        encoding="utf-8",
    )

    print(f"\nwrote {out_path}  ({out_path.stat().st_size:,} bytes)")

    # Quick sanity: how many channels actually change between adjacent snapshots?
    s0 = snapshots[0]["channels"]
    s_last = snapshots[-1]["channels"]
    diff = sum(
        1 for k in s0 if s0[k] != s_last.get(k)
    )
    print(f"channels that changed t={TIME_POINTS_S[0]}→t={TIME_POINTS_S[-1]}: {diff}/{len(s0)}")

    g0 = snapshots[0]["groups"]
    g_last = snapshots[-1]["groups"]
    moved = sum(
        1 for k in g0
        if g0[k]["tx"] != g_last.get(k, {}).get("tx")
        or g0[k]["ty"] != g_last.get(k, {}).get("ty")
    )
    print(f"groups that moved: {moved}/{len(g0)}")

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
