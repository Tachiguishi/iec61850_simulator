#include "action_base.hpp"
#include "action_registry.hpp"

#include "../logger.hpp"
#include "../msgpack_codec.hpp"

#include <iec61850_client.h>

#include <log4cplus/loggingmacros.h>

#include <mutex>
#include <string>
#include <vector>

namespace {

nlohmann::json build_model(IedConnection connection, const std::string& ied_name) {
    nlohmann::json model = {
        {"ied_name", ied_name},
        {"logical_devices", nlohmann::json::object()},
    };

    IedClientError error = IED_ERROR_OK;
    LinkedList ld_list = IedConnection_getLogicalDeviceList(connection, &error);
    if (error != IED_ERROR_OK || ld_list == nullptr) {
        return model;
    }

    std::vector<std::string> ld_names;
    for (LinkedList element = ld_list; element; element = element->next) {
        auto* name = static_cast<char*>(element->data);
        if (name) {
            ld_names.emplace_back(name);
        }
    }
    LinkedList_destroy(ld_list);

    for (const auto& ld_name : ld_names) {
        auto& ld = model["logical_devices"][ld_name];
        ld["description"] = "";
        ld["logical_nodes"] = nlohmann::json::object();

        LinkedList ln_list = IedConnection_getLogicalDeviceDirectory(connection, &error, ld_name.c_str());
        if (error != IED_ERROR_OK || ln_list == nullptr) {
            continue;
        }

        std::vector<std::string> ln_names;
        for (LinkedList element = ln_list; element; element = element->next) {
            auto* name = static_cast<char*>(element->data);
            if (name) {
                ln_names.emplace_back(name);
            }
        }
        LinkedList_destroy(ln_list);

        for (const auto& ln_name : ln_names) {
            auto& ln = ld["logical_nodes"][ln_name];
            ln["class"] = "";
            ln["description"] = "";
            ln["data_objects"] = nlohmann::json::object();

            std::string ln_ref = ld_name + "/" + ln_name;
            LinkedList do_list = IedConnection_getLogicalNodeVariables(connection, &error, ln_ref.c_str());
            if (error != IED_ERROR_OK || do_list == nullptr) {
                continue;
            }

            std::vector<std::string> do_names;
            for (LinkedList element = do_list; element; element = element->next) {
                auto* name = static_cast<char*>(element->data);
                if (name) {
                    do_names.emplace_back(name);
                }
            }
            LinkedList_destroy(do_list);

            for (const auto& do_name : do_names) {
                auto& dobj = ln["data_objects"][do_name];
                dobj["cdc"] = "";
                dobj["description"] = "";
                dobj["attributes"] = nlohmann::json::object();

                std::string do_ref = ln_ref + "." + do_name;
                LinkedList attr_list = IedConnection_getDataDirectory(connection, &error, do_ref.c_str());
                if (error != IED_ERROR_OK || attr_list == nullptr) {
                    continue;
                }

                std::vector<std::string> attrs;
                for (LinkedList element = attr_list; element; element = element->next) {
                    auto* name = static_cast<char*>(element->data);
                    if (name) {
                        attrs.emplace_back(name);
                    }
                }
                LinkedList_destroy(attr_list);

                for (const auto& attr : attrs) {
                    dobj["attributes"][attr] = nlohmann::json{{"name", attr}};
                }
            }
        }
    }

    return model;
}

std::string extract_instance_id(const nlohmann::json& payload) {
    if (auto id_obj = ipc::codec::find_key(payload, "instance_id")) {
        std::string id = ipc::codec::as_string(*id_obj, "");
        if (!id.empty()) {
            return id;
        }
    }
    return "";
}

bool require_instance_id(const nlohmann::json& payload,
                         const std::string& action,
                         nlohmann::json& response,
                         std::string& instance_id) {
    instance_id = extract_instance_id(payload);
    if (instance_id.empty()) {
        LOG4CPLUS_ERROR(client_logger(), action << ": instance_id is required");
        response["result"] = nlohmann::json::object();
        response["error"] = ipc::codec::make_error("instance_id is required");
        return false;
    }
    return true;
}

nlohmann::json read_value_result(IedConnection connection, const std::string& reference) {
    std::vector<FunctionalConstraint> fcs = {IEC61850_FC_ST, IEC61850_FC_MX, IEC61850_FC_SP, IEC61850_FC_CF};
    IedClientError error = IED_ERROR_OK;
    MmsValue* value = nullptr;
    for (auto fc : fcs) {
        value = IedConnection_readObject(connection, &error, reference.c_str(), fc);
        if (error == IED_ERROR_OK && value) {
            break;
        }
    }

    nlohmann::json value_result = {
        {"value", nullptr},
        {"quality", 0},
        {"timestamp", nullptr},
        {"error", nullptr},
    };

    if (error == IED_ERROR_OK && value) {
        MmsType type = MmsValue_getType(value);
        if (type == MMS_BOOLEAN) {
            value_result["value"] = MmsValue_getBoolean(value);
        } else if (type == MMS_INTEGER) {
            value_result["value"] = MmsValue_toInt64(value);
        } else if (type == MMS_UNSIGNED) {
            value_result["value"] = MmsValue_toUint32(value);
        } else if (type == MMS_FLOAT) {
            value_result["value"] = MmsValue_toDouble(value);
        } else if (type == MMS_VISIBLE_STRING || type == MMS_STRING) {
            value_result["value"] = std::string(MmsValue_toString(value));
        }
    } else {
        value_result["error"] = IedClientError_toString(error);
    }

    if (value) {
        MmsValue_delete(value);
    }
    return value_result;
}

} // namespace

