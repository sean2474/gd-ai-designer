#pragma once

#include "../core/Layout.hpp"

class LevelEditorLayer;
enum class GameObjectType;

namespace designer::gd {

// Reads the editor's current gameplay objects into a pure core::Layout.
// Returns an empty Layout if editor is null or has no objects.
// Filters out anything not classified as gameplay by core::ids.
core::Layout readLayout(LevelEditorLayer* editor);

// Maps GD's runtime-classified GameObjectType to our coarse ObjectKind.
// Source of truth — dump tools (tools/DumpObjectIDs) reuse this.
core::ObjectKind kindFromType(GameObjectType t);

// Combined classifier: `core::ids::kindOf(id)` override first (e.g. mark a
// specific trigger as TRIGGER_VISUAL), then GD's GameObjectType, then a
// type-based fallback for triggers/collectibles/special that GD's enum is
// too coarse for. Use this anywhere outside readLayout.
core::ObjectKind classify(int32_t gdId, GameObjectType t);

} // namespace designer::gd
