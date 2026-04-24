#pragma once

#include "../core/DecorationOp.hpp"

#include <vector>

class LevelEditorLayer;

namespace designer::gd {

// Applies decoration ops to the editor. Returns the count actually placed.
// Gameplay-id ops are skipped with a warning (see INTERFACES.md §1.2).
// TODO(phase-2): wrap the whole batch into a single undo-stack entry so that
// Ctrl+Z reverts the entire Design action at once (INTERFACES.md §5).
int applyDecorations(LevelEditorLayer* editor,
                     const std::vector<core::DecorationOp>& ops);

} // namespace designer::gd
