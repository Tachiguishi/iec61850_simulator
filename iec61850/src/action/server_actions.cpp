#include "action_base.hpp"
#include "action_registry.hpp"
#include "action_handle.hpp"

#include "../logger.hpp"
#include "../msgpack_codec.hpp"
#include "../network_config.hpp"

#include <iec61850_dynamic_model.h>
#include <iec61850_server.h>
#include <iec61850_model.h>

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

/*
 * read reference value example:
 * {
 *  "reference": "LD0/LLN0$ST$Alm",
 *  "fc": "ST"
 * }
 * 
 * result:
 * {
 *  "stVal": true,
 *  "q": "00000000",
 *  "t": "2024-01-01T00:00:00Z"
 * }
 */
nlohmann::json attribute_value_json(IedServer server, ModelNode* dataModel, FunctionalConstraint fc) {
    nlohmann::json result;

    switch(ModelNode_getType(dataModel)) {
        case DataAttributeModelType:{
                MmsValue* value = IedServer_getAttributeValue(server, (DataAttribute*) dataModel);
                switch(MmsValue_getType(value)){
                    case MMS_ARRAY:
                    case MMS_STRUCTURE:{
                        LinkedList children = ModelNode_getChildren(dataModel);
                        if(!children) {
                            break;
                        }
                        uint32_t arraySize = MmsValue_getArraySize(value);
                        for(int i = 0; i < arraySize; i++) {
                            LinkedList current = LinkedList_get(children, i);
                            ModelNode* child = static_cast<ModelNode*>(LinkedList_getData(current));

                            const char* name = ModelNode_getName(child);
                            result[name] = attribute_value_json(server, child, fc);
                        }

                        LinkedList_destroyStatic(children);
                    }
                        break;
                    case MMS_BOOLEAN:
                        result = MmsValue_getBoolean(value);
                        break;
                    case MMS_INTEGER:
                        result = MmsValue_toInt32(value);
                        break;
                    case MMS_UNSIGNED:
                        result = MmsValue_toUint32(value);
                        break;
                    case MMS_FLOAT:
                        result = MmsValue_toFloat(value);
                        break;
                    case MMS_OCTET_STRING:{
                        int size = MmsValue_getOctetStringSize(value);
                        std::string octetStringValue;
                        octetStringValue.reserve(size * 2);
                        for (int i = 0; i < size; i++) {
                            char hex[3];
                            snprintf(hex, sizeof(hex), "%02x", MmsValue_getOctetStringOctet(value, i));
                            octetStringValue.append(hex);
                        }
                        result = octetStringValue;
                    }
                    break;
                    case MMS_VISIBLE_STRING:
                    case MMS_STRING:
                        result = MmsValue_toString(value);
                        break;
                    case MMS_BIT_STRING:{
                        uint32_t bitStringSize = MmsValue_getBitStringSize(value);
                        std::string bitStringValue;
                        bitStringValue.reserve(bitStringSize);
                        for(int i = 0; i < bitStringSize; i++) {
                            bool bit = MmsValue_getBitStringBit(value, i);
                            bitStringValue.push_back(bit ? '1' : '0');
                        }
                        result = bitStringValue;
                    }
                        break;
                    case MMS_UTC_TIME:
                    case MMS_BINARY_TIME:{
                        uint8_t tempBuf[24];
                        MmsValue_printToBuffer(value, (char*) tempBuf, sizeof(tempBuf));
                        result = std::string((char*) tempBuf);
                    }
                        break;
                    default:
                        result = {"error", "Unsupported MMS value type: " + std::string(MmsValue_getTypeString(value))};
                        break;
                }
            }
            break;
        case ModelNodeType::DataObjectModelType: {
            LinkedList children = ModelNode_getChildren(dataModel);
            if(!children) {
                break;
            }
            uint32_t childCount = LinkedList_size(children);
            for(uint32_t i = 0; i < childCount; i++) {
                LinkedList current = LinkedList_get(children, i);
                ModelNode* child = static_cast<ModelNode*>(LinkedList_getData(current));
                
                if(ModelNode_getType(child) == DataAttributeModelType) {
                    DataAttribute* da = reinterpret_cast<DataAttribute*>(child);
                    if(da->fc != fc){
                        continue;
                    }
                }

                const char* name = ModelNode_getName(child);
                result[name] = attribute_value_json(server, child, fc);
            }
            LinkedList_destroyStatic(children);
        }
            break;
        default:
            return result;
    }

    return result;
}

