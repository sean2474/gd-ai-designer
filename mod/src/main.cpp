#include <Geode/Geode.hpp>
#include <Geode/modify/EditorUI.hpp>
#include <Geode/binding/LevelEditorLayer.hpp>
#include "Designer.hpp"

using namespace geode::prelude;

class $modify(DesignerEditorUI, EditorUI) {
	bool init(LevelEditorLayer* editor) {
		if (!EditorUI::init(editor)) return false;

		auto sprite = ButtonSprite::create("Design", "bigFont.fnt", "GJ_button_01.png", 0.6f);
		auto btn = CCMenuItemSpriteExtra::create(
			sprite,
			this,
			menu_selector(DesignerEditorUI::onDesign)
		);
		btn->setID("design-btn"_spr);

		auto menu = CCMenu::create();
		menu->setID("designer-menu"_spr);
		menu->addChild(btn);
		menu->setPosition({ 60.f, CCDirector::sharedDirector()->getWinSize().height - 30.f });
		this->addChild(menu, 100);

		return true;
	}

	void onDesign(CCObject*) {
		auto editor = LevelEditorLayer::get();
		if (!editor) {
			FLAlertLayer::create("Designer", "No editor instance.", "OK")->show();
			return;
		}

		auto layout = designer::readLayout(editor);
		if (layout.empty()) {
			FLAlertLayer::create("Designer", "No gameplay objects found in the level.", "OK")->show();
			return;
		}

		designer::RuleBasedStrategy strategy;
		auto ops = strategy.design(layout);

		int placed = designer::applyDecorations(editor, ops);

		auto msg = fmt::format(
			"Read <cy>{}</c> gameplay objects.\nPlaced <cg>{}</c> decoration objects.",
			layout.size(), placed
		);
		FLAlertLayer::create("Designer", msg, "OK")->show();

		log::info("Designer: layout={}, ops={}, placed={}", layout.size(), ops.size(), placed);
	}
};
