#include "RuleBasedStrategy.hpp"

namespace designer::strategies {

namespace {

constexpr float kUnit = 30.f; // GD grid unit (px)

// IDs this rule set reads from layout.
constexpr int32_t kIdBasicBlock      = 1;
constexpr int32_t kIdSpike           = 8;
constexpr int32_t kIdJumpPadYellow   = 35;
constexpr int32_t kIdJumpRingYellow  = 36;

// Decoration IDs this rule set emits.
constexpr int32_t kIdDecoBlockPlain  = 211;
constexpr int32_t kIdDecoBlockGrid   = 467;
constexpr int32_t kIdDecoSpikeSmall  = 503;

} // namespace

core::IStrategy::Result
RuleBasedStrategy::design(const core::Layout& input) {
    Result r;
    r.ops.reserve(input.objects.size());

    for (auto const& obj : input.objects) {
        switch (obj.gameObjectId) {
            case kIdBasicBlock:
                r.ops.push_back({
                    .gameObjectId = kIdDecoBlockGrid,
                    .x = obj.x,
                    .y = obj.y + kUnit,
                    .zOrder = -1,
                });
                break;

            case kIdSpike:
                r.ops.push_back({
                    .gameObjectId = kIdDecoSpikeSmall,
                    .x = obj.x - kUnit * 0.5f,
                    .y = obj.y,
                    .scale = 0.5f,
                });
                r.ops.push_back({
                    .gameObjectId = kIdDecoSpikeSmall,
                    .x = obj.x + kUnit * 0.5f,
                    .y = obj.y,
                    .scale = 0.5f,
                });
                break;

            case kIdJumpPadYellow:
            case kIdJumpRingYellow:
                r.ops.push_back({
                    .gameObjectId = kIdDecoBlockPlain,
                    .x = obj.x,
                    .y = obj.y + kUnit * 2.f,
                    .zOrder = -2,
                    .scale = 0.75f,
                });
                break;

            default:
                break;
        }
    }

    return r;
}

} // namespace designer::strategies
