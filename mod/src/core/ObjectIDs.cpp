#include "ObjectIDs.hpp"

#include <algorithm>
#include <array>

namespace designer::core::ids {

namespace {

// ID-keyed overrides. Used as a fallback when GD's GameObjectType is too
// coarse — covers triggers (some visual-only, some affect gameplay),
// collectibles, and special interaction objects that GD's enum collapses
// into Modifier / Pickup / Special. Mirrors
// ml/src/gd_designer/data/object_ids_overrides.py (INTERFACES.md §4).
//
// Layout-vs-decoration policy (GD Creator School / community convention):
// - KEEP (TRIGGER_GAMEPLAY): camera (zoom/static/offset/rotate/mode/edit),
//   move/rotate/scale/follow/animate, spawn/toggle/stop/random/count/item/
//   pickup/collision/touch, gravity/teleport/reverse/mirror, time-warp,
//   hide/show player, GP options.
// - DROP (TRIGGER_VISUAL): color (BG/ground/line/obj/3DL/channel),
//   pulse/alpha/fade, shader/shake/glitch/chromatic/pixelate/hue,
//   gradient, BG/MG change, SFX/song.
//
// Default for an unmapped Modifier-ish trigger is TRIGGER_GAMEPLAY (keep —
// less destructive). Speed portals (200-203, 1334) are PORTAL, not triggers.
constexpr std::array<Entry, 43> kTable = {{
    // ---- TRIGGER_VISUAL — color (legacy 1.x-2.0 family) ----
    {   23, ObjectKind::TRIGGER_VISUAL,    "trigger_color_3dl_legacy" },
    {   24, ObjectKind::TRIGGER_VISUAL,    "trigger_color_obj_legacy" },
    {   25, ObjectKind::TRIGGER_VISUAL,    "trigger_color_p1_legacy" },
    {   26, ObjectKind::TRIGGER_VISUAL,    "trigger_color_p2_legacy" },
    {   27, ObjectKind::TRIGGER_VISUAL,    "trigger_color_line2_legacy" },
    {   28, ObjectKind::TRIGGER_VISUAL,    "trigger_pulse_28_legacy" },
    {   29, ObjectKind::TRIGGER_VISUAL,    "trigger_bg_color_legacy" },
    {   30, ObjectKind::TRIGGER_VISUAL,    "trigger_ground_color_legacy" },
    {  104, ObjectKind::TRIGGER_VISUAL,    "trigger_line_color_legacy" },
    {  105, ObjectKind::TRIGGER_VISUAL,    "trigger_obj_color_legacy" },
    {  899, ObjectKind::TRIGGER_VISUAL,    "trigger_color" },
    {  900, ObjectKind::TRIGGER_VISUAL,    "trigger_color_ext" },
    {  915, ObjectKind::TRIGGER_VISUAL,    "trigger_color_legacy_3dl" },

    // ---- TRIGGER_VISUAL — pulse / alpha / fade ----
    {  221, ObjectKind::TRIGGER_VISUAL,    "trigger_pulse_legacy" },
    {  744, ObjectKind::TRIGGER_VISUAL,    "trigger_pulse" },
    { 1006, ObjectKind::TRIGGER_VISUAL,    "trigger_pulse_obj" },
    { 1007, ObjectKind::TRIGGER_VISUAL,    "trigger_alpha" },
    { 1521, ObjectKind::TRIGGER_VISUAL,    "trigger_animate_visual" },

    // ---- TRIGGER_VISUAL — shaders / effects ----
    { 1817, ObjectKind::TRIGGER_VISUAL,    "trigger_shake" },
    { 1819, ObjectKind::TRIGGER_VISUAL,    "trigger_bg_effect_config" },
    { 1820, ObjectKind::TRIGGER_VISUAL,    "trigger_gradient" },
    { 2899, ObjectKind::TRIGGER_VISUAL,    "trigger_shader" },

    // ---- TRIGGER_GAMEPLAY (control flow, transforms, camera per GDCS) ----
    {   22, ObjectKind::TRIGGER_GAMEPLAY,  "trigger_touch_legacy" },
    {  901, ObjectKind::TRIGGER_GAMEPLAY,  "trigger_move" },
    { 1049, ObjectKind::TRIGGER_GAMEPLAY,  "trigger_toggle" },
    { 1268, ObjectKind::TRIGGER_GAMEPLAY,  "trigger_spawn" },
    { 1346, ObjectKind::TRIGGER_GAMEPLAY,  "trigger_rotate" },
    { 1347, ObjectKind::TRIGGER_GAMEPLAY,  "trigger_follow" },
    { 1520, ObjectKind::TRIGGER_GAMEPLAY,  "trigger_animate" },

    // ---- PORTAL — speed portals (Modifier-typed in 2.2 → would default to
    //                  trigger; force-classify as PORTAL since they alter
    //                  player physics on touch). ----
    {  200, ObjectKind::PORTAL,             "speed_slow" },
    {  201, ObjectKind::PORTAL,             "speed_normal" },
    {  202, ObjectKind::PORTAL,             "speed_fast" },
    {  203, ObjectKind::PORTAL,             "speed_faster" },
    { 1334, ObjectKind::PORTAL,             "speed_fastest" },

    // ---- COLLECTIBLE (type=30/31 from dump) ----
    { 1275, ObjectKind::COLLECTIBLE,        "pickup_item_small" },
    { 1329, ObjectKind::COLLECTIBLE,        "pickup_item_inverse" },
    { 1587, ObjectKind::COLLECTIBLE,        "secret_coin_silver" },
    { 1589, ObjectKind::COLLECTIBLE,        "secret_coin_gold" },
    { 1598, ObjectKind::COLLECTIBLE,        "key_gold" },
    { 1614, ObjectKind::COLLECTIBLE,        "key_silver" },

    // ---- SPECIAL (type=40 from dump) ----
    { 1755, ObjectKind::SPECIAL,            "boost_arrow" },
    { 1813, ObjectKind::SPECIAL,            "special_interact_1813" },
    { 1829, ObjectKind::SPECIAL,            "special_interact_1829" },
}};

} // namespace

std::span<const Entry> catalog() {
    return { kTable.data(), kTable.size() };
}

ObjectKind kindOf(int32_t gdId) {
    auto it = std::find_if(kTable.begin(), kTable.end(),
        [gdId](const Entry& e) { return e.gdId == gdId; });
    return it == kTable.end() ? ObjectKind::UNKNOWN : it->kind;
}

bool isGameplay(int32_t gdId) {
    auto k = kindOf(gdId);
    return k != ObjectKind::UNKNOWN
        && k != ObjectKind::DECORATION
        && k != ObjectKind::TRIGGER_VISUAL;
}

bool isDecoration(int32_t gdId) {
    auto k = kindOf(gdId);
    return k == ObjectKind::DECORATION || k == ObjectKind::TRIGGER_VISUAL;
}

} // namespace designer::core::ids
