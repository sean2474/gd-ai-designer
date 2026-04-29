#include "LayoutReader.hpp"

#include "../core/ObjectIDs.hpp"

#include <Geode/binding/GameObject.hpp>
#include <Geode/binding/LevelEditorLayer.hpp>

#include <algorithm>
#include <limits>

using namespace geode::prelude;

namespace designer::gd {

// Map GD's runtime-classified GameObjectType to our coarse ObjectKind.
// See $GEODE_SDK/bindings/<ver>/bindings/include/Geode/Enums.hpp for the full
// enum (47 values). We group them into the abstract kinds the designer cares
// about and keep UNKNOWN for the ones we haven't decided on yet (Modifier,
// Collectible, Special, etc.) — those still flow into Layout as "gameplay,
// kind=UNKNOWN" so the data is not lost.
core::ObjectKind kindFromType(GameObjectType t) {
    using Gt = GameObjectType;
    switch (t) {
        case Gt::Solid:
        case Gt::Breakable:
        case Gt::CollisionObject:
            return core::ObjectKind::BLOCK_SOLID;

        case Gt::Slope:
            return core::ObjectKind::SLOPE;

        case Gt::Hazard:
        case Gt::AnimatedHazard:
            return core::ObjectKind::SPIKE;

        case Gt::YellowJumpPad:
        case Gt::PinkJumpPad:
        case Gt::GravityPad:
        case Gt::RedJumpPad:
        case Gt::SpiderPad:
            return core::ObjectKind::PAD;

        case Gt::YellowJumpRing:
        case Gt::PinkJumpRing:
        case Gt::GravityRing:
        case Gt::GreenRing:
        case Gt::RedJumpRing:
        case Gt::CustomRing:
        case Gt::DashRing:
        case Gt::GravityDashRing:
        case Gt::SpiderOrb:
        case Gt::TeleportOrb:
        case Gt::DropRing:
            return core::ObjectKind::ORB;

        case Gt::InverseGravityPortal:
        case Gt::NormalGravityPortal:
        case Gt::ShipPortal:
        case Gt::CubePortal:
        case Gt::InverseMirrorPortal:
        case Gt::NormalMirrorPortal:
        case Gt::BallPortal:
        case Gt::RegularSizePortal:
        case Gt::MiniSizePortal:
        case Gt::UfoPortal:
        case Gt::DualPortal:
        case Gt::SoloPortal:
        case Gt::WavePortal:
        case Gt::RobotPortal:
        case Gt::TeleportPortal:
        case Gt::SpiderPortal:
        case Gt::SwingPortal:
        case Gt::GravityTogglePortal:
            return core::ObjectKind::PORTAL;

        case Gt::Decoration:
            return core::ObjectKind::DECORATION;

        default:
            return core::ObjectKind::UNKNOWN;
    }
}

core::ObjectKind classify(int32_t gdId, GameObjectType t) {
    // 1) Per-id catalog override beats GD's coarse type — this is how
    //    triggers split into TRIGGER_VISUAL vs TRIGGER_GAMEPLAY.
    auto override_kind = core::ids::kindOf(gdId);
    if (override_kind != core::ObjectKind::UNKNOWN) return override_kind;

    // 2) GD's GameObjectType when it's specific enough (Solid/Hazard/Portal/...).
    auto type_kind = kindFromType(t);
    if (type_kind != core::ObjectKind::UNKNOWN) return type_kind;

    // 3) Type-based fallback for the broad buckets GD lumps together.
    //    20/22 are trigger-ish in the dump; default to GAMEPLAY (safer to keep).
    //    30/31 are pickups; 40 is special interaction.
    const int ti = static_cast<int>(t);
    if (ti == 20 || ti == 22) return core::ObjectKind::TRIGGER_GAMEPLAY;
    if (ti == 30 || ti == 31) return core::ObjectKind::COLLECTIBLE;
    if (ti == 40)             return core::ObjectKind::SPECIAL;
    return core::ObjectKind::UNKNOWN;
}

core::Layout readLayout(LevelEditorLayer* editor) {
    core::Layout out;
    if (!editor || !editor->m_objects) return out;

    auto objects = editor->m_objects;
    const int n = objects->count();
    out.objects.reserve(static_cast<size_t>(n));

    float minX =  std::numeric_limits<float>::infinity();
    float minY =  std::numeric_limits<float>::infinity();
    float maxX = -std::numeric_limits<float>::infinity();
    float maxY = -std::numeric_limits<float>::infinity();

    for (int i = 0; i < n; ++i) {
        auto obj = static_cast<GameObject*>(objects->objectAtIndex(i));
        if (!obj) continue;

        // Runtime classification is the source of truth for gameplay-vs-deco.
        // ObjectIDs catalog is used only to name specific IDs and as a fallback
        // when m_objectType is ambiguous.
        if (obj->m_objectType == GameObjectType::Decoration) continue;

        const int32_t id = obj->m_objectID;
        core::ObjectKind kind = kindFromType(obj->m_objectType);
        if (kind == core::ObjectKind::UNKNOWN) {
            // Try the catalog as a secondary source so well-known ids still
            // get a non-UNKNOWN kind.
            auto catalogKind = core::ids::kindOf(id);
            if (catalogKind != core::ObjectKind::UNKNOWN &&
                catalogKind != core::ObjectKind::DECORATION) {
                kind = catalogKind;
            }
        }

        const auto pos = obj->getPosition();
        out.objects.push_back(core::LayoutObject{
            .gameObjectId = id,
            .x = pos.x,
            .y = pos.y,
            .rotation = obj->getRotation(),
            .kind = kind,
        });

        minX = std::min(minX, pos.x);
        minY = std::min(minY, pos.y);
        maxX = std::max(maxX, pos.x);
        maxY = std::max(maxY, pos.y);
    }

    if (!out.objects.empty()) {
        out.minX = minX;
        out.minY = minY;
        out.maxX = maxX;
        out.maxY = maxY;
    }
    return out;
}

} // namespace designer::gd
