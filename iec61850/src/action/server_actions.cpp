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

void pack_attribute_value(msgpack::packer<msgpack::sbuffer>& pk, IedServer server, DataAttribute* da) {
    if (!da) {
        pk.pack_map(3);
        pk.pack("value");
        pk.pack_nil();
        pk.pack("quality");
        pk.pack(0);
        pk.pack("timestamp");
        pk.pack_nil();
        return;
    }

    DataAttributeType type = DataAttribute_getType(da);

    pk.pack_map(3);
    pk.pack("value");
    switch (type) {
        case IEC61850_BOOLEAN:
            pk.pack(IedServer_getBooleanAttributeValue(server, da));
            break;
        case IEC61850_INT8:
        case IEC61850_INT16:
        case IEC61850_INT32:
        case IEC61850_ENUMERATED:
            pk.pack(IedServer_getInt32AttributeValue(server, da));
            break;
        case IEC61850_INT64:
            pk.pack(IedServer_getInt64AttributeValue(server, da));
            break;
        case IEC61850_INT8U:
        case IEC61850_INT16U:
        case IEC61850_INT32U:
            pk.pack(IedServer_getUInt32AttributeValue(server, da));
            break;
        case IEC61850_FLOAT32:
            pk.pack(IedServer_getFloatAttributeValue(server, da));
            break;
        case IEC61850_FLOAT64:
            pk.pack(static_cast<double>(IedServer_getFloatAttributeValue(server, da)));
            break;
        case IEC61850_VISIBLE_STRING_32:
        case IEC61850_VISIBLE_STRING_64:
        case IEC61850_VISIBLE_STRING_129:
        case IEC61850_VISIBLE_STRING_255:
        case IEC61850_UNICODE_STRING_255: {
            const char* str = IedServer_getStringAttributeValue(server, da);
            pk.pack(str ? str : "");
            break;
        }
        default:
            pk.pack_nil();
            break;
    }
    pk.pack("quality");
    pk.pack(0);
    pk.pack("timestamp");
    pk.pack_nil();
}

