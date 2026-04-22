#include "action.hpp"

#include "action_base.hpp"
#include "action_registry.hpp"
#include "logger.hpp"
#include "msgpack_codec.hpp"

#include <log4cplus/loggingmacros.h>

namespace ipc::actions {

namespace {

ActionRegistry& get_registry() {
    static ActionRegistry registry = [] {
        ActionRegistry reg;
        register_client_actions(reg);
        register_server_actions(reg);
        return reg;
    }();

    return registry;
}

} // namespace

bool ActionHandler::ensure_payload_map(const ActionContext& ctx, nlohmann::json& response) {
    if (ctx.payload.is_null()) {
        LOG4CPLUS_ERROR(server_logger(), ctx.action << " missing payload");
        pack_error_response(response, "Missing payload");
        return false;
    }
    return true;
}

void ActionHandler::pack_error_response(nlohmann::json& response, const std::string& error_msg) {
    response["result"] = nlohmann::json::object();
    response["error"] = ipc::codec::make_error(error_msg);
}

std::string ActionHandler::validate_and_extract_instance_id(
    const nlohmann::json& payload,
    const std::string& action,
    nlohmann::json& response,
    bool& error_occurred) {
    std::string instance_id = extract_instance_id(payload);
    if (instance_id.empty()) {
        LOG4CPLUS_ERROR(server_logger(), action << ": instance_id is required");
        pack_error_response(response, "instance_id is required");
        error_occurred = true;
        return "";
    }
    error_occurred = false;
    return instance_id;
}

std::string ActionHandler::extract_instance_id(const nlohmann::json& payload) {
    if (auto id_obj = ipc::codec::find_key(payload, "instance_id")) {
        std::string id = ipc::codec::as_string(*id_obj, "");
        if (!id.empty()) {
            return id;
        }
    }
    return "";
}

std::string handle_action(const std::string& request_bytes, BackendContext& context) {
    ipc::codec::Request request;
    nlohmann::json response = nlohmann::json::object();

    try {
        request = ipc::codec::decode_request(request_bytes);
    } catch (const std::exception& exc) {
        LOG4CPLUS_ERROR(core_logger(), "Decode error: " << exc.what());
        response["id"] = "";
        response["result"] = nlohmann::json::object();
        response["error"] = ipc::codec::make_error(std::string("Decode error: ") + exc.what());
        return ipc::codec::encode_response_bytes(response);
    }

    LOG4CPLUS_INFO(core_logger(), "IPC action: " << request.action << " id=" << request.id);

    response["id"] = request.id;
    ActionContext ctx{request.action, context, request.payload};
    ActionHandler* handler = get_registry().find(request.action);
    if (!handler) {
        LOG4CPLUS_WARN(core_logger(), "Unknown action: " << request.action);
        response["result"] = nlohmann::json::object();
        response["error"] = ipc::codec::make_error("Unknown action");
        return ipc::codec::encode_response_bytes(response);
    }

    handler->handle(ctx, response);
    return ipc::codec::encode_response_bytes(response);
}

} // namespace ipc::actions
