#include "action_base.hpp"
#include "action_registry.hpp"
#include "action_handle.hpp"

#include "../logger.hpp"
#include "../msgpack_codec.hpp"
#include "../network_config.hpp"

#include <iec61850_dynamic_model.h>

#include <algorithm>
#include <chrono>
#include <cstring>
#include <ctime>
#include <mutex>
#include <string>

#include <log4cplus/loggingmacros.h>

namespace {

std::string now_iso() {
    auto now = std::chrono::system_clock::now();
    std::time_t tt = std::chrono::system_clock::to_time_t(now);
    std::tm tm{};
    gmtime_r(&tt, &tm);
    char buffer[32] = {0};
    std::strftime(buffer, sizeof(buffer), "%Y-%m-%dT%H:%M:%SZ", &tm);
    return buffer;
}

void on_connection_event(IedServer, ClientConnection connection, bool connected, void* param) {
    auto* ctx = static_cast<ServerInstanceContext*>(param);

    std::string peer = ClientConnection_getPeerAddress(connection) ? ClientConnection_getPeerAddress(connection) : "unknown";
    std::string id = peer;
    if (connected) {
        ctx->clients.push_back({id, now_iso()});
    } else {
        ctx->clients.erase(
            std::remove_if(ctx->clients.begin(), ctx->clients.end(),
                           [&](const ClientInfo& info) { return info.id == id; }),
            ctx->clients.end());
    }
}

nlohmann::json attribute_value_json(IedServer server, DataAttribute* da) {
    nlohmann::json result = {
        {"value", nullptr},
        {"quality", 0},
        {"timestamp", nullptr},
    };

    if (!da) {
        return result;
    }

    DataAttributeType type = DataAttribute_getType(da);
    switch (type) {
        case IEC61850_BOOLEAN:
            result["value"] = IedServer_getBooleanAttributeValue(server, da);
            break;
        case IEC61850_INT8:
        case IEC61850_INT16:
        case IEC61850_INT32:
        case IEC61850_ENUMERATED:
            result["value"] = IedServer_getInt32AttributeValue(server, da);
            break;
        case IEC61850_INT64:
            result["value"] = IedServer_getInt64AttributeValue(server, da);
            break;
        case IEC61850_INT8U:
        case IEC61850_INT16U:
        case IEC61850_INT32U:
            result["value"] = IedServer_getUInt32AttributeValue(server, da);
            break;
        case IEC61850_FLOAT32:
            result["value"] = IedServer_getFloatAttributeValue(server, da);
            break;
        case IEC61850_FLOAT64:
            result["value"] = static_cast<double>(IedServer_getFloatAttributeValue(server, da));
            break;
        case IEC61850_VISIBLE_STRING_32:
        case IEC61850_VISIBLE_STRING_64:
        case IEC61850_VISIBLE_STRING_129:
        case IEC61850_VISIBLE_STRING_255:
        case IEC61850_UNICODE_STRING_255: {
            const char* str = IedServer_getStringAttributeValue(server, da);
            result["value"] = str ? str : "";
            break;
        }
        default:
            break;
    }
    return result;
}

void update_attribute_value(IedServer server, DataAttribute* da, const nlohmann::json& value_obj) {
    if (!da || !server) {
        return;
    }
    DataAttributeType type = DataAttribute_getType(da);
    switch (type) {
        case IEC61850_BOOLEAN:
            IedServer_updateBooleanAttributeValue(server, da, ipc::codec::as_bool(value_obj));
            break;
        case IEC61850_INT8:
        case IEC61850_INT16:
        case IEC61850_INT32:
        case IEC61850_ENUMERATED:
            IedServer_updateInt32AttributeValue(server, da, static_cast<int32_t>(ipc::codec::as_int64(value_obj)));
            break;
        case IEC61850_INT64:
            IedServer_updateInt64AttributeValue(server, da, static_cast<int64_t>(ipc::codec::as_int64(value_obj)));
            break;
        case IEC61850_INT8U:
        case IEC61850_INT16U:
        case IEC61850_INT32U:
            IedServer_updateUnsignedAttributeValue(server, da, static_cast<uint32_t>(ipc::codec::as_int64(value_obj)));
            break;
        case IEC61850_FLOAT32:
            IedServer_updateFloatAttributeValue(server, da, static_cast<float>(ipc::codec::as_double(value_obj)));
            break;
        case IEC61850_FLOAT64:
            IedServer_updateFloatAttributeValue(server, da, static_cast<float>(ipc::codec::as_double(value_obj)));
            break;
        case IEC61850_VISIBLE_STRING_32:
        case IEC61850_VISIBLE_STRING_64:
        case IEC61850_VISIBLE_STRING_129:
        case IEC61850_VISIBLE_STRING_255:
        case IEC61850_UNICODE_STRING_255: {
            std::string value = ipc::codec::as_string(value_obj, "");
            char* str_copy = strdup(value.c_str());
            if (str_copy) {
                IedServer_updateVisibleStringAttributeValue(server, da, str_copy);
                free(str_copy);
            } else {
                LOG4CPLUS_ERROR(server_logger(), "Failed to allocate string memory for update");
            }
            break;
        }
        default:
            break;
    }
}

} // namespace

