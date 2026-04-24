#pragma once

// Contract version: 1.0 — see docs/INTERFACES.md §4
//
// NOTE on scope:
//   At runtime, the primary source of "is this gameplay or decoration?" and
//   "what kind of object is this?" is GD's own GameObjectType enum (see
//   gd/LayoutReader.cpp::kindFromType). This catalog complements it by:
//     1) naming specific IDs in a human-friendly way (debug/logs),
//     2) providing a fallback classification when GameObjectType is ambiguous
//        (e.g. Modifier, Special),
//     3) giving pure unit tests and the ML data pipeline (where no GD runtime
//        exists) a way to classify ids.
//
// So this file intentionally lists only a handful of well-known ids at Phase 1;
// it grows in lockstep with the ml Python mirror during Phase 2.

#include "Layout.hpp"

#include <cstdint>
#include <span>

namespace designer::core::ids {

struct Entry {
    int32_t gdId;
    ObjectKind kind;
    const char* name;
};

std::span<const Entry> catalog();

// Catalog-based lookups (pure, no GD runtime). Returns UNKNOWN for ids not in
// the catalog — callers that have access to a GameObject* should prefer that.
ObjectKind kindOf(int32_t gdId);
bool isGameplay(int32_t gdId);
bool isDecoration(int32_t gdId);

} // namespace designer::core::ids
