#pragma once

#include "action_base.hpp"

#include <memory>
#include <string>
#include <unordered_map>

namespace ipc::actions {

class ActionRegistry {
public:
    void add(std::unique_ptr<ActionHandler> handler);
    ActionHandler* find(const std::string& action);

private:
    std::unordered_map<std::string, std::unique_ptr<ActionHandler>> handlers_;
};

void register_client_actions(ActionRegistry& registry);
void register_server_actions(ActionRegistry& registry);

} // namespace ipc::actions
