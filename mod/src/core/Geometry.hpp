#pragma once

// Minimal geometry types, independent of cocos2d. Use inside core/ instead of
// cocos2d::CCPoint so that core stays pure (see docs/CLAUDE.md layer table).

namespace designer::core {

struct Vec2 {
    float x = 0.f;
    float y = 0.f;
};

struct Rect {
    float minX = 0.f;
    float minY = 0.f;
    float maxX = 0.f;
    float maxY = 0.f;

    constexpr float width()  const { return maxX - minX; }
    constexpr float height() const { return maxY - minY; }
};

} // namespace designer::core