namespace ipc::actions {

class ClientConnectAction final : public ActionHandler {
public:
    const char* name() const override { return "client.connect"; }

    bool handle(ActionContext& ctx, nlohmann::json& response) override {
        std::lock_guard<std::mutex> lock(ctx.context.mutex);

        std::string instance_id;
        if (!require_instance_id(ctx.payload, ctx.action, response, instance_id)) {
            return true;
        }

        auto host_obj = ipc::codec::find_key(ctx.payload, "host");
        auto port_obj = ipc::codec::find_key(ctx.payload, "port");
        auto cfg_obj = ipc::codec::find_key(ctx.payload, "config");
        if (!host_obj || !port_obj) {
            LOG4CPLUS_ERROR(client_logger(), "client.connect invalid request");
            response["result"] = nlohmann::json::object();
            response["error"] = ipc::codec::make_error("Invalid request");
            return true;
        }

        std::string host = ipc::codec::as_string(*host_obj, "");
        int port = static_cast<int>(ipc::codec::as_int64(*port_obj, 102));

        LOG4CPLUS_INFO(client_logger(), "client.connect to " << host << ":" << port << " for instance " + instance_id);

        auto* inst = ctx.context.get_or_create_client_instance(instance_id);

        if (inst->connection) {
            IedConnection_close(inst->connection);
            IedConnection_destroy(inst->connection);
            inst->connection = nullptr;
        }

        inst->connection = IedConnection_create();
        inst->target_host = host;
        inst->target_port = port;
        IedConnection connection = inst->connection;

        if (cfg_obj && cfg_obj->is_object()) {
            if (auto timeout_obj = ipc::codec::find_key(*cfg_obj, "timeout_ms")) {
                IedConnection_setConnectTimeout(connection, static_cast<int>(ipc::codec::as_int64(*timeout_obj, 5000)));
                IedConnection_setRequestTimeout(connection, static_cast<int>(ipc::codec::as_int64(*timeout_obj, 5000)));
            }
        }

        IedClientError error = IED_ERROR_OK;
        IedConnection_connect(connection, &error, host.c_str(), port);

        if (error == IED_ERROR_OK) {
            inst->connected = true;
            LOG4CPLUS_INFO(client_logger(), "client.connect success for instance " << instance_id);
            response["result"] = {
                {"success", true},
                {"instance_id", instance_id},
            };
            response["error"] = nullptr;
        } else {
            inst->connected = false;
            LOG4CPLUS_ERROR(client_logger(), "client.connect failed: " << IedClientError_toString(error));
            response["result"] = nlohmann::json::object();
            response["error"] = ipc::codec::make_error(IedClientError_toString(error));
        }
        return true;
    }
};

class ClientDisconnectAction final : public ActionHandler {
public:
    const char* name() const override { return "client.disconnect"; }

