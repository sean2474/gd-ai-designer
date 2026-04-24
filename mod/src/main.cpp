// Entry translation unit.
//
// This file intentionally contains no logic. All editor hooks are registered
// through Geode's $modify macro in other translation units; see:
//   - src/ui/EditorButton.cpp  (EditorUI hook, Design button)
//
// Keep this file present: Geode's build expects at least one source unit that
// brings in <Geode/Geode.hpp>.

#include <Geode/Geode.hpp>
