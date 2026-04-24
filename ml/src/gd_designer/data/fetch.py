"""Stage 1 fetcher. Pulls rated GD levels via gd.py and saves raw JSON per level.

Spec: docs/DATA_COLLECTION.md §§2-5, §9. Output schema: schema.RawLevel.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import gd

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

USER_AGENT = "GDDesignAI-Crawler/0.1.0 (+https://github.com/sean2474/gd-ai-designer)"
BACKOFF_SCHEDULE_SEC = (10, 30, 60, 120)
OBJECT_COUNT_MIN = 10
OBJECT_COUNT_MAX = 20_000
MIN_GAME_VERSION = 21  # 2.1+; 2.0 has different object set (DATA_COLLECTION.md §3)
MIN_UPLOAD_YEAR = 2019  # decoration conventions stabilize after 2019-01-01
MIN_X_WIDTH_UNITS = 120  # ensures ≥ 2 encoder windows (ENCODER.md §1)


@dataclass
class FetchConfig:
    output_dir: Path
    ratings: tuple[Rating, ...] = (Rating.FEATURED, Rating.EPIC, Rating.LEGENDARY, Rating.MYTHIC)
    exclude_platformer: bool = True
    rate_per_sec: float = 1.0
    max_pages_per_query: int = 100
    force: bool = False
    from_manifest: Path | None = None
    max_levels: int | None = None  # dry-run cap


@dataclass
class FetchStats:
    fetched: int = 0
    skipped_existing: int = 0
    rejected: int = 0
    errors: int = 0
    by_rating: dict[str, int] = field(default_factory=dict)


# ---------- rating classification ----------


def _classify_rating(level: gd.Level) -> Rating | None:
    """Return the highest applicable trophy tier, or None if unrated.

    gd.py exposes tier flags on the Level model. We probe them defensively because
    the mythic tier was added in GD 2.2 and older gd.py versions may not ship it.
    """
    # Prefer the most specific tier first.
    if getattr(level, "is_mythic", lambda: False)():
        return Rating.MYTHIC
    if getattr(level, "is_legendary", lambda: False)():
        return Rating.LEGENDARY
    if getattr(level, "is_epic", lambda: False)():
        return Rating.EPIC
    if getattr(level, "is_featured", lambda: False)():
        return Rating.FEATURED
    return None


def _normalize_length(level: gd.Level) -> Length:
    raw = getattr(level, "length", None)
    name = getattr(raw, "name", str(raw)).lower()
    try:
        return Length(name)
    except ValueError:
        # Unknown — treat as XL to avoid data loss; rejection filter may still drop it.
        return Length.XL


def _is_platformer(level: gd.Level) -> bool:
    fn = getattr(level, "is_platformer", None)
    if callable(fn):
        return bool(fn())
    return bool(getattr(level, "platformer", False))


# ---------- paths / IO ----------


def _level_path(cfg: FetchConfig, level_id: int) -> Path:
    return cfg.output_dir / f"{level_id}.json"


def _write_raw(path: Path, raw: RawLevel) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(raw.model_dump_json(indent=2), encoding="utf-8")


def _rejection_log_path(cfg: FetchConfig) -> Path:
    return cfg.output_dir.parent / "rejection_log.jsonl"


def _append_rejection(cfg: FetchConfig, entry: RejectionEntry) -> None:
    path = _rejection_log_path(cfg)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(entry.model_dump_json() + "\n")


def _manifest_path(cfg: FetchConfig) -> Path:
    return cfg.output_dir.parent / "manifest.csv"


def _append_manifest(cfg: FetchConfig, entry: ManifestEntry) -> None:
    path = _manifest_path(cfg)
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


# ---------- backoff-aware single call ----------


async def _with_backoff(
    call: Any,
    *args: Any,
    streak: FailureStreak,
    label: str = "",
    **kwargs: Any,
) -> Any:
    """Run an awaitable with the §4.3 schedule on 429/503-like errors."""
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
        except Exception as exc:  # gd.py wraps HTTP errors; treat all as retryable here
            last_exc = exc
            log.debug("call failed (%s): %r", label, exc)
    await streak.failure()
    assert last_exc is not None
    raise last_exc


# ---------- discovery ----------


async def _search_level_ids(
    client: gd.Client,
    rating: Rating,
    cfg: FetchConfig,
    bucket: TokenBucket,
    streak: FailureStreak,
) -> list[int]:
    """Walk search pages for one rating tier, return deduped level ids.

    gd.py's search API changes between versions; we lean on SearchStrategy enum values
    that have been stable (FEATURED, EPIC, AWARDED). Mythic/Legendary share the EPIC
    strategy and are filtered by tier flag on the level object during download.
    """
    strategy_name = {
        Rating.FEATURED: "FEATURED",
        Rating.EPIC: "EPIC",
        Rating.LEGENDARY: "EPIC",
        Rating.MYTHIC: "EPIC",
    }[rating]

    SearchStrategy = getattr(gd, "SearchStrategy", None)
    strategy = getattr(SearchStrategy, strategy_name, None) if SearchStrategy else None
    if strategy is None:
        log.error("gd.py missing SearchStrategy.%s; skipping %s", strategy_name, rating.value)
        return []

    ids: list[int] = []
    seen: set[int] = set()
    for page in range(cfg.max_pages_per_query):
        await bucket.acquire()
        try:
            results = await _with_backoff(
                client.search_levels_on_page,
                strategy=strategy,
                page=page,
                streak=streak,
                label=f"search {rating.value} p{page}",
            )
        except Exception as exc:
            log.error("search gave up at %s p%d: %r", rating.value, page, exc)
            break

        page_ids = [int(lvl.id) for lvl in results] if results else []
        if not page_ids:
            break

        new = [i for i in page_ids if i not in seen]
        if not new:
            # Page returned only duplicates → exhausted.
            break
        seen.update(new)
        ids.extend(new)

        if cfg.max_levels and len(ids) >= cfg.max_levels:
            break

    return ids


# ---------- per-level download + filter ----------


def _passes_filters(
    level: gd.Level,
    level_string: str,
    cfg: FetchConfig,
) -> tuple[bool, RejectionReason | None, str]:
    rating = _classify_rating(level)
    if rating is None:
        return False, RejectionReason.NOT_RATED, ""
    if rating not in cfg.ratings:
        return False, RejectionReason.NOT_RATED, f"tier {rating.value} not requested"

    if cfg.exclude_platformer and _is_platformer(level):
        return False, RejectionReason.PLATFORMER, ""

    object_count = int(getattr(level, "object_count", 0) or 0)
    if not (OBJECT_COUNT_MIN <= object_count <= OBJECT_COUNT_MAX):
        return False, RejectionReason.OBJECT_COUNT_OUT_OF_RANGE, f"n={object_count}"

    if not level_string or ";" not in level_string:
        return False, RejectionReason.EMPTY_LEVEL_STRING, ""

    game_version = int(getattr(level, "game_version", 0) or 0)
    if game_version and game_version < MIN_GAME_VERSION:
        return False, RejectionReason.GAME_VERSION_TOO_OLD, f"gv={game_version}"

    # Upload date filter (DATA_COLLECTION.md §3): gd.py exposes this as
    # `level.uploaded_at` (datetime) or `level.uploaded_timestamp`. Best-effort.
    uploaded = getattr(level, "uploaded_at", None) or getattr(level, "uploaded_timestamp", None)
    if uploaded is not None:
        try:
            year = uploaded.year if hasattr(uploaded, "year") else None
            if year is not None and year < MIN_UPLOAD_YEAR:
                return False, RejectionReason.GAME_VERSION_TOO_OLD, f"uploaded={year}"
        except Exception:  # noqa: BLE001 — defensive; gd.py field shape varies
            pass  # if we can't parse, let it through

    return True, None, ""


async def _download_and_save(
    client: gd.Client,
    level_id: int,
    cfg: FetchConfig,
    bucket: TokenBucket,
    streak: FailureStreak,
    stats: FetchStats,
) -> None:
    path = _level_path(cfg, level_id)
    if path.exists() and not cfg.force:
        stats.skipped_existing += 1
        return

    await bucket.acquire()
    try:
        level: gd.Level = await _with_backoff(
            client.get_level,
            level_id,
            streak=streak,
            label=f"get_level {level_id}",
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

    # gd.py exposes the decompressed level string on `.data`. See DATA_COLLECTION.md §2.1.
    level_string = getattr(level, "data", "") or ""

    ok, reject_reason, detail = _passes_filters(level, level_string, cfg)
    if not ok:
        stats.rejected += 1
        assert reject_reason is not None
        _append_rejection(
            cfg,
            RejectionEntry(level_id=level_id, reason=reject_reason, detail=detail),
        )
        return

    rating = _classify_rating(level)
    assert rating is not None

    creator_name = ""
    creator = getattr(level, "creator", None)
    if creator is not None:
        creator_name = getattr(creator, "name", "") or ""

    song_id = 0
    song = getattr(level, "song", None)
    if song is not None:
        song_id = int(getattr(song, "id", 0) or 0)

    raw = RawLevel(
        level_id=level_id,
        name=str(getattr(level, "name", "")),
        creator=creator_name,
        rating=rating,
        song_id=song_id,
        object_count=int(getattr(level, "object_count", 0) or 0),
        length=_normalize_length(level),
        platformer=_is_platformer(level),
        game_version=int(getattr(level, "game_version", 0) or 0),
        level_string_raw=level_string,
    )

    _write_raw(path, raw)
    _append_manifest(
        cfg,
        ManifestEntry(
            level_id=level_id,
            creator=creator_name,
            name=raw.name,
            rating=rating,
            object_count=raw.object_count,
            raw_hash=_sha256(level_string),
        ),
    )
    stats.fetched += 1
    stats.by_rating[rating.value] = stats.by_rating.get(rating.value, 0) + 1
    log.info("saved %d (%s, %d objs)", level_id, rating.value, raw.object_count)


# ---------- public entry point ----------


async def collect_raw(cfg: FetchConfig) -> FetchStats:
    cfg.output_dir.mkdir(parents=True, exist_ok=True)
    stats = FetchStats()
    bucket = TokenBucket(rate_per_sec=cfg.rate_per_sec)
    streak = FailureStreak()
    sem = asyncio.Semaphore(1)  # §4.2 — strictly sequential.

    client_kwargs: dict[str, Any] = {}
    # gd.py >= 1.0 accepts a user_agent kwarg; older builds don't. Probe.
    try:
        client = gd.Client(user_agent=USER_AGENT, **client_kwargs)  # type: ignore[call-arg]
    except TypeError:
        client = gd.Client(**client_kwargs)

    async with _maybe_context(client):
        level_ids = await _gather_level_ids(client, cfg, bucket, streak)
        if cfg.max_levels:
            level_ids = level_ids[: cfg.max_levels]
        log.info("discovered %d unique level ids", len(level_ids))

        for i, level_id in enumerate(level_ids):
            async with sem:
                await _download_and_save(client, level_id, cfg, bucket, streak, stats)
            if (i + 1) % 50 == 0:
                log.info(
                    "progress %d/%d (saved=%d skipped=%d rejected=%d err=%d)",
                    i + 1,
                    len(level_ids),
                    stats.fetched,
                    stats.skipped_existing,
                    stats.rejected,
                    stats.errors,
                )
    return stats


async def _gather_level_ids(
    client: gd.Client,
    cfg: FetchConfig,
    bucket: TokenBucket,
    streak: FailureStreak,
) -> list[int]:
    if cfg.from_manifest is not None:
        ids = _read_manifest_ids(cfg.from_manifest)
        log.info("using manifest %s → %d ids", cfg.from_manifest, len(ids))
        return ids

    collected: list[int] = []
    seen: set[int] = set()
    for rating in cfg.ratings:
        page_ids = await _search_level_ids(client, rating, cfg, bucket, streak)
        for i in page_ids:
            if i not in seen:
                seen.add(i)
                collected.append(i)
    return collected


class _NullAsyncContext:
    async def __aenter__(self) -> None:
        return None

    async def __aexit__(self, *_: Any) -> None:
        return None


def _maybe_context(client: gd.Client) -> Any:
    """Some gd.py versions are async-context-managers, some aren't."""
    if hasattr(client, "__aenter__"):
        return client
    return _NullAsyncContext()


def iter_raw_files(raw_dir: Path) -> Iterable[Path]:
    """Used by Stage 2 — but exposed here since listing the raw dir belongs to data layer."""
    return sorted(raw_dir.glob("*.json"))
