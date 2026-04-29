"""Stage 2.5 runner — load every `data/raw/{id}.json` into SQLite at
`data/gd.db`.

Idempotent: skips levels already present unless `DB_FORCE=True` in config.py.
Object kinds come from `data/object_ids.json` (dumped by the Geode mod's
"Dump IDs" button); rows where the id isn't in the dump get kind=UNKNOWN(0).
"""
from __future__ import annotations

import json
import logging
import sys

from gd_designer.data.config import (
    DB_COMMIT_EVERY,
    DB_FORCE,
    DB_PATH,
    LOG_VERBOSITY,
    OBJECT_IDS_JSON,
    RAW_DIR,
)
from gd_designer.data.db import has_level, level_count, object_count, open_db
from gd_designer.data.fetch import iter_raw_files
from gd_designer.data.parse import convert_level
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


def _load_kind_map() -> dict[int, int]:
    if not OBJECT_IDS_JSON.exists():
        log.warning(
            "%s missing — every object row will be kind=UNKNOWN(0). Click "
            "'Dump IDs' in the mod and rerun for proper classification.",
            OBJECT_IDS_JSON,
        )
        return {}
    data = json.loads(OBJECT_IDS_JSON.read_text(encoding="utf-8"))
    return {int(k): int(v["kind"]) for k, v in data.get("ids", {}).items()}


def main() -> int:
    _configure_logging(LOG_VERBOSITY)

    kind_map = _load_kind_map()
    log.info("kind_map entries: %d", len(kind_map))

    conn = open_db(DB_PATH)
    log.info(
        "db opened at %s (existing: %d levels, %d objects)",
        DB_PATH,
        level_count(conn),
        object_count(conn),
    )

    raw_files = list(iter_raw_files(RAW_DIR))
    log.info("raw files: %d", len(raw_files))

    inserted = skipped = errors = 0
    object_rows_total = 0

    for i, raw_path in enumerate(raw_files):
        try:
            level_id = int(raw_path.stem)
        except ValueError:
            continue

        if not DB_FORCE and has_level(conn, level_id):
            skipped += 1
            continue

        try:
            raw = RawLevel.model_validate_json(raw_path.read_text(encoding="utf-8"))
            parsed = convert_level(raw)
        except Exception as exc:
            log.error("parse failed for %s: %r", raw_path.name, exc)
            errors += 1
            continue

        try:
            conn.execute("DELETE FROM objects WHERE level_id = ?", (level_id,))
            conn.execute(
                """
                INSERT OR REPLACE INTO levels (
                    level_id, name, creator, rating, game_version, song_id,
                    length, platformer, object_count,
                    bbox_min_x, bbox_min_y, bbox_max_x, bbox_max_y,
                    fetched_at, raw_path
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    raw.level_id,
                    raw.name,
                    raw.creator,
                    raw.rating.value,
                    raw.game_version,
                    raw.song_id,
                    raw.length.value,
                    int(raw.platformer),
                    parsed.object_count,
                    parsed.bbox_min_x,
                    parsed.bbox_min_y,
                    parsed.bbox_max_x,
                    parsed.bbox_max_y,
                    raw.fetched_at.isoformat(),
                    f"raw/{raw_path.name}",
                ),
            )
            object_rows = [
                (
                    raw.level_id,
                    idx,
                    obj.object_id,
                    kind_map.get(obj.object_id, 0),
                    obj.x,
                    obj.y,
                    obj.rotation,
                    obj.scale,
                    obj.z_order,
                    obj.z_layer,
                    obj.color_channel,
                    obj.color_channel_2,
                    int(obj.flip_x),
                    int(obj.flip_y),
                )
                for idx, obj in enumerate(parsed.objects)
            ]
            conn.executemany(
                """
                INSERT INTO objects (
                    level_id, idx, object_id, kind,
                    x, y, rotation, scale,
                    z_order, z_layer,
                    color_channel, color_channel_2,
                    flip_x, flip_y
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                object_rows,
            )
            inserted += 1
            object_rows_total += len(object_rows)
        except Exception as exc:
            log.error("db insert failed for %d: %r", level_id, exc)
            errors += 1
            continue

        if (inserted + skipped) % DB_COMMIT_EVERY == 0:
            conn.commit()
            log.info(
                "progress %d/%d (inserted=%d skipped=%d errors=%d objects=%d)",
                i + 1,
                len(raw_files),
                inserted,
                skipped,
                errors,
                object_rows_total,
            )

    conn.commit()
    conn.close()
    print(
        f"done: inserted={inserted} skipped={skipped} errors={errors} "
        f"object_rows_added={object_rows_total}"
    )
    return 0 if errors == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
