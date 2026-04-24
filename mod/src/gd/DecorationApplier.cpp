#include "DecorationApplier.hpp"

#include "../core/ObjectIDs.hpp"

#include <Geode/binding/GameObject.hpp>
#include <Geode/binding/LevelEditorLayer.hpp>
#include <Geode/loader/Log.hpp>

#include <cocos2d.h>

using namespace geode::prelude;

namespace designer::gd {

int applyDecorations(LevelEditorLayer* editor,
                     const std::vector<core::DecorationOp>& ops) {
    if (!editor) return 0;

    int placed = 0;
    for (auto const& op : ops) {
        // Guard against mis-routed gameplay ids showing up as "decoration".
        if (core::ids::isGameplay(op.gameObjectId)) {
            log::warn("DecorationApplier: skipping gameplay id {}", op.gameObjectId);
            continue;
        }

        auto created = editor->createObject(op.gameObjectId,
                                            cocos2d::CCPoint{ op.x, op.y },
                                            false);
        if (!created) continue;

        if (op.rotation != 0.f) created->setRotation(op.rotation);
        if (op.scale    != 1.f) created->setScale(op.scale);
        if (op.zOrder   != 0)   created->setZOrder(op.zOrder);
        // colorChannel: TODO — wiring via GameObject color channels lands in Phase 2.
        ++placed;
    }
    return placed;
}

} // namespace designer::gd
