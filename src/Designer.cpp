#include "Designer.hpp"
#include <Geode/Geode.hpp>
#include <Geode/binding/LevelEditorLayer.hpp>
#include <Geode/binding/GameObject.hpp>

using namespace geode::prelude;

namespace designer {

namespace ids {
	constexpr int BASIC_BLOCK       = 1;
	constexpr int SPIKE             = 8;
	constexpr int JUMP_PAD_YELLOW   = 35;
	constexpr int JUMP_RING_YELLOW  = 36;

	constexpr int DECO_BLOCK_PLAIN  = 211;
	constexpr int DECO_BLOCK_GRID   = 467;
	constexpr int DECO_SPIKE_SMALL  = 503;
}

constexpr float UNIT = 30.f;

static bool isGameplayObject(int id) {
	return id == ids::BASIC_BLOCK
		|| id == ids::SPIKE
		|| id == ids::JUMP_PAD_YELLOW
		|| id == ids::JUMP_RING_YELLOW;
}

std::vector<LayoutObject> readLayout(LevelEditorLayer* editor) {
	std::vector<LayoutObject> out;
	if (!editor || !editor->m_objects) return out;

	auto objects = editor->m_objects;
	for (int i = 0; i < objects->count(); ++i) {
		auto obj = static_cast<GameObject*>(objects->objectAtIndex(i));
		if (!obj) continue;
		if (!isGameplayObject(obj->m_objectID)) continue;

		out.push_back({
			.objectID = obj->m_objectID,
			.pos      = obj->getPosition(),
			.rotation = obj->getRotation(),
			.groupID  = 0,
		});
	}
	return out;
}

int applyDecorations(LevelEditorLayer* editor, const std::vector<DecorationOp>& ops) {
	if (!editor) return 0;
	int placed = 0;
	for (auto const& op : ops) {
		auto created = editor->createObject(op.objectID, op.pos, false);
		if (!created) continue;
		if (op.rotation != 0.f) created->setRotation(op.rotation);
		if (op.scale != 1.f)    created->setScale(op.scale);
		if (op.zOrder != 0)     created->setZOrder(op.zOrder);
		++placed;
	}
	return placed;
}

std::vector<DecorationOp> RuleBasedStrategy::design(const std::vector<LayoutObject>& layout) {
	std::vector<DecorationOp> ops;
	ops.reserve(layout.size());

	for (auto const& obj : layout) {
		switch (obj.objectID) {
			case ids::BASIC_BLOCK: {
				ops.push_back({
					.objectID = ids::DECO_BLOCK_GRID,
					.pos      = { obj.pos.x, obj.pos.y + UNIT },
					.zOrder   = -1,
				});
				break;
			}
			case ids::SPIKE: {
				ops.push_back({
					.objectID = ids::DECO_SPIKE_SMALL,
					.pos      = { obj.pos.x - UNIT * 0.5f, obj.pos.y },
					.scale    = 0.5f,
				});
				ops.push_back({
					.objectID = ids::DECO_SPIKE_SMALL,
					.pos      = { obj.pos.x + UNIT * 0.5f, obj.pos.y },
					.scale    = 0.5f,
				});
				break;
			}
			case ids::JUMP_PAD_YELLOW:
			case ids::JUMP_RING_YELLOW: {
				ops.push_back({
					.objectID = ids::DECO_BLOCK_PLAIN,
					.pos      = { obj.pos.x, obj.pos.y + UNIT * 2.f },
					.scale    = 0.75f,
					.zOrder   = -2,
				});
				break;
			}
		}
	}

	return ops;
}

} // namespace designer
