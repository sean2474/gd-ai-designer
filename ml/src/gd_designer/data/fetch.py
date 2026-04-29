"""Stage 1 fetcher. Hybrid fetch: GDBrowser API for discovery/metadata
(clean 2.2 tier classification), RobTop GD server for the raw level string
(GDBrowser doesn't serve level payloads).

Spec: docs/DATA_COLLECTION.md §§2-5, §9. Output schema: schema.RawLevel.
Output: one JSON per level under data/raw/. SQLite migration deferred.
"""
from __future__ import annotations

import asyncio
import base64
import gzip
import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncIterator, Iterable

import httpx

from .rate_limiter import FailureStreak, TokenBucket
from .schema import (
    Length,
    ManifestEntry,
    RawLevel,
    Rating,
    RejectionEntry,
    RejectionReason,
)

log = logging.getLogger(__name__)

# ---- endpoints ----
GDBROWSER_BASE = "https://gdbrowser.com"
GD_BASE = "http://www.boomlings.com/database"  # fallback; primary is GDHistory
GDHISTORY_BASE = "https://history.geometrydash.eu"
GD_SECRET = "Wmfd2893gb7"  # public "download level" secret, same value GD client sends
USER_AGENT = "GDDesignAI-Crawler/0.1.0 (+https://github.com/sean2474/gd-ai-designer)"

# ---- filter thresholds ----
BACKOFF_SCHEDULE_SEC = (10, 30, 60, 120)
# Version window: GDBrowser gameVersion "1.9"→19, "2.0"→20, "2.1"→21, "2.2"→22.
# Lower bound 1.9 (pre-1.9 levels use a different object set entirely).
# No upper bound — 2.2 included for future use.
MIN_GAME_VERSION = 19
MAX_GAME_VERSION = 99
MIN_X_WIDTH_UNITS = 120     # ≥ 2 encoder windows; enforced in Stage 2 (needs parsed data)


@dataclass
class FetchConfig:
    output_dir: Path
    ratings: tuple[Rating, ...] = (Rating.FEATURED, Rating.EPIC, Rating.LEGENDARY, Rating.MYTHIC)
    exclude_platformer: bool = True
    rate_per_sec: float = 1.0
    max_pages_per_query: int = 100
    force: bool = False
    from_manifest: Path | None = None
    max_levels: int | None = None


@dataclass
class FetchStats:
    fetched: int = 0
    skipped_existing: int = 0
    rejected: int = 0
    errors: int = 0
    by_rating: dict[str, int] = field(default_factory=dict)


# ---------- GDBrowser metadata helpers ----------


_GDBROWSER_TYPE_FOR_RATING = {
    Rating.FEATURED: "featured",
    Rating.EPIC: "epic",
    Rating.LEGENDARY: "legendary",
    Rating.MYTHIC: "mythic",
}


def _rating_from_gdbrowser(meta: dict) -> Rating | None:
    """GDBrowser exposes booleans + `epicValue` (0..3). Use the most specific tier."""
    ev = meta.get("epicValue", 0) or 0
    if ev == 3 or meta.get("mythic"):
        return Rating.MYTHIC
    if ev == 2 or meta.get("legendary"):
        return Rating.LEGENDARY
    if ev == 1 or meta.get("epic"):
        return Rating.EPIC
    if meta.get("featured"):
        return Rating.FEATURED
    return None


def _length_from_gdbrowser(meta: dict) -> Length:
    name = str(meta.get("length", "")).lower()
    if meta.get("platformer"):
        return Length.PLATFORMER
    try:
        return Length(name)
    except ValueError:
        return Length.XL


def _game_version_int(meta: dict) -> int:
    """GDBrowser returns gameVersion as e.g. "2.2" — convert to 22."""
    raw = str(meta.get("gameVersion", "") or "")
    if not raw:
        return 0
    if "." in raw:
        a, b = raw.split(".", 1)
        try:
            return int(a) * 10 + int(b[:1])
        except ValueError:
            return 0
    try:
        return int(raw)
    except ValueError:
        return 0