namespace ipc::actions {

class ServerStartAction final : public ActionHandler {
public:
    const char* name() const override { return "server.start"; }

    bool handle(ActionContext& ctx, nlohmann::json& response) override {
        if (!ensure_payload_map(ctx, response)) {
            return true;
        }

        std::lock_guard<std::mutex> lock(ctx.context.mutex);

        bool error_occurred = false;
        std::string instance_id = validate_and_extract_instance_id(ctx.payload, ctx.action, response, error_occurred);
        if (error_occurred) {
            return true;
        }

        LOG4CPLUS_INFO(server_logger(), "server.start requested for instance " << instance_id);

        auto* inst = ctx.context.get_server_instance(instance_id);
        if (!inst || !inst->model) {
            LOG4CPLUS_ERROR(server_logger(), "server.start: server not initialized for instance " << instance_id);
            pack_error_response(response, "Server not initialized. Call server.load_model first");
            return true;
        }

        if (!inst->config) {
            inst->config = IedServerConfig_create();
        }

        if (!inst->server) {
            inst->server = IedServer_createWithConfig(inst->model, nullptr, inst->config);
            IedServer_setConnectionIndicationHandler(inst->server, on_connection_event, inst);
            if (inst->ip_address != "0.0.0.0") {
                IedServer_setLocalIpAddress(inst->server, inst->ip_address.c_str());
            }
        }

        if (inst->running) {
            IedServer_stop(inst->server);
            inst->running = false;
        }

        int port = inst->port;
        std::string ip_address = inst->ip_address;

        auto config_obj = ipc::codec::find_key(ctx.payload, "config");
        if (config_obj && config_obj->is_object()) {
            if (auto port_obj = ipc::codec::find_key(*config_obj, "port")) {
                port = static_cast<int>(ipc::codec::as_int64(*port_obj, inst->port));
                inst->port = port;
            }
            if (auto ip_obj = ipc::codec::find_key(*config_obj, "ip_address")) {
                ip_address = ipc::codec::as_string(*ip_obj, inst->ip_address);
                if (ip_address != "0.0.0.0") {
                    IedServer_setLocalIpAddress(inst->server, ip_address.c_str());
                    inst->ip_address = ip_address;
                }
            }
        }

        if (network::should_configure_ip(ip_address) && !ctx.context.global_interface_name.empty()) {
            if (network::add_ip_address(ctx.context.global_interface_name, ip_address, ctx.context.global_prefix_len)) {
                inst->ip_configured = true;
                LOG4CPLUS_INFO(server_logger(), "Configured IP " << ip_address << " on " << ctx.context.global_interface_name);
            } else {
                LOG4CPLUS_WARN(server_logger(), "Failed to configure IP " << ip_address << " on " << ctx.context.global_interface_name);
            }
        } else {
            LOG4CPLUS_INFO(server_logger(), "Using IP " << ip_address << " without additional configuration");
        }

        LOG4CPLUS_INFO(server_logger(), "Starting server instance " << instance_id << " on " << ip_address << ":" << port);
        IedServer_start(inst->server, port);
        inst->running = IedServer_isRunning(inst->server);

        LOG4CPLUS_INFO(server_logger(), "Server instance " << instance_id << " started on " << ip_address << ":" << port << " with state " << (inst->running ? "RUNNING" : "FAILED"));

        response["result"] = {
            {"success", inst->running},
            {"instance_id", instance_id},
        };
        response["error"] = nullptr;
        return true;
    }
};

class ServerStopAction final : public ActionHandler {
public:
    const char* name() const override { return "server.stop"; }

