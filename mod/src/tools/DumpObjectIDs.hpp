#pragma once

// Dev tool: walk every GD object id, query its GameObjectType, write a JSON
// file the ML pipeline can use to classify (gameplay / decoration / ...).
//
// Lives in tools/ rather than core/ because it depends on GD runtime — the
// id → type table is hardcoded inside GD itself; only way to read it is to
// instantiate each object at runtime.

#include <filesystem>

class LevelEditorLayer;

namespace designer::tools {

// Iterates ids 1..max_id, calls `editor->createObject(id, off-screen pos)` for
// each, reads `m_objectType`, and writes JSON. Returns the number of entries
// successfully dumped.
int dumpObjectIDsToJson(LevelEditorLayer* editor, const std::filesystem::path& out, int maxId = 3000);

} // namespace designer::tools