# ---------- GD server response parsing ----------


def _safe_int(v: Any, default: int = 0) -> int:
    """Tolerant int parse for GDBrowser/GD responses where some fields are
    occasionally non-numeric (e.g., songID returning a track NAME 'Level 5')."""
    if v is None or v == "":
        return default
    try:
        return int(v)
    except (TypeError, ValueError):
        try:
            return int(float(v))
        except (TypeError, ValueError):
            return default


def _parse_gd_kv(body: str) -> dict[str, str]:
    """RobTop's downloadGJLevel22 returns `k:v:k:v:...#hash`. Parse to dict."""
    head, _, _tail = body.partition("#")
    parts = head.split(":")
    return {parts[i]: parts[i + 1] for i in range(0, len(parts) - 1, 2)}


def _parse_kv_comma(s: str) -> dict[str, str]:
    """GD level header / objects are `k,v,k,v,...` comma-separated."""
    if not s:
        return {}
    parts = s.split(",")
    return {parts[i]: parts[i + 1] for i in range(0, len(parts) - 1, 2)}


def decode_level_string(encoded: str) -> tuple[dict[str, str], list[dict[str, str]]]:
    """Decode GD's key-4 field: url-safe base64 → gzip → ASCII.

    Returns (level_header, objects). Format:
        "<kA1,v,kA2,v,...>;<obj1 k,v,...>;<obj2 k,v,...>;...;"
    Trailing empty segments from the final `;` are dropped.
    """
    if not encoded:
        return {}, []
    padded = encoded + "=" * (-len(encoded) % 4)
    compressed = base64.urlsafe_b64decode(padded)
    data_str = gzip.decompress(compressed).decode("utf-8", errors="replace")
    sections = data_str.split(";")
    header = _parse_kv_comma(sections[0]) if sections else {}
    objects = [_parse_kv_comma(s) for s in sections[1:] if s]
    return header, objects


# ---------- IO ----------


def _level_path(cfg: FetchConfig, level_id: int) -> Path:
    return cfg.output_dir / f"{level_id}.json"


def _write_raw(path: Path, raw: RawLevel) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(raw.model_dump_json(indent=2), encoding="utf-8")


def _append_rejection(cfg: FetchConfig, entry: RejectionEntry) -> None:
    path = cfg.output_dir.parent / "rejection_log.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(entry.model_dump_json() + "\n")


def _append_manifest(cfg: FetchConfig, entry: ManifestEntry) -> None:
    path = cfg.output_dir.parent / "manifest.csv"
    new = not path.exists()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        if new:
            f.write("level_id,creator,name,rating,object_count,raw_hash\n")
        safe_name = entry.name.replace('"', "'")
        safe_creator = entry.creator.replace('"', "'")
        f.write(
            f'{entry.level_id},"{safe_creator}","{safe_name}",'
            f"{entry.rating.value},{entry.object_count},{entry.raw_hash}\n"
        )


def _sha256(s: str) -> str:
    return "sha256:" + hashlib.sha256(s.encode("utf-8")).hexdigest()


def _state_path(cfg: FetchConfig) -> Path:
    return cfg.output_dir.parent / "crawl_state.json"


def _load_state(path: Path) -> dict[str, int]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        log.warning("could not load crawl state %s: %r", path, exc)
        return {}


