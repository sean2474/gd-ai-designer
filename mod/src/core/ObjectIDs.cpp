#include "ObjectIDs.hpp"

#include <algorithm>
#include <array>

namespace designer::core::ids {

namespace {

// Phase 1 catalog. Only entries the current rule-based strategy references.
// Extend in lockstep with ml/src/gd_designer/data/object_ids.py (INTERFACES.md §4).
constexpr std::array<Entry, 7> kTable = {{
    {   1, ObjectKind::BLOCK_SOLID, "basic_block"       },
    {   8, ObjectKind::SPIKE,       "spike"             },
    {  35, ObjectKind::PAD,         "jump_pad_yellow"   },
    {  36, ObjectKind::ORB,         "jump_ring_yellow"  },
    { 211, ObjectKind::DECORATION,  "deco_block_plain"  },
    { 467, ObjectKind::DECORATION,  "deco_block_grid"   },
    { 503, ObjectKind::DECORATION,  "deco_spike_small"  },
}};

} // namespace

std::span<const Entry> catalog() {
    return { kTable.data(), kTable.size() };
}

ObjectKind kindOf(int32_t gdId) {
    auto it = std::find_if(kTable.begin(), kTable.end(),
        [gdId](const Entry& e) { return e.gdId == gdId; });
    return it == kTable.end() ? ObjectKind::UNKNOWN : it->kind;
}

bool isGameplay(int32_t gdId) {
    auto k = kindOf(gdId);
    return k != ObjectKind::UNKNOWN && k != ObjectKind::DECORATION;
}

bool isDecoration(int32_t gdId) {
    return kindOf(gdId) == ObjectKind::DECORATION;
}

} // namespace designer::core::ids
