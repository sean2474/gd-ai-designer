#pragma once

// Contract version: 1.0 — see docs/INTERFACES.md §1

#include <cstdint>
#include <string>
#include <vector>

namespace designer::core {

enum class ObjectKind : uint8_t {
    UNKNOWN     = 0,
    BLOCK_SOLID = 1,
    BLOCK_HALF  = 2,
    SPIKE       = 3,
    ORB         = 4,
    PAD         = 5,
    PORTAL      = 6,
    SLOPE       = 7,
    DECORATION  = 8,
};

struct LayoutObject {
    int32_t gameObjectId = 0;
    float x = 0.f;
    float y = 0.f;
    float rotation = 0.f;
    ObjectKind kind = ObjectKind::UNKNOWN;
};

struct Layout {
    std::vector<LayoutObject> objects;
    float minX = 0.f;
    float minY = 0.f;
    float maxX = 0.f;
    float maxY = 0.f;
    std::string metaJson;
};

} // namespace designer::core