def _save_state(path: Path, state: dict[str, int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(state), encoding="utf-8")
    tmp.replace(path)


def _read_manifest_ids(path: Path) -> list[int]:
    ids: list[int] = []
    with path.open("r", encoding="utf-8") as f:
        header = f.readline()
        if "level_id" not in header:
            raise ValueError(f"manifest missing header: {path}")
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                ids.append(int(line.split(",", 1)[0]))
            except ValueError:
                continue
    return ids


# ---------- backoff ----------


async def _with_backoff(
    call: Any,
    *args: Any,
    streak: FailureStreak,
    label: str = "",
    **kwargs: Any,
) -> Any:
    last_exc: BaseException | None = None
    for delay in (0, *BACKOFF_SCHEDULE_SEC):
        if delay:
            log.warning("backoff %ss (%s)", delay, label)
            await asyncio.sleep(delay)
        try:
            result = await call(*args, **kwargs)
            streak.success()
            return result
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            last_exc = exc
            log.debug("call failed (%s): %r", label, exc)
    await streak.failure()
    assert last_exc is not None
    raise last_exc


# ---------- HTTP calls ----------


async def _gdbrowser_search(
    http: httpx.AsyncClient, search_type: str, page: int
) -> list[dict]:
    resp = await http.get(
        f"{GDBROWSER_BASE}/api/search/*",
        params={"type": search_type, "page": page},
    )
    resp.raise_for_status()
    data = resp.json()
    return data if isinstance(data, list) else []


async def _gd_download(http: httpx.AsyncClient, level_id: int) -> dict[str, str]:
    """Direct RobTop download — fallback path. Aggressively rate-limited (429s)."""
    resp = await http.post(
        f"{GD_BASE}/downloadGJLevel22.php",
        data={"levelID": str(level_id), "secret": GD_SECRET},
        headers={"User-Agent": ""},
    )
    resp.raise_for_status()
    body = resp.text
    if body.strip() == "-1":
        raise ValueError(f"GD server returned -1 for level {level_id}")
    return _parse_gd_kv(body)


_GMD_K_RE = re.compile(r"<k>(k\d+)</k>\s*<[isr]>([^<]*)</[isr]>")


def _parse_gmd(gmd_text: str) -> dict[str, str]:
    """Pull out k4 (level data) and other k* fields from a GMD plist."""
    return {k: v for k, v in _GMD_K_RE.findall(gmd_text)}


async def _gdhistory_meta(http: httpx.AsyncClient, level_id: int) -> dict:
    resp = await http.get(f"{GDHISTORY_BASE}/api/v1/level/{level_id}/")
    resp.raise_for_status()
    return resp.json()


async def _gdhistory_download(
    http: httpx.AsyncClient, level_id: int, record_id: int
) -> str:
    """Download GMD plist text from GDHistory for a specific record."""
    resp = await http.get(
        f"{GDHISTORY_BASE}/level/{level_id}/{record_id}/download/"
    )
    resp.raise_for_status()
    return resp.text


def _pick_record(meta: dict) -> int | None:
    """Pick the newest record that actually has the level string available."""
    records = meta.get("records") or []
    candidates = [r for r in records if r.get("level_string_available")]
    if not candidates:
        return None
    candidates.sort(
        key=lambda r: r.get("cache_real_date", "") or "", reverse=True
    )
    return int(candidates[0]["id"])


async def _fetch_level_kv_via_gdhistory(
    http: httpx.AsyncClient, level_id: int
) -> dict[str, str] | None:
    """Try GDHistory first. Returns key-value dict shaped like RobTop's response
    (minimum: key 4 = level string), or None if GDHistory has no usable record."""
    meta = await _gdhistory_meta(http, level_id)
    if not meta.get("cache_level_string_available"):
        return None
    rec_id = _pick_record(meta)
    if rec_id is None:
        return None
    gmd_text = await _gdhistory_download(http, level_id, rec_id)
    kv = _parse_gmd(gmd_text)
    if "k4" not in kv:
        return None
    # Map GMD's k* keys to RobTop's numeric keys for downstream compatibility.
    out: dict[str, str] = {"4": kv["k4"]}
    if "k1" in kv:
        out["1"] = kv["k1"]
    if "k2" in kv:
        out["2"] = kv["k2"]
    return out


# ---------- filters ----------


def _check_metadata(
    meta: dict, cfg: FetchConfig
) -> tuple[Rating | None, RejectionReason | None, str]:
    rating = _rating_from_gdbrowser(meta)
    if rating is None:
        return None, RejectionReason.NOT_RATED, ""
    if rating not in cfg.ratings:
        return rating, RejectionReason.NOT_RATED, f"tier {rating.value} not requested"

    if cfg.exclude_platformer and meta.get("platformer"):
        return rating, RejectionReason.PLATFORMER, ""

    gv = _game_version_int(meta)
    if gv and gv < MIN_GAME_VERSION:
        return rating, RejectionReason.GAME_VERSION_TOO_OLD, f"gv={gv}"
    if gv and gv > MAX_GAME_VERSION:
        return rating, RejectionReason.GAME_VERSION_TOO_NEW, f"gv={gv}"

    return rating, None, ""


# ---------- per-level ----------


async def _process_level(
    http: httpx.AsyncClient,
    meta: dict,
    cfg: FetchConfig,
    bucket: TokenBucket,
    streak: FailureStreak,
    stats: FetchStats,
) -> None:
    try:
        level_id = int(meta["id"])
    except (KeyError, ValueError):
        stats.errors += 1
        return

    path = _level_path(cfg, level_id)
    if path.exists() and not cfg.force:
        stats.skipped_existing += 1
        return

    rating, reject, detail = _check_metadata(meta, cfg)
    if reject is not None:
        stats.rejected += 1
        _append_rejection(
            cfg,
            RejectionEntry(level_id=level_id, reason=reject, detail=detail),
        )
        return
    assert rating is not None

    # Primary: GDHistory (Cloudflare-cached, kinder rate limits).
    # Fallback: RobTop boomlings.com (gets 429'd quickly).
    kv: dict[str, str] | None = None
    try:
        await bucket.acquire()
        kv = await _with_backoff(
            _fetch_level_kv_via_gdhistory,
            http,
            level_id,
            streak=streak,
            label=f"gdhistory {level_id}",
        )
    except Exception as exc:
        log.debug("gdhistory failed for %d: %r — falling back", level_id, exc)
        kv = None

    if kv is None:
        try:
            await bucket.acquire()
            kv = await _with_backoff(
                _gd_download,
                http,
                level_id,
                streak=streak,
                label=f"boomlings {level_id}",
            )
        except Exception as exc:
            stats.errors += 1
            _append_rejection(
                cfg,
                RejectionEntry(
                    level_id=level_id,
                    reason=RejectionReason.FETCH_ERROR,
                    detail=repr(exc)[:200],
                ),
            )
            return

    level_string = kv.get("4", "")
    if not level_string:
        stats.rejected += 1
        _append_rejection(
            cfg,
            RejectionEntry(level_id=level_id, reason=RejectionReason.EMPTY_LEVEL_STRING),
        )
        return

    creator = str(meta.get("author", "") or "")
    # GDBrowser returns "songID": "Level 5" (string name) for the original
    # game's official tracks; only customSong is numeric. Try numeric paths
    # first, fall back to officialSong index, finally 0.
    song_id = _safe_int(meta.get("customSong")) or _safe_int(meta.get("songID"))
    if not song_id:
        song_id = _safe_int(meta.get("officialSong"))

    # GDBrowser's "objects" meta is occasionally 0 even for non-empty levels
    # (older or recently re-uploaded levels). Decode the actual level string
    # and count semicolons → real object count. Fall back to meta on parse
    # failure so we still record something.
    try:
        _, decoded_objs = decode_level_string(level_string)
        decoded_count = len(decoded_objs)
    except Exception:
        decoded_count = 0
    meta_count = _safe_int(meta.get("objects"))
    actual_object_count = decoded_count if decoded_count > 0 else meta_count

    raw = RawLevel(
        level_id=level_id,
        name=str(meta.get("name", "") or ""),
        creator=creator,
        rating=rating,
        song_id=song_id,
        object_count=actual_object_count,
        length=_length_from_gdbrowser(meta),
        platformer=bool(meta.get("platformer", False)),
        game_version=_game_version_int(meta),
        level_string_raw=level_string,
    )
    _write_raw(path, raw)
    _append_manifest(
        cfg,
        ManifestEntry(
            level_id=level_id,
            creator=creator,
            name=raw.name,
            rating=rating,
            object_count=raw.object_count,
            raw_hash=_sha256(level_string),
        ),
    )
    stats.fetched += 1
    stats.by_rating[rating.value] = stats.by_rating.get(rating.value, 0) + 1
    log.info("saved %d (%s, %d objs)", level_id, rating.value, raw.object_count)


# ---------- discovery ----------


async def _stream_search(
    http: httpx.AsyncClient,
    cfg: FetchConfig,
    bucket: TokenBucket,
    streak: FailureStreak,
) -> "AsyncIterator[dict]":
    """Yield GDBrowser search results across all requested tiers, deduped.

    Resumable via `state_path` (a JSON file mapping rating-name → last completed
    page). On startup we resume from `last_page + 1`; after each page we
    persist progress so a kill+restart picks up where we left off.
    """
    state_path = _state_path(cfg)
    state = _load_state(state_path)
    seen: set[int] = set()
    for rating in cfg.ratings:
        search_type = _GDBROWSER_TYPE_FOR_RATING[rating]
        start_page = state.get(rating.value, -1) + 1
        if start_page > 0:
            log.info("resuming %s from page %d", search_type, start_page)
        for page in range(start_page, cfg.max_pages_per_query):
            await bucket.acquire()
            try:
                items = await _with_backoff(
                    _gdbrowser_search,
                    http,
                    search_type,
                    page,
                    streak=streak,
                    label=f"search {search_type} p{page}",
                )
            except Exception as exc:
                log.error("search gave up: %s p%d: %r", search_type, page, exc)
                break
            if not items:
                break

            added_this_page = 0
            for m in items:
                try:
                    lid = int(m.get("id", 0))
                except (TypeError, ValueError):
                    continue
                if lid <= 0 or lid in seen:
                    continue
                seen.add(lid)
                added_this_page += 1
                yield m
            state[rating.value] = page
            _save_state(state_path, state)
            if added_this_page == 0:
                break


async def _stream_manifest(
    http: httpx.AsyncClient,
    path: Path,
    bucket: TokenBucket,
    streak: FailureStreak,
) -> "AsyncIterator[dict]":
    """Re-pull metadata from GDBrowser for each id in an existing manifest."""
    ids = _read_manifest_ids(path)
    for lid in ids:
        await bucket.acquire()
        try:
            resp = await _with_backoff(
                http.get,
                f"{GDBROWSER_BASE}/api/level/{lid}",
                streak=streak,
                label=f"meta {lid}",
            )
            resp.raise_for_status()
            meta = resp.json()
        except Exception as exc:
            log.warning("skip manifest id %d: %r", lid, exc)
            continue
        if isinstance(meta, dict):
            yield meta


# ---------- public ----------


async def collect_raw(cfg: FetchConfig) -> FetchStats:
    cfg.output_dir.mkdir(parents=True, exist_ok=True)
    stats = FetchStats()
    bucket = TokenBucket(rate_per_sec=cfg.rate_per_sec)
    streak = FailureStreak()
    sem = asyncio.Semaphore(1)

    async with httpx.AsyncClient(
        headers={"User-Agent": USER_AGENT},
        timeout=30.0,
        follow_redirects=True,
    ) as http:
        if cfg.from_manifest is not None:
            source = _stream_manifest(http, cfg.from_manifest, bucket, streak)
        else:
            source = _stream_search(http, cfg, bucket, streak)

        seen_candidates = 0
        async for meta in source:
            seen_candidates += 1
            async with sem:
                await _process_level(http, meta, cfg, bucket, streak, stats)
            if cfg.max_levels and stats.fetched >= cfg.max_levels:
                log.info("reached max_levels=%d saved, stopping", cfg.max_levels)
                break
            if seen_candidates % 25 == 0:
                log.info(
                    "progress %d cand (saved=%d skipped=%d rejected=%d err=%d)",
                    seen_candidates,
                    stats.fetched,
                    stats.skipped_existing,
                    stats.rejected,
                    stats.errors,
                )
    return stats


def iter_raw_files(raw_dir: Path) -> Iterable[Path]:
    return sorted(raw_dir.glob("*.json"))
