#pragma once

// Contract version: 1.0 — see docs/INTERFACES.md §2

#include "DecorationOp.hpp"
#include "Layout.hpp"

#include <string>
#include <string_view>
#include <vector>

namespace designer::core {

class IStrategy {
public:
    struct Result {
        std::vector<DecorationOp> ops;
        std::string error; // empty → success
    };

    virtual ~IStrategy() = default;

    // Pure transform. Does not mutate `input`, does not throw.
    virtual Result design(const Layout& input) = 0;

    // Identifier for logs / UI.
    virtual std::string_view name() const = 0;
};

} // namespace designer::core