    bool handle(ActionContext& ctx, nlohmann::json& response) override {
        if (!ensure_payload_map(ctx, response)) {
            return true;
        }

        std::lock_guard<std::mutex> lock(ctx.context.mutex);

        bool error_occurred = false;
        std::string instance_id = validate_and_extract_instance_id(ctx.payload, ctx.action, response, error_occurred);
        if (error_occurred) {
            return true;
        }

        LOG4CPLUS_INFO(server_logger(), "server.stop requested for instance " << instance_id);

        auto* inst = ctx.context.get_server_instance(instance_id);
        if (inst && inst->server && inst->running) {
            IedServer_stop(inst->server);
            inst->running = false;
            LOG4CPLUS_INFO(server_logger(), "Server instance " << instance_id << " stopped");
        }

        response["result"] = ipc::codec::make_success_payload();
        response["error"] = nullptr;
        return true;
    }
};

class ServerRemoveAction final : public ActionHandler {
public:
    const char* name() const override { return "server.remove"; }

    bool handle(ActionContext& ctx, nlohmann::json& response) override {
        if (!ensure_payload_map(ctx, response)) {
            return true;
        }

        std::lock_guard<std::mutex> lock(ctx.context.mutex);

        bool error_occurred = false;
        std::string instance_id = validate_and_extract_instance_id(ctx.payload, ctx.action, response, error_occurred);
        if (error_occurred) {
            return true;
        }

        LOG4CPLUS_INFO(server_logger(), "server.remove requested for instance " << instance_id);

        auto* inst = ctx.context.get_server_instance(instance_id);
        if (inst) {
            if (inst->ip_configured && !ctx.context.global_interface_name.empty()) {
                network::remove_ip_address(ctx.context.global_interface_name, inst->ip_address, ctx.context.global_prefix_len);
                inst->ip_configured = false;
                LOG4CPLUS_INFO(server_logger(), "Cleaned up IP " << inst->ip_address << " from " << ctx.context.global_interface_name);
            }

            if (inst->server) {
                if (inst->running) {
                    IedServer_stop(inst->server);
                    inst->running = false;
                }
                IedServer_destroy(inst->server);
                inst->server = nullptr;
            }
            if (inst->config) {
                IedServerConfig_destroy(inst->config);
                inst->config = nullptr;
            }
            if (inst->model) {
                IedModel_destroy(inst->model);
                inst->model = nullptr;
            }
            inst->clients.clear();
            ctx.context.remove_server_instance(instance_id);
            LOG4CPLUS_INFO(server_logger(), "Server instance " << instance_id << " removed");
        }

        response["result"] = ipc::codec::make_success_payload();
        response["error"] = nullptr;
        return true;
    }
};

class ServerSetDataValueAction final : public ActionHandler {
public:
    const char* name() const override { return "server.set_data_value"; }

