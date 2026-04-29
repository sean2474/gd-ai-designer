"""Phase 1b smoke test: render Future Funk at t = 1..100s (10s steps) into
PNG files via GDRWeb running in headless Chromium driven by Playwright.

Prereq: vite dev server running:
    cd ml/render/gdrweb-src && npm run dev
And the harness must be reachable at http://localhost:5173/test/harness.html.
"""
from __future__ import annotations

import asyncio
import base64
import logging
import sys
import time
from pathlib import Path

import base64 as b64lib
import gzip

from gd_designer.data.parse import convert_level
from gd_designer.data.schema import RawLevel

from playwright.async_api import async_playwright


HARNESS_URL = "http://localhost:5173/test/harness.html"
LEVEL_ID = 44062068  # Future Funk by JonathanGD
RAW_PATH = Path(f"/Users/sean2474/Desktop/project/gd-design-ai/data/raw/{LEVEL_ID}.json")
OUT_DIR = Path("/Users/sean2474/Desktop/project/gd-design-ai/data/renders/future_funk_anim")

# t (seconds) → cam_x. Rough 1x-speed approximation (311 px/sec). GDRWeb
# exposes a more accurate `level.timeAt(x)` we can use later, but for the
# smoke test this is close enough.
SPEED_PX_PER_SEC = 311
# Middle-section animation test: t = 30.0, 30.5, ..., 50.0 (41 frames @ 0.5s).
# Tight enough to see triggers / pulse / move animations cycle.
TIME_POINTS_S = [round(30 + 0.5 * i, 1) for i in range(41)]

# Camera-y heuristic: take the median y of gameplay objects within
# CAMERA_Y_WINDOW pixels of cam_x. Without a player physics sim we don't
# know the real y, but the median is close to where playable action lives.
CAMERA_Y_WINDOW = 600
GAMEPLAY_KINDS = {1, 2, 3, 4, 5, 6, 7}  # block / spike / orb / pad / portal / slope

# Zoom: 1.0 = GDRWeb default (very wide view); 2.0 ≈ in-game gameplay zoom.
# Higher zoom = closer-up; the visible y window shrinks so cam_y centering
# becomes more important.
CAMERA_ZOOM = 2.0

# Vertical offset on top of the median-y heuristic. GD's in-game camera
# sits above the player so the bottom of the screen lines up roughly with
# the ground; raising cam_y by ~90 (3 blocks) reproduces that and keeps
# the ground from dominating the lower half of the frame.
CAMERA_Y_OFFSET = 90.0


log = logging.getLogger(__name__)


def _plaintext(raw: RawLevel) -> str:
    # Use the ORIGINAL decompressed bytes verbatim — reconstructing from our
    # parsed dicts would lose duplicate keys / change ordering and confuse
    # GDRWeb's parser.
    encoded = raw.level_string_raw
    padded = encoded + "=" * (-len(encoded) % 4)
    return gzip.decompress(b64lib.urlsafe_b64decode(padded)).decode(
        "utf-8", errors="replace"
    )


async def _wait_for_ready(page, timeout_ms: int = 30000) -> None:
    log.info("waiting for harness to become ready…")
    await page.wait_for_function("() => window.gdReady === true", timeout=timeout_ms)


def _camera_y_for(cam_x: float, gameplay_xys: list[tuple[float, float]]) -> float:
    """Median y of gameplay objects within ±CAMERA_Y_WINDOW of cam_x,
    bumped up by CAMERA_Y_OFFSET so the ground doesn't dominate the frame."""
    ys = [y for x, y in gameplay_xys
          if cam_x - CAMERA_Y_WINDOW <= x <= cam_x + CAMERA_Y_WINDOW]
    if not ys:
        return CAMERA_Y_OFFSET
    ys.sort()
    return ys[len(ys) // 2] + CAMERA_Y_OFFSET


async def _render_one(page, cam_x: float, cam_y: float) -> bytes:
    await page.evaluate(f"window.gdSetCamera({cam_x}, {cam_y}, {CAMERA_ZOOM})")
    await page.evaluate("window.gdRender({ hideTriggers: true })")
    b64 = await page.evaluate("window.gdToPng()")
    return base64.b64decode(b64)


async def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    raw = RawLevel.model_validate_json(RAW_PATH.read_text(encoding="utf-8"))
    log.info("loaded level %d (%s) — %d objects",
             raw.level_id, raw.name, raw.object_count)

    plaintext = _plaintext(raw)
    log.info("plaintext bytes: %d", len(plaintext))

    # Build a (x, y) list of gameplay objects for the camera-y heuristic.
    parsed = convert_level(raw)
    import json as _json
    kind_map_path = Path(
        "/Users/sean2474/Desktop/project/gd-design-ai/data/object_ids.json"
    )
    kind_map: dict[int, int] = {}
    if kind_map_path.exists():
        kdata = _json.loads(kind_map_path.read_text(encoding="utf-8"))
        kind_map = {int(k): int(v["kind"]) for k, v in kdata.get("ids", {}).items()}
    gameplay_xys = [
        (obj.x, obj.y)
        for obj in parsed.objects
        if kind_map.get(obj.object_id, -1) in GAMEPLAY_KINDS
    ]
    log.info("gameplay objects (for cam-y heuristic): %d", len(gameplay_xys))

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as pw:
        # Headless Chromium ships without GPU drivers — WebGL silently fails
        # unless we point it at the swiftshader software backend.
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
        page.on("console", lambda msg: log.debug("[browser] %s", msg.text))
        page.on("pageerror", lambda exc: log.error("[browser-error] %s", exc))

        await page.goto(HARNESS_URL)
        await _wait_for_ready(page)

        log.info("loading level into renderer…")
        loaded = await page.evaluate(
            "(plain) => window.gdLoadLevel(plain)", plaintext
        )
        if not loaded:
            log.error("gdLoadLevel returned false")
            return 1

        for t in TIME_POINTS_S:
            cam_x = t * SPEED_PX_PER_SEC
            cam_y = _camera_y_for(cam_x, gameplay_xys)
            t0 = time.monotonic()
            png = await _render_one(page, cam_x, cam_y)
            elapsed = (time.monotonic() - t0) * 1000
            t_label = f"{t:06.1f}s".replace(".", "_")
            out = OUT_DIR / f"t{t_label}.png"
            out.write_bytes(png)
            log.info(
                "t=%5.1fs  cam=(%6.0f, %5.0f)  → %s  (%d bytes, %.1f ms)",
                t, cam_x, cam_y, out.name, len(png), elapsed,
            )

        await browser.close()

    print(f"\nwrote {len(TIME_POINTS_S)} frames to {OUT_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
