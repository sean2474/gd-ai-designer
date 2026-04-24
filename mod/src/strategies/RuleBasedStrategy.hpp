#pragma once

#include "../core/Strategy.hpp"

namespace designer::strategies {

class RuleBasedStrategy final : public core::IStrategy {
public:
    Result design(const core::Layout& input) override;
    std::string_view name() const override { return "rule_based"; }
};

} // namespace designer::strategies
