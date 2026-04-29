#include "DumpObjectIDs.hpp"

#include "../gd/LayoutReader.hpp"

#include <Geode/Geode.hpp>
#include <Geode/binding/GameObject.hpp>

#include <fstream>

using namespace geode::prelude;

namespace designer::tools {

int dumpObjectIDsToJson(
    LevelEditorLayer* editor, const std::filesystem::path& out, int maxId
) {
    if (!editor) return 0;

    std::filesystem::create_directories(out.parent_path());
    std::ofstream f(out);
    if (!f) return 0;

    f << "{\n";
    f << "  \"schema_version\": \"1.0\",\n";
    f << "  \"source\": \"GD GameObject m_objectType, dumped via gd-design-ai mod\",\n";
    f << "  \"kind_enum\": {\n"
      << "    \"UNKNOWN\": 0,\n"
      << "    \"BLOCK_SOLID\": 1,\n"
      << "    \"BLOCK_HALF\": 2,\n"
      << "    \"SPIKE\": 3,\n"
      << "    \"ORB\": 4,\n"
      << "    \"PAD\": 5,\n"
      << "    \"PORTAL\": 6,\n"
      << "    \"SLOPE\": 7,\n"
      << "    \"DECORATION\": 8,\n"
      << "    \"TRIGGER_GAMEPLAY\": 9,\n"
      << "    \"TRIGGER_VISUAL\": 10,\n"
      << "    \"COLLECTIBLE\": 11,\n"
      << "    \"SPECIAL\": 12\n"
      << "  },\n";
    f << "  \"ids\": {\n";

    int written = 0;
    const auto offscreen = ccp(-1.0e6f, -1.0e6f);

    for (int id = 1; id <= maxId; ++id) {
        // LevelEditorLayer::createObject(int, CCPoint, bool noUndo) — passes
        // noUndo=true so we don't pollute the editor's undo stack with 3000
        // ephemeral entries during the sweep.
        GameObject* obj = editor->createObject(id, offscreen, true);
        if (!obj) continue;

        const auto type = static_cast<int>(obj->m_objectType);
        const auto kind = static_cast<int>(
            designer::gd::classify(id, obj->m_objectType));

        if (written > 0) f << ",\n";
        f << "    \"" << id << "\": {\"type\": " << type
          << ", \"kind\": " << kind << "}";
        ++written;

        // The object isn't tracked anywhere, but createObject likely added it
        // as a child of editor's batch nodes. Remove + release so we don't
        // accumulate garbage during the sweep.
        obj->removeFromParentAndCleanup(true);
    }

    f << "\n  }\n";
    f << "}\n";
    f.flush();

    return written;
}

} // namespace designer::tools