    bool handle(ActionContext& ctx, nlohmann::json& response) override {
        if (!ensure_payload_map(ctx, response)) {
            return true;
        }

        std::lock_guard<std::mutex> lock(ctx.context.mutex);

        bool error_occurred = false;
        std::string instance_id = validate_and_extract_instance_id(ctx.payload, ctx.action, response, error_occurred);
        if (error_occurred) {
            return true;
        }

        auto ref_obj = ipc::codec::find_key(ctx.payload, "reference");
        auto value_obj = ipc::codec::find_key(ctx.payload, "value");

        auto* inst = ctx.context.get_server_instance(instance_id);
        if (!inst || !inst->server || !inst->model || !ref_obj || !value_obj) {
            LOG4CPLUS_ERROR(server_logger(), "server.set_data_value invalid request for instance " << instance_id);
            pack_error_response(response, "Invalid request: missing server, model, reference, or value");
            return true;
        }

        std::string reference = ipc::codec::as_string(*ref_obj, "");
        LOG4CPLUS_DEBUG(server_logger(), "Update value: " << reference);
        ModelNode* node = IedModel_getModelNodeByObjectReference(inst->model, reference.c_str());
        if (node && ModelNode_getType(node) == DataAttributeModelType) {
            auto* da = reinterpret_cast<DataAttribute*>(node);
            IedServer_lockDataModel(inst->server);
            update_attribute_value(inst->server, da, *value_obj);
            IedServer_unlockDataModel(inst->server);
        }

        response["result"] = ipc::codec::make_success_payload();
        response["error"] = nullptr;
        return true;
    }
};

class ServerGetValuesAction final : public ActionHandler {
public:
    const char* name() const override { return "server.get_values"; }

    bool handle(ActionContext& ctx, nlohmann::json& response) override {
        if (!ensure_payload_map(ctx, response)) {
            return true;
        }

        std::lock_guard<std::mutex> lock(ctx.context.mutex);

        bool error_occurred = false;
        std::string instance_id = validate_and_extract_instance_id(ctx.payload, ctx.action, response, error_occurred);
        if (error_occurred) {
            return true;
        }

        auto refs_obj = ipc::codec::find_key(ctx.payload, "references");

        auto* inst = ctx.context.get_server_instance(instance_id);
        if (!inst || !inst->server || !inst->model || !refs_obj || !refs_obj->is_array()) {
            LOG4CPLUS_ERROR(server_logger(), "server.get_values invalid request for instance " << instance_id);
            pack_error_response(response, "Invalid request: missing server, model, or references array");
            return true;
        }

        nlohmann::json values = nlohmann::json::object();
        for (const auto& ref_item : *refs_obj) {
            std::string reference = ipc::codec::as_string(ref_item, "");
            ModelNode* node = IedModel_getModelNodeByObjectReference(inst->model, reference.c_str());
            if (node && ModelNode_getType(node) == DataAttributeModelType) {
                values[reference] = attribute_value_json(inst->server, reinterpret_cast<DataAttribute*>(node));
            } else {
                values[reference] = {
                    {"value", nullptr},
                    {"quality", 0},
                    {"timestamp", nullptr},
                };
            }
        }

        response["result"] = {{"values", values}};
        response["error"] = nullptr;
        return true;
    }
};

class ServerGetClientsAction final : public ActionHandler {
public:
    const char* name() const override { return "server.get_clients"; }

    bool handle(ActionContext& ctx, nlohmann::json& response) override {
        if (!ensure_payload_map(ctx, response)) {
            return true;
        }

        std::lock_guard<std::mutex> lock(ctx.context.mutex);

        bool error_occurred = false;
        std::string instance_id = validate_and_extract_instance_id(ctx.payload, ctx.action, response, error_occurred);
        if (error_occurred) {
            return true;
        }

        LOG4CPLUS_DEBUG(server_logger(), "server.get_clients requested for instance " << instance_id);

        auto* inst = ctx.context.get_server_instance(instance_id);
        nlohmann::json clients = nlohmann::json::array();
        if (inst) {
            for (const auto& client : inst->clients) {
                clients.push_back({
                    {"id", client.id},
                    {"connected_at", client.connected_at},
                });
            }
        }

        response["result"] = {{"clients", clients}};
        response["error"] = nullptr;
        return true;
    }
};

class ServerListInstancesAction final : public ActionHandler {
public:
    const char* name() const override { return "server.list_instances"; }

