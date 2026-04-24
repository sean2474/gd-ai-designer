#pragma once

// Contract version: 1.0 — see docs/INTERFACES.md §1

#include <cstdint>

namespace designer::core {

struct DecorationOp {
    int32_t gameObjectId = 0;
    float x = 0.f;
    float y = 0.f;
    float rotation = 0.f;
    int32_t zOrder = -1;
    int32_t colorChannel = 0;
    float scale = 1.f;
};

} // namespace designer::core
