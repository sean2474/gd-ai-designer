"""Stage 1 fetcher. Hybrid fetch: GDBrowser API for discovery/metadata
(clean 2.2 tier classification), RobTop GD server for the raw level string
(GDBrowser doesn't serve level payloads).

Spec: docs/DATA_COLLECTION.md §§2-5, §9. Output schema: schema.RawLevel.
Output: one JSON per level under data/raw/. SQLite migration deferred.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

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
GD_BASE = "http://www.boomlings.com/database"
GD_SECRET = "Wmfd2893gb7"  # public "download level" secret, same value GD client sends
USER_AGENT = "GDDesignAI-Crawler/0.1.0 (+https://github.com/sean2474/gd-ai-designer)"

# ---- filter thresholds (per DATA_COLLECTION.md §3 + user additions) ----
BACKOFF_SCHEDULE_SEC = (10, 30, 60, 120)
OBJECT_COUNT_MIN = 10
OBJECT_COUNT_MAX = 20_000
MIN_GAME_VERSION = 21       # 2.1+; 2.0 uses different object set
MIN_UPLOAD_YEAR = 2019      # decoration conventions stabilize after 2019-01-01
MIN_X_WIDTH_UNITS = 120     # ≥ 2 encoder windows; enforced in Stage 2 (needs parsed data)

_YEARS_AGO = re.compile(r"(\d+)\s*year", re.IGNORECASE)


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


def _parse_gd_kv(body: str) -> dict[str, str]:
    """RobTop's downloadGJLevel22 returns `k:v:k:v:...#hash`. Parse to dict."""
    head, _, _tail = body.partition("#")
    parts = head.split(":")
    return {parts[i]: parts[i + 1] for i in range(0, len(parts) - 1, 2)}


def _parse_upload_year(uploaded_text: str, today: datetime) -> int | None:
    """GD returns fuzzy strings like "2 years" / "5 months" / "3 weeks". Best-effort year."""
    if not uploaded_text:
        return None
    m = _YEARS_AGO.search(uploaded_text)
    if m:
        return today.year - int(m.group(1))
    # months/weeks/days all mean same-year-ish — return current year.
    return today.year


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
    """Direct RobTop download. Requires empty UA (GD client sends no UA)."""
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

    obj_count = int(meta.get("objects", 0) or 0)
    if not (OBJECT_COUNT_MIN <= obj_count <= OBJECT_COUNT_MAX):
        return rating, RejectionReason.OBJECT_COUNT_OUT_OF_RANGE, f"n={obj_count}"

    gv = _game_version_int(meta)
    if gv and gv < MIN_GAME_VERSION:
        return rating, RejectionReason.GAME_VERSION_TOO_OLD, f"gv={gv}"

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

    await bucket.acquire()
    try:
        kv = await _with_backoff(
            _gd_download, http, level_id, streak=streak, label=f"download {level_id}"
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

    # Secondary filter: upload year (key 28 = "X years/months/weeks ago" text).
    now = datetime.now(timezone.utc)
    upload_year = _parse_upload_year(kv.get("28", ""), now)
    if upload_year is not None and upload_year < MIN_UPLOAD_YEAR:
        stats.rejected += 1
        _append_rejection(
            cfg,
            RejectionEntry(
                level_id=level_id,
                reason=RejectionReason.GAME_VERSION_TOO_OLD,
                detail=f"uploaded ~{upload_year} (< {MIN_UPLOAD_YEAR})",
            ),
        )
        return

    creator = str(meta.get("author", "") or "")
    song_id = int(meta.get("songID", 0) or meta.get("customSong", 0) or 0)

    raw = RawLevel(
        level_id=level_id,
        name=str(meta.get("name", "") or ""),
        creator=creator,
        rating=rating,
        song_id=song_id,
        object_count=int(meta.get("objects", 0) or 0),
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


async def _collect_candidates(
    http: httpx.AsyncClient,
    cfg: FetchConfig,
    bucket: TokenBucket,
    streak: FailureStreak,
) -> list[dict]:
    """Walk GDBrowser search pages for each requested tier, dedupe by id."""
    seen: set[int] = set()
    out: list[dict] = []

    for rating in cfg.ratings:
        search_type = _GDBROWSER_TYPE_FOR_RATING[rating]
        for page in range(cfg.max_pages_per_query):
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
                out.append(m)
                added_this_page += 1
            if added_this_page == 0:
                break
            if cfg.max_levels and len(out) >= cfg.max_levels:
                return out
    return out


async def _candidates_from_manifest(
    http: httpx.AsyncClient,
    path: Path,
    bucket: TokenBucket,
    streak: FailureStreak,
) -> list[dict]:
    """When reproducing, manifest gives level ids. Re-pull metadata for filtering."""
    ids = _read_manifest_ids(path)
    out: list[dict] = []
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
            if isinstance(meta, dict):
                out.append(meta)
        except Exception as exc:
            log.warning("skip manifest id %d: %r", lid, exc)
    return out


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
            candidates = await _candidates_from_manifest(http, cfg.from_manifest, bucket, streak)
        else:
            candidates = await _collect_candidates(http, cfg, bucket, streak)

        if cfg.max_levels:
            candidates = candidates[: cfg.max_levels]
        log.info("discovered %d candidate levels", len(candidates))

        for i, meta in enumerate(candidates):
            async with sem:
                await _process_level(http, meta, cfg, bucket, streak, stats)
            if (i + 1) % 25 == 0:
                log.info(
                    "progress %d/%d (saved=%d skipped=%d rejected=%d err=%d)",
                    i + 1,
                    len(candidates),
                    stats.fetched,
                    stats.skipped_existing,
                    stats.rejected,
                    stats.errors,
                )
    return stats


def iter_raw_files(raw_dir: Path) -> Iterable[Path]:
    return sorted(raw_dir.glob("*.json"))
