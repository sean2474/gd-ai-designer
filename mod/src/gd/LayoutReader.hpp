#pragma once

#include "../core/Layout.hpp"

class LevelEditorLayer;

namespace designer::gd {

// Reads the editor's current gameplay objects into a pure core::Layout.
// Returns an empty Layout if editor is null or has no objects.
// Filters out anything not classified as gameplay by core::ids.
core::Layout readLayout(LevelEditorLayer* editor);

} // namespace designer::gd