    bool handle(ActionContext& ctx, nlohmann::json& response) override {
        if (!ensure_payload_map(ctx, response)) {
            return true;
        }

        std::lock_guard<std::mutex> lock(ctx.context.mutex);
        LOG4CPLUS_DEBUG(server_logger(), "server.list_instances requested");

        nlohmann::json instances = nlohmann::json::array();
        for (const auto& entry : ctx.context.server_instances) {
            const auto& id = entry.first;
            const auto& inst = entry.second;
            instances.push_back({
                {"instance_id", id},
                {"state", inst->running ? "RUNNING" : "STOPPED"},
                {"port", inst->port},
                {"ied_name", inst->ied_name},
            });
        }

        response["result"] = {{"instances", instances}};
        response["error"] = nullptr;
        return true;
    }
};

class ServerGetInterfacesAction final : public ActionHandler {
public:
    const char* name() const override { return "server.get_interfaces"; }

    bool handle(ActionContext& ctx, nlohmann::json& response) override {
        if (!ensure_payload_map(ctx, response)) {
            return true;
        }

        std::lock_guard<std::mutex> lock(ctx.context.mutex);
        LOG4CPLUS_INFO(server_logger(), "server.get_interfaces requested");

        auto interfaces = network::get_network_interfaces();

        nlohmann::json iface_array = nlohmann::json::array();
        for (const auto& iface : interfaces) {
            iface_array.push_back({
                {"name", iface.name},
                {"description", iface.description},
                {"is_up", iface.is_up},
                {"addresses", iface.addresses},
            });
        }

        nlohmann::json current_interface = nullptr;
        if (!ctx.context.global_interface_name.empty()) {
            current_interface = {
                {"name", ctx.context.global_interface_name},
                {"prefix_len", ctx.context.global_prefix_len},
            };
        }

        response["result"] = {
            {"interfaces", iface_array},
            {"current_interface", current_interface},
        };
        response["error"] = nullptr;
        return true;
    }
};

class ServerSetInterfaceAction final : public ActionHandler {
public:
    const char* name() const override { return "server.set_interface"; }

    bool handle(ActionContext& ctx, nlohmann::json& response) override {
        if (!ensure_payload_map(ctx, response)) {
            return true;
        }

        std::lock_guard<std::mutex> lock(ctx.context.mutex);
        LOG4CPLUS_INFO(server_logger(), "server.set_interface requested");

        auto iface_obj = ipc::codec::find_key(ctx.payload, "interface_name");
        if (!iface_obj) {
            LOG4CPLUS_ERROR(server_logger(), "server.set_interface: interface_name is required");
            pack_error_response(response, "interface_name is required");
            return true;
        }

        std::string interface_name = ipc::codec::as_string(*iface_obj, "");
        int prefix_len = 24;

        if (auto prefix_obj = ipc::codec::find_key(ctx.payload, "prefix_len")) {
            prefix_len = static_cast<int>(ipc::codec::as_int64(*prefix_obj, 24));
        }

        network::remove_by_label(ctx.context.global_interface_name);

        ctx.context.global_interface_name = interface_name;
        ctx.context.global_prefix_len = prefix_len;

        LOG4CPLUS_INFO(server_logger(), "Global interface set to: " << interface_name << " (prefix_len: " << prefix_len << ")");

        response["result"] = {
            {"interface_name", interface_name},
            {"prefix_len", prefix_len},
        };
        response["error"] = nullptr;
        return true;
    }
};

void register_server_actions(ActionRegistry& registry) {
    registry.add(std::make_unique<ServerStartAction>());
    registry.add(std::make_unique<ServerStopAction>());
    registry.add(std::make_unique<ServerRemoveAction>());
    registry.add(std::make_unique<ServerLoadModelAction>());
    registry.add(std::make_unique<ServerSetDataValueAction>());
    registry.add(std::make_unique<ServerGetValuesAction>());
    registry.add(std::make_unique<ServerGetClientsAction>());
    registry.add(std::make_unique<ServerListInstancesAction>());
    registry.add(std::make_unique<ServerGetInterfacesAction>());
    registry.add(std::make_unique<ServerSetInterfaceAction>());
}

} // namespace ipc::actions