void update_attribute_value(IedServer server, DataAttribute* da, const msgpack::object& value_obj) {
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

    bool handle(ActionContext& ctx, msgpack::packer<msgpack::sbuffer>& pk) override {
        if (!ensure_payload_map(ctx, pk)) {
            return true;
        }

        std::lock_guard<std::mutex> lock(ctx.context.mutex);

        bool error_occurred = false;
        std::string instance_id = validate_and_extract_instance_id(ctx.payload, ctx.action, pk, error_occurred);
        if (error_occurred) {
            return true;
        }

        LOG4CPLUS_INFO(server_logger(), "server.start requested for instance " << instance_id);

        auto* inst = ctx.context.get_server_instance(instance_id);
        if (!inst || !inst->model) {
            LOG4CPLUS_ERROR(server_logger(), "server.start: server not initialized for instance " << instance_id);
            pack_error_response(pk, "Server not initialized. Call server.load_model first");
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
        if (config_obj && config_obj->type == msgpack::type::MAP) {
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
            std::string label = ctx.context.global_interface_name + ":iec" + instance_id;
            if (network::add_ip_address(ctx.context.global_interface_name, ip_address, ctx.context.global_prefix_len, label)) {
                inst->ip_configured = true;
                LOG4CPLUS_INFO(server_logger(), "Configured IP " << ip_address << " on " << ctx.context.global_interface_name);
            } else {
                LOG4CPLUS_WARN(server_logger(), "Failed to configure IP " << ip_address << " on " << ctx.context.global_interface_name);
            }
        }

        LOG4CPLUS_INFO(server_logger(), "Starting server instance " << instance_id << " on " << ip_address << ":" << port);
        IedServer_start(inst->server, port);
        inst->running = IedServer_isRunning(inst->server);

        LOG4CPLUS_INFO(server_logger(), "Server instance " << instance_id << " started on " << ip_address << ":" << port);

        pk.pack("payload");
        pk.pack_map(2);
        pk.pack("success");
        if (inst->running) {
            pk.pack(true);
        } else {
            pk.pack(false);
        }
        pk.pack("instance_id");
        pk.pack(instance_id);
        pk.pack("error");
        pk.pack_nil();
        return true;
    }
};

class ServerStopAction final : public ActionHandler {
public:
    const char* name() const override { return "server.stop"; }

    bool handle(ActionContext& ctx, msgpack::packer<msgpack::sbuffer>& pk) override {
        if (!ensure_payload_map(ctx, pk)) {
            return true;
        }

        std::lock_guard<std::mutex> lock(ctx.context.mutex);

        bool error_occurred = false;
        std::string instance_id = validate_and_extract_instance_id(ctx.payload, ctx.action, pk, error_occurred);
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

        pk.pack("payload");
        ipc::codec::pack_success_payload(pk);
        pk.pack("error");
        pk.pack_nil();
        return true;
    }
};

class ServerRemoveAction final : public ActionHandler {
public:
    const char* name() const override { return "server.remove"; }

    bool handle(ActionContext& ctx, msgpack::packer<msgpack::sbuffer>& pk) override {
        if (!ensure_payload_map(ctx, pk)) {
            return true;
        }

        std::lock_guard<std::mutex> lock(ctx.context.mutex);

        bool error_occurred = false;
        std::string instance_id = validate_and_extract_instance_id(ctx.payload, ctx.action, pk, error_occurred);
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

        pk.pack("payload");
        ipc::codec::pack_success_payload(pk);
        pk.pack("error");
        pk.pack_nil();
        return true;
    }
};

class ServerSetDataValueAction final : public ActionHandler {
public:
    const char* name() const override { return "server.set_data_value"; }

    bool handle(ActionContext& ctx, msgpack::packer<msgpack::sbuffer>& pk) override {
        if (!ensure_payload_map(ctx, pk)) {
            return true;
        }

        std::lock_guard<std::mutex> lock(ctx.context.mutex);

        bool error_occurred = false;
        std::string instance_id = validate_and_extract_instance_id(ctx.payload, ctx.action, pk, error_occurred);
        if (error_occurred) {
            return true;
        }

        auto ref_obj = ipc::codec::find_key(ctx.payload, "reference");
        auto value_obj = ipc::codec::find_key(ctx.payload, "value");

        auto* inst = ctx.context.get_server_instance(instance_id);
        if (!inst || !inst->server || !inst->model || !ref_obj || !value_obj) {
            LOG4CPLUS_ERROR(server_logger(), "server.set_data_value invalid request for instance " << instance_id);
            pack_error_response(pk, "Invalid request: missing server, model, reference, or value");
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

        pk.pack("payload");
        ipc::codec::pack_success_payload(pk);
        pk.pack("error");
        pk.pack_nil();
        return true;
    }
};

class ServerGetValuesAction final : public ActionHandler {
public:
    const char* name() const override { return "server.get_values"; }

    bool handle(ActionContext& ctx, msgpack::packer<msgpack::sbuffer>& pk) override {
        if (!ensure_payload_map(ctx, pk)) {
            return true;
        }

        std::lock_guard<std::mutex> lock(ctx.context.mutex);

        bool error_occurred = false;
        std::string instance_id = validate_and_extract_instance_id(ctx.payload, ctx.action, pk, error_occurred);
        if (error_occurred) {
            return true;
        }

        auto refs_obj = ipc::codec::find_key(ctx.payload, "references");

        auto* inst = ctx.context.get_server_instance(instance_id);
        if (!inst || !inst->server || !inst->model || !refs_obj || refs_obj->type != msgpack::type::ARRAY) {
            LOG4CPLUS_ERROR(server_logger(), "server.get_values invalid request for instance " << instance_id);
            pack_error_response(pk, "Invalid request: missing server, model, or references array");
            return true;
        }

        pk.pack("payload");
        pk.pack_map(1);
        pk.pack("values");
        pk.pack_map(refs_obj->via.array.size);

        for (uint32_t i = 0; i < refs_obj->via.array.size; ++i) {
            std::string reference = ipc::codec::as_string(refs_obj->via.array.ptr[i]);
            pk.pack(reference);
            ModelNode* node = IedModel_getModelNodeByObjectReference(inst->model, reference.c_str());
            if (node && ModelNode_getType(node) == DataAttributeModelType) {
                pack_attribute_value(pk, inst->server, reinterpret_cast<DataAttribute*>(node));
            } else {
                pk.pack_map(3);
                pk.pack("value");
                pk.pack_nil();
                pk.pack("quality");
                pk.pack(0);
                pk.pack("timestamp");
                pk.pack_nil();
            }
        }

        pk.pack("error");
        pk.pack_nil();
        return true;
    }
};

class ServerGetClientsAction final : public ActionHandler {
public:
    const char* name() const override { return "server.get_clients"; }

    bool handle(ActionContext& ctx, msgpack::packer<msgpack::sbuffer>& pk) override {
        if (!ensure_payload_map(ctx, pk)) {
            return true;
        }

        std::lock_guard<std::mutex> lock(ctx.context.mutex);

        bool error_occurred = false;
        std::string instance_id = validate_and_extract_instance_id(ctx.payload, ctx.action, pk, error_occurred);
        if (error_occurred) {
            return true;
        }

        LOG4CPLUS_DEBUG(server_logger(), "server.get_clients requested for instance " << instance_id);

        auto* inst = ctx.context.get_server_instance(instance_id);

        pk.pack("payload");
        pk.pack_map(1);
        pk.pack("clients");
        if (inst) {
            pk.pack_array(inst->clients.size());
            for (const auto& client : inst->clients) {
                pk.pack_map(2);
                pk.pack("id");
                pk.pack(client.id);
                pk.pack("connected_at");
                pk.pack(client.connected_at);
            }
        } else {
            pk.pack_array(0);
        }
        pk.pack("error");
        pk.pack_nil();
        return true;
    }
};

class ServerListInstancesAction final : public ActionHandler {
public:
    const char* name() const override { return "server.list_instances"; }

    bool handle(ActionContext& ctx, msgpack::packer<msgpack::sbuffer>& pk) override {
        if (!ensure_payload_map(ctx, pk)) {
            return true;
        }

        std::lock_guard<std::mutex> lock(ctx.context.mutex);
        LOG4CPLUS_DEBUG(server_logger(), "server.list_instances requested");

        pk.pack("payload");
        pk.pack_map(1);
        pk.pack("instances");
        pk.pack_array(ctx.context.server_instances.size());

        for (const auto& entry : ctx.context.server_instances) {
            const auto& id = entry.first;
            const auto& inst = entry.second;
            pk.pack_map(4);
            pk.pack("instance_id");
            pk.pack(id);
            pk.pack("state");
            pk.pack(inst->running ? "RUNNING" : "STOPPED");
            pk.pack("port");
            pk.pack(inst->port);
            pk.pack("ied_name");
            pk.pack(inst->ied_name);
        }

        pk.pack("error");
        pk.pack_nil();
        return true;
    }
};

class ServerGetInterfacesAction final : public ActionHandler {
public:
    const char* name() const override { return "server.get_interfaces"; }

    bool handle(ActionContext& ctx, msgpack::packer<msgpack::sbuffer>& pk) override {
        if (!ensure_payload_map(ctx, pk)) {
            return true;
        }

        std::lock_guard<std::mutex> lock(ctx.context.mutex);
        LOG4CPLUS_INFO(server_logger(), "server.get_interfaces requested");

        auto interfaces = network::get_network_interfaces();

        pk.pack("payload");
        pk.pack_map(2);
        pk.pack("interfaces");
        pk.pack_array(interfaces.size());

        for (const auto& iface : interfaces) {
            pk.pack_map(4);
            pk.pack("name");
            pk.pack(iface.name);
            pk.pack("description");
            pk.pack(iface.description);
            pk.pack("is_up");
            pk.pack(iface.is_up);
            pk.pack("addresses");
            pk.pack_array(iface.addresses.size());
            for (const auto& addr : iface.addresses) {
                pk.pack(addr);
            }
        }

        pk.pack("current_interface");
        if (ctx.context.global_interface_name.empty()) {
            pk.pack_nil();
        } else {
            pk.pack_map(2);
            pk.pack("name");
            pk.pack(ctx.context.global_interface_name);
            pk.pack("prefix_len");
            pk.pack(ctx.context.global_prefix_len);
        }

        pk.pack("error");
        pk.pack_nil();
        return true;
    }
};

class ServerSetInterfaceAction final : public ActionHandler {
public:
    const char* name() const override { return "server.set_interface"; }

    bool handle(ActionContext& ctx, msgpack::packer<msgpack::sbuffer>& pk) override {
        if (!ensure_payload_map(ctx, pk)) {
            return true;
        }

        std::lock_guard<std::mutex> lock(ctx.context.mutex);
        LOG4CPLUS_INFO(server_logger(), "server.set_interface requested");

        auto iface_obj = ipc::codec::find_key(ctx.payload, "interface_name");
        if (!iface_obj) {
            LOG4CPLUS_ERROR(server_logger(), "server.set_interface: interface_name is required");
            pack_error_response(pk, "interface_name is required");
            return true;
        }

        std::string interface_name = ipc::codec::as_string(*iface_obj, "");
        int prefix_len = 24;

        if (auto prefix_obj = ipc::codec::find_key(ctx.payload, "prefix_len")) {
            prefix_len = static_cast<int>(ipc::codec::as_int64(*prefix_obj, 24));
        }

        ctx.context.global_interface_name = interface_name;
        ctx.context.global_prefix_len = prefix_len;

        LOG4CPLUS_INFO(server_logger(), "Global interface set to: " << interface_name << " (prefix_len: " << prefix_len << ")");

        pk.pack("payload");
        pk.pack_map(2);
        pk.pack("interface_name");
        pk.pack(interface_name);
        pk.pack("prefix_len");
        pk.pack(prefix_len);
        pk.pack("error");
        pk.pack_nil();
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
