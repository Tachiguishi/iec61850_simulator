#include "action_registry.hpp"

namespace ipc::actions {

void ActionRegistry::add(std::unique_ptr<ActionHandler> handler) {
    if (!handler) {
        return;
    }

    std::string action_name = "";
    switch(handler->name()) {
        case ActionMethod::ServerStart: action_name = "server.start"; break;
        case ActionMethod::ServerStop: action_name = "server.stop"; break;
        case ActionMethod::ServerRemove: action_name = "server.remove"; break;
        case ActionMethod::ServerLoadModel: action_name = "server.load_model"; break;
        case ActionMethod::ServerConfig: action_name = "server.config"; break;
        case ActionMethod::ServerWrite: action_name = "server.write"; break;
        case ActionMethod::ServerRead: action_name = "server.read"; break;
        case ActionMethod::ServerGetClients: action_name = "server.get_clients"; break;
        case ActionMethod::ServerListInstances: action_name = "server.list_instances"; break;
        case ActionMethod::ServerGetInterfaces: action_name = "server.get_interfaces"; break;
        case ActionMethod::ServerSetInterface: action_name = "server.set_interface"; break;
        case ActionMethod::ClientConnect: action_name = "client.connect"; break;
        case ActionMethod::ClientDisconnect: action_name = "client.disconnect"; break;
        case ActionMethod::ClientBrowse: action_name = "client.browse"; break;
        case ActionMethod::ClientRead: action_name = "client.read"; break;
        case ActionMethod::ClientReadBatch: action_name = "client.read_batch"; break;
        case ActionMethod::ClientWrite: action_name = "client.write"; break;
        case ActionMethod::ClientListInstances: action_name = "client.list_instances"; break;
        default:
            return; // Unknown action method, do not register
    }
    handlers_.emplace(action_name, std::move(handler));
}

ActionHandler* ActionRegistry::find(const std::string& action) {
    auto it = handlers_.find(action);
    if (it == handlers_.end()) {
        return nullptr;
    }
    return it->second.get();
}

} // namespace ipc::actions