bool update_attribute_value(IedServer server, ModelNode* dataModel, const nlohmann::json& value_obj) {
    if (!server || !dataModel) {
        return false;
    }

    switch(ModelNode_getType(dataModel)){
        case ModelNodeType::DataObjectModelType:{
            if (!value_obj.is_object()) {
                return false;
            }

            LinkedList children = ModelNode_getChildren(dataModel);
            if (!children) {
                return false;
            }

            bool updated_any = false;
            bool all_success = true;
            uint32_t child_count = LinkedList_size(children);
            for (uint32_t i = 0; i < child_count; i++) {
                LinkedList current = LinkedList_get(children, i);
                auto* child = static_cast<ModelNode*>(LinkedList_getData(current));
                if (!child) {
                    all_success = false;
                    continue;
                }

                const char* name = ModelNode_getName(child);
                if (!name) {
                    all_success = false;
                    continue;
                }

                auto it = value_obj.find(name);
                if (it == value_obj.end()) {
                    continue;
                }

                updated_any = true;
                if (!update_attribute_value(server, child, *it)) {
                    all_success = false;
                }
            }

            LinkedList_destroyStatic(children);
            return updated_any && all_success;
        }
            break;
        case ModelNodeType::DataAttributeModelType:{
            auto* da = reinterpret_cast<DataAttribute*>(dataModel);
            MmsValue* current_value = IedServer_getAttributeValue(server, da);
            if (!current_value) {
                return false;
            }
            DataAttributeType da_type = da->type;
            switch (MmsValue_getType(current_value)) {
                case MMS_BOOLEAN: {
                    if (!value_obj.is_boolean()) {
                        return false;
                    }
                    bool new_value = value_obj.get<bool>();
                    IedServer_updateBooleanAttributeValue(server, da, new_value);
                }
                    break;
                case MMS_INTEGER:{
                    if (!value_obj.is_number_integer()) {
                        return false;
                    }
                    int32_t new_int_value = value_obj.get<int32_t>();
                    IedServer_updateInt32AttributeValue(server, da, new_int_value);
                }
                    break;
                case MMS_UNSIGNED:{
                    if (!value_obj.is_number_unsigned()) {
                        return false;
                    }
                    uint32_t new_uint_value = value_obj.get<uint32_t>();
                    IedServer_updateUnsignedAttributeValue(server, da, new_uint_value);
                }
                    break;
                case MMS_FLOAT:{
                    if (!value_obj.is_number()) {
                        return false;
                    }
                    float new_float_value = value_obj.get<float>();
                    IedServer_updateFloatAttributeValue(server, da, new_float_value);
                }
                    break;
                case MMS_VISIBLE_STRING:
                case MMS_STRING:{
                    if (!value_obj.is_string()) {
                        return false;
                    }
                    std::string new_str_value = value_obj.get<std::string>();
                    IedServer_updateVisibleStringAttributeValue(server, da, const_cast<char*>(new_str_value.c_str()));
                }
                    break;
                case MMS_OCTET_STRING:{
                    if (!value_obj.is_string()) {
                        return false;
                    }
                    std::string octet_str_value = value_obj.get<std::string>();
                    std::vector<uint8_t> octet_bytes;
                    for (size_t i = 0; i < octet_str_value.size(); i += 2) {
                        if (i + 1 >= octet_str_value.size()) {
                            return false;
                        }
                        uint8_t byte = std::stoul(octet_str_value.substr(i, 2), nullptr, 16);
                        octet_bytes.push_back(byte);
                    }
                    MmsValue_setOctetString(current_value, octet_bytes.data(), octet_bytes.size());
                }
                    break;
                case MMS_BIT_STRING:{
                    if (!value_obj.is_string()) {
                        return false;
                    }
                    std::string bit_str_value = value_obj.get<std::string>();
                    uint32_t bitValue = 0;
                    for (size_t i = 0; i < bit_str_value.size(); i++) {
                        char c = bit_str_value[i];
                        if (c != '0' && c != '1') {
                            return false;
                        }
                        if (c == '1') {
                            bitValue |= (1 << i);
                        }
                    }
                    if(da_type == DataAttributeType::IEC61850_QUALITY) {
                        IedServer_updateQuality(server, da, bitValue);
                    }
                    else {
                        IedServer_updateBitStringAttributeValue(server, da, bitValue);
                    }
                }
                    break;
                case MMS_UTC_TIME:
                case MMS_BINARY_TIME:{
                    if (!value_obj.is_string()) {
                        return false;
                    }
                    std::string time_str_value = value_obj.get<std::string>();

                    int millis = 0;
                    if (!time_str_value.empty() && time_str_value.back() == 'Z') {
                        time_str_value.pop_back();
                    }

                    size_t dot_pos = time_str_value.find('.');
                    if (dot_pos != std::string::npos) {
                        std::string fraction = time_str_value.substr(dot_pos + 1);
                        time_str_value = time_str_value.substr(0, dot_pos);
                        if (fraction.empty() || fraction.size() > 3 ||
                            !std::all_of(fraction.begin(), fraction.end(), [](char c) { return c >= '0' && c <= '9'; })) {
                            return false;
                        }
                        while (fraction.size() < 3) {
                            fraction.push_back('0');
                        }
                        millis = std::stoi(fraction);
                    }

                    struct tm tm{};

                    const char* formats[] = {
                        "%Y%m%d%H%M%S",
                        "%Y%m%dT%H%M%S",
                        "%Y-%m-%dT%H:%M:%S",
                    };

                    bool parsed = false;
                    for (const char* format : formats) {
                        tm = {};
                        char* end = strptime(time_str_value.c_str(), format, &tm);
                        if (end && *end == '\0') {
                            parsed = true;
                            break;
                        }
                    }

                    if (!parsed) {
                        return false;
                    }

                    time_t time_value = timegm(&tm);
                    IedServer_updateUTCTimeAttributeValue(server, da,
                                                           static_cast<uint64_t>(time_value) * 1000 + static_cast<uint64_t>(millis));
                }
                    break;
                case MMS_ARRAY:
                case MMS_STRUCTURE:{
                    if (!value_obj.is_object()) {
                        return false;
                    }
                    LinkedList children = ModelNode_getChildren(dataModel);
                    if (!children) {
                        return false;
                    }
                    bool updated_any = false;
                    bool all_success = true;
                    uint32_t array_size = MmsValue_getArraySize(current_value);
                    for (uint32_t i = 0; i < array_size; i++) {
                        LinkedList current = LinkedList_get(children, i);
                        ModelNode* child = static_cast<ModelNode*>(LinkedList_getData(current));
                        const char* name = ModelNode_getName(child);
                        auto it = value_obj.find(name);
                        if (it == value_obj.end()) {
                            continue;
                        }
                        updated_any = true;
                        if (!update_attribute_value(server, child, *it)) {
                            all_success = false;
                        }
                    }
                    LinkedList_destroyStatic(children);
                    return updated_any && all_success;
                }
                    break;
                default:
                    return false;
            }
        }
            break;
        default:
            return false;
    }

    return true;
}

} // namespace

