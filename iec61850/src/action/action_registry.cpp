#include "action_registry.hpp"

namespace ipc::actions {

void ActionRegistry::add(std::unique_ptr<ActionHandler> handler) {
    if (!handler) {
        return;
    }
    handlers_.emplace(handler->name(), std::move(handler));
}

ActionHandler* ActionRegistry::find(const std::string& action) {
    auto it = handlers_.find(action);
    if (it == handlers_.end()) {
        return nullptr;
    }
    return it->second.get();
}

} // namespace ipc::actions
