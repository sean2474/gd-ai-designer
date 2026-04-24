#pragma once

#include <Geode/Geode.hpp>

class LevelEditorLayer;
class GameObject;

namespace designer {

struct LayoutObject {
	int objectID;
	cocos2d::CCPoint pos;
	float rotation;
	int groupID;
};

struct DecorationOp {
	int objectID;
	cocos2d::CCPoint pos;
	float rotation = 0.f;
	float scale = 1.f;
	int zOrder = 0;
};

class Strategy {
public:
	virtual ~Strategy() = default;
	virtual std::vector<DecorationOp> design(const std::vector<LayoutObject>& layout) = 0;
};

class RuleBasedStrategy : public Strategy {
public:
	std::vector<DecorationOp> design(const std::vector<LayoutObject>& layout) override;
};

std::vector<LayoutObject> readLayout(LevelEditorLayer* editor);
int applyDecorations(LevelEditorLayer* editor, const std::vector<DecorationOp>& ops);

} // namespace designer