namespace ipc::actions {

class ServerStartAction final : public ActionHandler {
public:
    ActionMethod name() const override { return ActionMethod::ServerStart; }

    bool handle(ActionContext& ctx, nlohmann::json& response) override {
        if (!check_payload_existence(ctx, response)) {
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
        if (!inst || !inst->model || !inst->server) {
            LOG4CPLUS_ERROR(server_logger(), "server.start: server not initialized for instance " << instance_id);
            pack_error_response(response, "Server not initialized. Call server.load_model first");
            return true;
        }

        if (inst->running) {
            LOG4CPLUS_ERROR(server_logger(), "server.start: server already running for instance " << instance_id);
            pack_error_response(response, "Server is already running");
            return true;
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
                inst->ip_address = ip_address;
            }
        }

        if (inst->ip_address != "0.0.0.0") {
            IedServer_setLocalIpAddress(inst->server, inst->ip_address.c_str());
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

        IedServer_setConnectionIndicationHandler(inst->server, on_connection_event, inst);

        LOG4CPLUS_INFO(server_logger(), "Starting server instance " << instance_id << " on " << ip_address << ":" << port);
        IedServer_start(inst->server, port);
        inst->running = IedServer_isRunning(inst->server);

        LOG4CPLUS_INFO(server_logger(), "Server instance " << instance_id << " started on " << ip_address << ":" << port << " with state " << (inst->running ? "RUNNING" : "FAILED"));

        response["result"] = {
            {"success", inst->running},
            {"instance_id", instance_id},
        };
        return true;
    }
};

class ServerStopAction final : public ActionHandler {
public:
    ActionMethod name() const override { return ActionMethod::ServerStop; }