    bool handle(ActionContext& ctx, nlohmann::json& response) override {
        std::lock_guard<std::mutex> lock(ctx.context.mutex);

        std::string instance_id;
        if (!require_instance_id(ctx.payload, ctx.action, response, instance_id)) {
            return true;
        }

        LOG4CPLUS_INFO(client_logger(), "client.disconnect requested for instance " + instance_id);

        auto* inst = ctx.context.get_client_instance(instance_id);
        if (inst && inst->connection) {
            IedConnection_close(inst->connection);
            IedConnection_destroy(inst->connection);
            inst->connection = nullptr;
            inst->connected = false;
            ctx.context.remove_client_instance(instance_id);
        }
        response["result"] = ipc::codec::make_success_payload();
        response["error"] = nullptr;
        return true;
    }
};

class ClientBrowseAction final : public ActionHandler {
public:
    const char* name() const override { return "client.browse"; }

    bool handle(ActionContext& ctx, nlohmann::json& response) override {
        std::lock_guard<std::mutex> lock(ctx.context.mutex);

        std::string instance_id;
        if (!require_instance_id(ctx.payload, ctx.action, response, instance_id)) {
            return true;
        }

        auto* inst = ctx.context.get_client_instance(instance_id);
        IedConnection connection = inst ? inst->connection : nullptr;
        std::string ied_name = inst ? inst->ied_name : "IED";

        if (!connection) {
            LOG4CPLUS_ERROR(client_logger(), "client.browse when not connected");
            response["result"] = nlohmann::json::object();
            response["error"] = ipc::codec::make_error("Client not connected");
        } else {
            LOG4CPLUS_DEBUG(client_logger(), "client.browse requested");
            response["result"] = {
                {"model", build_model(connection, ied_name)},
            };
            response["error"] = nullptr;
        }
        return true;
    }
};

class ClientReadAction final : public ActionHandler {
public:
    const char* name() const override { return "client.read"; }

    bool handle(ActionContext& ctx, nlohmann::json& response) override {
        std::lock_guard<std::mutex> lock(ctx.context.mutex);

        std::string instance_id;
        if (!require_instance_id(ctx.payload, ctx.action, response, instance_id)) {
            return true;
        }

        auto ref_obj = ipc::codec::find_key(ctx.payload, "reference");

        auto* inst = ctx.context.get_client_instance(instance_id);
        IedConnection connection = inst ? inst->connection : nullptr;

        if (!connection || !ref_obj) {
            LOG4CPLUS_ERROR(client_logger(), "client.read invalid request");
            response["result"] = nlohmann::json::object();
            response["error"] = ipc::codec::make_error("Invalid request");
            return true;
        }

        std::string reference = ipc::codec::as_string(*ref_obj, "");
        LOG4CPLUS_DEBUG(client_logger(), "client.read " << reference);
        response["result"] = {{"value", read_value_result(connection, reference)}};
        response["error"] = nullptr;
        return true;
    }
};

class ClientReadBatchAction final : public ActionHandler {
public:
    const char* name() const override { return "client.read_batch"; }

    bool handle(ActionContext& ctx, nlohmann::json& response) override {
        std::lock_guard<std::mutex> lock(ctx.context.mutex);

        std::string instance_id;
        if (!require_instance_id(ctx.payload, ctx.action, response, instance_id)) {
            return true;
        }

        auto refs_obj = ipc::codec::find_key(ctx.payload, "references");

        auto* inst = ctx.context.get_client_instance(instance_id);
        IedConnection connection = inst ? inst->connection : nullptr;

        if (!connection || !refs_obj || !refs_obj->is_array()) {
            LOG4CPLUS_ERROR(client_logger(), "client.read_batch invalid request");
            response["result"] = nlohmann::json::object();
            response["error"] = ipc::codec::make_error("Invalid request");
            return true;
        }

        LOG4CPLUS_DEBUG(client_logger(), "client.read_batch requested");
        nlohmann::json values = nlohmann::json::object();

        for (const auto& ref : *refs_obj) {
            std::string reference = ipc::codec::as_string(ref, "");
            values[reference] = read_value_result(connection, reference);
        }

        response["result"] = {{"values", values}};
        response["error"] = nullptr;
        return true;
    }
};

class ClientWriteAction final : public ActionHandler {
public:
    const char* name() const override { return "client.write"; }

