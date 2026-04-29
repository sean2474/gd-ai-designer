"""GD object key catalog.

Each object in a level is a comma-separated `k,v,k,v,...` list where keys are
small integers chosen by RobTop. These are the most commonly used ones; see
https://wyliemaster.github.io/gddocs/ for the full table.
"""

# core placement / identity
KEY_OBJECT_ID = "1"      # int — GD internal object ID (spike=8, block=1, etc.)
KEY_X = "2"              # float — world x
KEY_Y = "3"              # float — world y (up = +)
KEY_FLIP_X = "4"         # bool
KEY_FLIP_Y = "5"         # bool
KEY_ROTATION = "6"       # float degrees

# editor-only layers (don't affect gameplay)
KEY_EDITOR_LAYER = "20"   # int
KEY_EDITOR_LAYER_2 = "61"  # int

# color channels
KEY_COLOR_CHANNEL = "21"   # int — main color
KEY_COLOR_CHANNEL_2 = "22"  # int — detail color

# render ordering
KEY_Z_LAYER = "24"  # int — relative z layer (-4..+4 typically)
KEY_Z_ORDER = "25"  # int — finer z ordering within a layer

# transform
KEY_SCALE = "32"  # float — uniform scale

# groups (animations, triggers). Format: "1.2.3" pipe-separated ints as string.
KEY_GROUP_IDS = "57"

# known keys union — used by parse.py to separate typed fields from `extra`.
KNOWN_KEYS: frozenset[str] = frozenset(
    {
        KEY_OBJECT_ID,
        KEY_X,
        KEY_Y,
        KEY_FLIP_X,
        KEY_FLIP_Y,
        KEY_ROTATION,
        KEY_EDITOR_LAYER,
        KEY_EDITOR_LAYER_2,
        KEY_COLOR_CHANNEL,
        KEY_COLOR_CHANNEL_2,
        KEY_Z_LAYER,
        KEY_Z_ORDER,
        KEY_SCALE,
        KEY_GROUP_IDS,
    }
)
