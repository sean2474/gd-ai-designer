// $modify hook for the editor. Adds a "Design" button that runs the currently
// selected strategy over the level's gameplay layout.
//
// Placement: top-left of EditorUI. TODO: move into a proper editor panel in
// Phase 2 once DesignerPanel is introduced.

#include "../gd/DecorationApplier.hpp"
#include "../gd/LayoutReader.hpp"
#include "../strategies/RuleBasedStrategy.hpp"

#include <Geode/Geode.hpp>
#include <Geode/binding/LevelEditorLayer.hpp>
#include <Geode/modify/EditorUI.hpp>

#include <fmt/format.h>

using namespace geode::prelude;

class $modify(DesignerEditorUI, EditorUI) {
    bool init(LevelEditorLayer* editor) {
        if (!EditorUI::init(editor)) return false;

        auto sprite = ButtonSprite::create(
            "Design", "bigFont.fnt", "GJ_button_01.png", 0.6f);

        auto btn = CCMenuItemSpriteExtra::create(
            sprite,
            this,
            menu_selector(DesignerEditorUI::onDesign)
        );
        btn->setID("design-btn"_spr);

        auto menu = CCMenu::create();
        menu->setID("designer-menu"_spr);
        menu->addChild(btn);
        menu->setPosition({
            60.f,
            CCDirector::sharedDirector()->getWinSize().height - 30.f
        });
        this->addChild(menu, 100);

        return true;
    }

    void onDesign(CCObject*) {
        auto editor = LevelEditorLayer::get();
        if (!editor) {
            FLAlertLayer::create("Designer", "No editor instance.", "OK")->show();
            return;
        }

        auto layout = designer::gd::readLayout(editor);
        if (layout.objects.empty()) {
            FLAlertLayer::create(
                "Designer",
                "No gameplay objects found in the level.",
                "OK"
            )->show();
            return;
        }

        designer::strategies::RuleBasedStrategy strategy;
        auto result = strategy.design(layout);

        if (!result.error.empty()) {
            FLAlertLayer::create(
                "Designer",
                fmt::format("Strategy error: {}", result.error).c_str(),
                "OK"
            )->show();
            return;
        }

        int placed = designer::gd::applyDecorations(editor, result.ops);

        auto msg = fmt::format(
            "Read <cy>{}</c> gameplay objects.\nPlaced <cg>{}</c> decoration objects.",
            layout.objects.size(), placed
        );
        FLAlertLayer::create("Designer", msg, "OK")->show();

        log::info("Designer[{}]: layout={}, ops={}, placed={}",
            strategy.name(),
            layout.objects.size(),
            result.ops.size(),
            placed);
    }
};