    bool handle(ActionContext& ctx, nlohmann::json& response) override {
        std::lock_guard<std::mutex> lock(ctx.context.mutex);

        std::string instance_id;
        if (!require_instance_id(ctx.payload, ctx.action, response, instance_id)) {
            return true;
        }

        auto ref_obj = ipc::codec::find_key(ctx.payload, "reference");
        auto value_obj = ipc::codec::find_key(ctx.payload, "value");

        auto* inst = ctx.context.get_client_instance(instance_id);
        IedConnection connection = inst ? inst->connection : nullptr;

        if (!connection || !ref_obj || !value_obj) {
            LOG4CPLUS_ERROR(client_logger(), "client.write invalid request");
            response["result"] = nlohmann::json::object();
            response["error"] = ipc::codec::make_error("Invalid request");
            return true;
        }

        std::string reference = ipc::codec::as_string(*ref_obj, "");
        LOG4CPLUS_DEBUG(client_logger(), "client.write " << reference);
        IedClientError error = IED_ERROR_OK;
        bool success = false;
        std::vector<FunctionalConstraint> fcs = {IEC61850_FC_SP, IEC61850_FC_CF, IEC61850_FC_ST, IEC61850_FC_MX};

        if (value_obj->is_boolean()) {
            for (auto fc : fcs) {
                IedConnection_writeBooleanValue(connection, &error, reference.c_str(), fc, value_obj->get<bool>());
                if (error == IED_ERROR_OK) {
                    success = true;
                    break;
                }
            }
        } else if (value_obj->is_number_float()) {
            double v = value_obj->get<double>();
            for (auto fc : fcs) {
                IedConnection_writeFloatValue(connection, &error, reference.c_str(), fc, static_cast<float>(v));
                if (error == IED_ERROR_OK) {
                    success = true;
                    break;
                }
            }
        } else if (value_obj->is_string()) {
            std::string value = value_obj->get<std::string>();
            for (auto fc : fcs) {
                IedConnection_writeVisibleStringValue(connection, &error, reference.c_str(), fc, const_cast<char*>(value.c_str()));
                if (error == IED_ERROR_OK) {
                    success = true;
                    break;
                }
            }
        } else {
            int64_t v = ipc::codec::as_int64(*value_obj);
            for (auto fc : fcs) {
                IedConnection_writeInt32Value(connection, &error, reference.c_str(), fc, static_cast<int32_t>(v));
                if (error == IED_ERROR_OK) {
                    success = true;
                    break;
                }
            }
        }

        response["result"] = {{"success", success}};
        if (success) {
            LOG4CPLUS_INFO(client_logger(), "client.write success");
            response["error"] = nullptr;
        } else {
            LOG4CPLUS_ERROR(client_logger(), "client.write failed: " << IedClientError_toString(error));
            response["error"] = ipc::codec::make_error(IedClientError_toString(error));
        }
        return true;
    }
};

class ClientListInstancesAction final : public ActionHandler {
public:
    const char* name() const override { return "client.list_instances"; }

    bool handle(ActionContext& ctx, nlohmann::json& response) override {
        std::lock_guard<std::mutex> lock(ctx.context.mutex);
        LOG4CPLUS_DEBUG(client_logger(), "client.list_instances requested");

        nlohmann::json instances = nlohmann::json::array();
        for (const auto& entry : ctx.context.client_instances) {
            const auto& id = entry.first;
            const auto& inst = entry.second;
            instances.push_back({
                {"instance_id", id},
                {"state", inst->connected ? "CONNECTED" : "DISCONNECTED"},
                {"target_host", inst->target_host},
                {"target_port", inst->target_port},
            });
        }

        response["result"] = {{"instances", instances}};
        response["error"] = nullptr;
        return true;
    }
};

void register_client_actions(ActionRegistry& registry) {
    registry.add(std::make_unique<ClientConnectAction>());
    registry.add(std::make_unique<ClientDisconnectAction>());
    registry.add(std::make_unique<ClientBrowseAction>());
    registry.add(std::make_unique<ClientReadAction>());
    registry.add(std::make_unique<ClientReadBatchAction>());
    registry.add(std::make_unique<ClientWriteAction>());
    registry.add(std::make_unique<ClientListInstancesAction>());
}

} // namespace ipc::actions