    bool handle(ActionContext& ctx, nlohmann::json& response) override {
        if (!check_payload_existence(ctx, response)) {
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
        return true;
    }
};

class ServerRemoveAction final : public ActionHandler {
public:
    ActionMethod name() const override { return ActionMethod::ServerRemove; }

    bool handle(ActionContext& ctx, nlohmann::json& response) override {
        if (!check_payload_existence(ctx, response)) {
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
        return true;
    }
};

class ServerWriteAction final : public ActionHandler {
public:
    ActionMethod name() const override { return ActionMethod::ServerWrite; }

    bool handle(ActionContext& ctx, nlohmann::json& response) override {
        if (!check_payload_existence(ctx, response)) {
            return true;
        }

        std::lock_guard<std::mutex> lock(ctx.context.mutex);

        bool error_occurred = false;
        std::string instance_id = validate_and_extract_instance_id(ctx.payload, ctx.action, response, error_occurred);
        if (error_occurred) {
            return true;
        }

        auto* inst = ctx.context.get_server_instance(instance_id);
        if (!inst || !inst->server || !inst->model) {
            LOG4CPLUS_ERROR(server_logger(), "server.write invalid request for instance " << instance_id);
            pack_error_response(response, "Invalid request: missing server, model, or items array");
            return true;
        }

        auto items_obj = ipc::codec::find_key(ctx.payload, "items");
        if(!items_obj || !items_obj->is_array()){
            LOG4CPLUS_ERROR(server_logger(), "server.write: missing or invalid 'items' array for instance " << instance_id);
            pack_error_response(response, "Invalid request: missing or invalid 'items' array");
            return true;
        }

        nlohmann::json results = nlohmann::json::array();
        IedServer_lockDataModel(inst->server);
        for (const auto& write_item : *items_obj) {
            std::string reference = write_item.value("reference", "");
            std::string fc = write_item.value("fc", ""); // Optional functional constraint for better error messages
            nlohmann::json result = {
                {"reference", reference},
                {"fc", fc},
            };

            auto item_value = ipc::codec::find_key(write_item, "value");
            if (!item_value || item_value->is_null()) {
                result["success"] = false;
                result["error"] = "Invalid value";
                results.push_back(result);
                continue;
            }

            ModelNode* node = IedModel_getModelNodeByObjectReference(inst->model, reference.c_str());
            if (!node) {
                result["success"] = false;
                result["error"] = "Reference not found";
                results.push_back(result);
                continue;
            }

           bool update_result = update_attribute_value(inst->server, node, *item_value);
            result["success"] = update_result;
            if(!update_result) {
                result["error"] = "value update failed (unsupported type or invalid value)";
            }

            results.push_back(result);
        }
        IedServer_unlockDataModel(inst->server);

        response["result"] = results;
        return true;
    }
};

class ServerReadAction final : public ActionHandler {
public:
    ActionMethod name() const override { return ActionMethod::ServerRead; }

