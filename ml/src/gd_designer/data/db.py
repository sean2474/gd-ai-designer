"""SQLite layer for the data pipeline.

Stage 2 output (parsed levels + per-object rows) lives here so the ML/training
side can run ad-hoc filters ("Spu7Nix levels", "spikes after y=200", etc.)
without rescanning thousands of JSON files.

Schema mirrors `mod/src/core/Layout.hpp` ObjectKind enum.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA_VERSION = "1.0"

# WAL mode lets readers run while a writer is in progress (we expect lots of
# ad-hoc query sessions concurrent with re-parses).
_PRAGMAS = """
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
"""

_SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_version (
    version TEXT PRIMARY KEY,
    applied_at TEXT NOT NULL DEFAULT (datetime('now'))
);
INSERT OR IGNORE INTO schema_version (version) VALUES ('1.0');

-- Coarse classification matching mod/src/core/Layout.hpp ObjectKind enum.
-- Convenience for human queries; objects.kind stores the integer.
CREATE TABLE IF NOT EXISTS kinds (
    id   INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE
);
INSERT OR IGNORE INTO kinds (id, name) VALUES
    (0,  'UNKNOWN'),
    (1,  'BLOCK_SOLID'),
    (2,  'BLOCK_HALF'),
    (3,  'SPIKE'),
    (4,  'ORB'),
    (5,  'PAD'),
    (6,  'PORTAL'),
    (7,  'SLOPE'),
    (8,  'DECORATION'),
    (9,  'TRIGGER_GAMEPLAY'),
    (10, 'TRIGGER_VISUAL'),
    (11, 'COLLECTIBLE'),
    (12, 'SPECIAL');

-- One row per crawled level.
CREATE TABLE IF NOT EXISTS levels (
    level_id        INTEGER PRIMARY KEY,
    name            TEXT NOT NULL,
    creator         TEXT NOT NULL,
    rating          TEXT NOT NULL,        -- featured | epic | legendary | mythic
    game_version    INTEGER NOT NULL,     -- 19/20/21/22 → 1.9/2.0/2.1/2.2
    song_id         INTEGER NOT NULL,
    length          TEXT NOT NULL,        -- tiny | short | medium | long | xl | platformer
    platformer      INTEGER NOT NULL,     -- 0/1
    object_count    INTEGER NOT NULL,     -- parsed-actual count (may differ from GDBrowser meta)
    bbox_min_x      REAL NOT NULL,
    bbox_min_y      REAL NOT NULL,
    bbox_max_x      REAL NOT NULL,
    bbox_max_y      REAL NOT NULL,
    fetched_at      TEXT NOT NULL,        -- ISO 8601
    raw_path        TEXT NOT NULL         -- relative path under data/raw/
);
CREATE INDEX IF NOT EXISTS idx_levels_creator ON levels(creator);
CREATE INDEX IF NOT EXISTS idx_levels_rating  ON levels(rating);
CREATE INDEX IF NOT EXISTS idx_levels_gv      ON levels(game_version);
CREATE INDEX IF NOT EXISTS idx_levels_objc    ON levels(object_count);

-- One row per object inside a level. PRIMARY KEY (level_id, idx) preserves
-- the order objects appeared in the source level string.
CREATE TABLE IF NOT EXISTS objects (
    level_id        INTEGER NOT NULL,
    idx             INTEGER NOT NULL,
    object_id       INTEGER NOT NULL,
    kind            INTEGER NOT NULL,
    x               REAL    NOT NULL,
    y               REAL    NOT NULL,
    rotation        REAL    NOT NULL,
    scale           REAL    NOT NULL,
    z_order         INTEGER NOT NULL,
    z_layer         INTEGER NOT NULL,
    color_channel   INTEGER NOT NULL,
    color_channel_2 INTEGER NOT NULL,
    flip_x          INTEGER NOT NULL,
    flip_y          INTEGER NOT NULL,
    PRIMARY KEY (level_id, idx),
    FOREIGN KEY (level_id) REFERENCES levels(level_id) ON DELETE CASCADE
);
-- Query axes: "objects in this level by x", "all spikes", "all of obj_id 1220".
CREATE INDEX IF NOT EXISTS idx_obj_level_x   ON objects(level_id, x);
CREATE INDEX IF NOT EXISTS idx_obj_kind      ON objects(kind);
CREATE INDEX IF NOT EXISTS idx_obj_object_id ON objects(object_id);
CREATE INDEX IF NOT EXISTS idx_obj_kind_x    ON objects(kind, x);
"""


def open_db(path: Path) -> sqlite3.Connection:
    """Create or open the SQLite database, applying schema + pragmas."""
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.executescript(_PRAGMAS)
    conn.executescript(_SCHEMA)
    return conn


def has_level(conn: sqlite3.Connection, level_id: int) -> bool:
    cur = conn.execute("SELECT 1 FROM levels WHERE level_id = ?", (level_id,))
    return cur.fetchone() is not None


def level_count(conn: sqlite3.Connection) -> int:
    cur = conn.execute("SELECT COUNT(*) FROM levels")
    return int(cur.fetchone()[0])


def object_count(conn: sqlite3.Connection) -> int:
    cur = conn.execute("SELECT COUNT(*) FROM objects")
    return int(cur.fetchone()[0])
