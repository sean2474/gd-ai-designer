// $modify hook for the editor. Adds a "Design" button that runs the currently
// selected strategy over the level's gameplay layout.
//
// Placement: top-left of EditorUI. TODO: move into a proper editor panel in
// Phase 2 once DesignerPanel is introduced.

#include "../gd/DecorationApplier.hpp"
#include "../gd/LayoutReader.hpp"
#include "../strategies/RuleBasedStrategy.hpp"
#include "../tools/DumpObjectIDs.hpp"

#include <Geode/Geode.hpp>
#include <Geode/binding/LevelEditorLayer.hpp>
#include <Geode/modify/EditorUI.hpp>

#include <fmt/format.h>

using namespace geode::prelude;

class $modify(DesignerEditorUI, EditorUI) {
    bool init(LevelEditorLayer* editor) {
        if (!EditorUI::init(editor)) return false;

        auto designSprite = ButtonSprite::create(
            "Design", "bigFont.fnt", "GJ_button_01.png", 0.6f);
        auto designBtn = CCMenuItemSpriteExtra::create(
            designSprite, this, menu_selector(DesignerEditorUI::onDesign));
        designBtn->setID("design-btn"_spr);

        auto dumpSprite = ButtonSprite::create(
            "Dump IDs", "bigFont.fnt", "GJ_button_04.png", 0.5f);
        auto dumpBtn = CCMenuItemSpriteExtra::create(
            dumpSprite, this, menu_selector(DesignerEditorUI::onDumpIDs));
        dumpBtn->setID("dump-ids-btn"_spr);
        dumpBtn->setPositionY(-30.f);

        auto menu = CCMenu::create();
        menu->setID("designer-menu"_spr);
        menu->addChild(designBtn);
        menu->addChild(dumpBtn);
        menu->setPosition({
            60.f,
            CCDirector::sharedDirector()->getWinSize().height - 30.f
        });
        this->addChild(menu, 100);

        return true;
    }

    void onDumpIDs(CCObject*) {
        auto editor = LevelEditorLayer::get();
        if (!editor) {
            FLAlertLayer::create("Dump IDs", "No editor instance.", "OK")->show();
            return;
        }
        // Hardcoded path so the ML pipeline picks it up directly. Dev tool.
        const std::filesystem::path out =
            "/Users/sean2474/Desktop/project/gd-design-ai/data/object_ids.json";
        const int n = designer::tools::dumpObjectIDsToJson(editor, out, 3000);
        log::info("DumpObjectIDs: wrote {} entries to {}", n, out.string());
        FLAlertLayer::create(
            "Dump IDs",
            fmt::format("Wrote <cy>{}</c> entries to\n<cg>{}</c>",
                        n, out.string()).c_str(),
            "OK"
        )->show();
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