    bool handle(ActionContext& ctx, nlohmann::json& response) override {
        if (!check_payload_existence(ctx, response)) {
            return true;
        }

        std::lock_guard<std::mutex> lock(ctx.context.mutex);

        bool error_occurred = false;
        std::string instance_id = validate_and_extract_instance_id(ctx.payload, ctx.action, response, error_occurred);
        if (error_occurred) {
            return true;
        }

        auto* inst = ctx.context.get_server_instance(instance_id);
        if (!inst || !inst->server || !inst->model) {
            LOG4CPLUS_ERROR(server_logger(), "server.read invalid request for instance " << instance_id);
            pack_error_response(response, "Invalid request: missing server, model, or references array");
            return true;
        }

        auto items_obj = ipc::codec::find_key(ctx.payload, "items");
        if(!items_obj || !items_obj->is_array()){
            LOG4CPLUS_ERROR(server_logger(), "server.write: missing or invalid 'items' array for instance " << instance_id);
            pack_error_response(response, "Invalid request: missing or invalid 'items' array");
            return true;
        }

        nlohmann::json values = nlohmann::json::array();
        for (const auto& ref_item : *items_obj) {
            std::string reference = ref_item.value("reference", "");
            std::string fc = ref_item.value("fc", "");
            ModelNode* node = IedModel_getModelNodeByObjectReference(inst->model, reference.c_str());
            nlohmann::json value = {
                {"reference", reference},
                {"fc", fc},
            };
            if (node) {
                FunctionalConstraint fc_enum = FunctionalConstraint_fromString(fc.c_str());
                if(fc_enum == IEC61850_FC_NONE) {
                    LOG4CPLUS_WARN(server_logger(), "Unknown functional constraint '" << fc << "' for reference " << reference);
                    value["error"] = "Unknown functional constraint: " + fc;
                }
                else{
                    if(fc_enum == IEC61850_FC_SE){
                        fc_enum = IEC61850_FC_SG; // SE is an editable version of SG
                    }
                    nlohmann::json result = attribute_value_json(inst->server, node, fc_enum);
                    if(result.is_null()) {
                        LOG4CPLUS_WARN(server_logger(), "Failed to read value for reference " << reference << " with functional constraint " << fc);
                        value["error"] = "Failed to read value for reference with functional constraint: " + fc;
                    } else {
                        value["value"] = result;
                    }
                }
            } else {
                value["error"] = "Reference not found";
            }

            values.push_back(value);
        }

        response["result"] = values;
        return true;
    }
};

class ServerGetClientsAction final : public ActionHandler {
public:
    ActionMethod name() const override { return ActionMethod::ServerGetClients; }

    bool handle(ActionContext& ctx, nlohmann::json& response) override {
        if (!check_payload_existence(ctx, response)) {
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
        return true;
    }
};

class ServerListInstancesAction final : public ActionHandler {
public:
    ActionMethod name() const override { return ActionMethod::ServerListInstances; }

    bool handle(ActionContext& ctx, nlohmann::json& response) override {
        if (!check_payload_existence(ctx, response)) {
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
        return true;
    }
};

class ServerGetInterfacesAction final : public ActionHandler {
public:
    ActionMethod name() const override { return ActionMethod::ServerGetInterfaces; }

    bool handle(ActionContext& ctx, nlohmann::json& response) override {
        if (!check_payload_existence(ctx, response)) {
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
        return true;
    }
};

class ServerSetInterfaceAction final : public ActionHandler {
public:
    ActionMethod name() const override { return ActionMethod::ServerSetInterface; }

    bool handle(ActionContext& ctx, nlohmann::json& response) override {
        if (!check_payload_existence(ctx, response)) {
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
        return true;
    }
};

void register_server_actions(ActionRegistry& registry) {
    registry.add(std::make_unique<ServerStartAction>());
    registry.add(std::make_unique<ServerStopAction>());
    registry.add(std::make_unique<ServerRemoveAction>());
    registry.add(std::make_unique<ServerConfigAction>());
    registry.add(std::make_unique<ServerLoadModelAction>());
    registry.add(std::make_unique<ServerWriteAction>());
    registry.add(std::make_unique<ServerReadAction>());
    registry.add(std::make_unique<ServerGetClientsAction>());
    registry.add(std::make_unique<ServerListInstancesAction>());
    registry.add(std::make_unique<ServerGetInterfacesAction>());
    registry.add(std::make_unique<ServerSetInterfaceAction>());
}

} // namespace ipc::actions
