#include "action_server.hpp"

#include "logger.hpp"
#include "msgpack_codec.hpp"

#include <iec61850_dynamic_model.h>

#include <algorithm>
#include <chrono>
#include <ctime>

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

// 从payload中提取instance_id，必须提供instance_id
std::string extract_instance_id(const msgpack::object& payload) {
    if (auto id_obj = ipc::codec::find_key(payload, "instance_id")) {
        std::string id = ipc::codec::as_string(*id_obj, "");
        if (!id.empty()) {
            return id;
        }
    }
    return "";
}

FunctionalConstraint map_fc(const std::string& fc) {
    if (fc == "ST") return IEC61850_FC_ST;
    if (fc == "MX") return IEC61850_FC_MX;
    if (fc == "SP") return IEC61850_FC_SP;
    if (fc == "SV") return IEC61850_FC_SV;
    if (fc == "CF") return IEC61850_FC_CF;
    if (fc == "DC") return IEC61850_FC_DC;
    if (fc == "SG") return IEC61850_FC_SG;
    if (fc == "SE") return IEC61850_FC_SE;
    if (fc == "SR") return IEC61850_FC_SR;
    if (fc == "OR") return IEC61850_FC_OR;
    if (fc == "BL") return IEC61850_FC_BL;
    if (fc == "EX") return IEC61850_FC_EX;
    if (fc == "CO") return IEC61850_FC_CO;
    return IEC61850_FC_ST;
}

DataAttributeType map_type(const std::string& type) {
    if (type == "BOOLEAN") return IEC61850_BOOLEAN;
    if (type == "INT8") return IEC61850_INT8;
    if (type == "INT16") return IEC61850_INT16;
    if (type == "INT32") return IEC61850_INT32;
    if (type == "INT64") return IEC61850_INT64;
    if (type == "INT8U") return IEC61850_INT8U;
    if (type == "INT16U") return IEC61850_INT16U;
    if (type == "INT32U") return IEC61850_INT32U;
    if (type == "FLOAT32") return IEC61850_FLOAT32;
    if (type == "FLOAT64") return IEC61850_FLOAT64;
    if (type == "ENUM") return IEC61850_ENUMERATED;
    if (type == "VIS_STRING_32") return IEC61850_VISIBLE_STRING_32;
    if (type == "VIS_STRING_64") return IEC61850_VISIBLE_STRING_64;
    if (type == "VIS_STRING_129") return IEC61850_VISIBLE_STRING_129;
    if (type == "VIS_STRING_255") return IEC61850_VISIBLE_STRING_255;
    if (type == "UNICODE_STRING_255") return IEC61850_UNICODE_STRING_255;
    if (type == "OCTET_STRING_64") return IEC61850_OCTET_STRING_64;
    if (type == "QUALITY") return IEC61850_QUALITY;
    if (type == "TIMESTAMP") return IEC61850_TIMESTAMP;
    return IEC61850_VISIBLE_STRING_255;
}

MmsValue* create_value_from_msg(const msgpack::object& obj, DataAttributeType type) {
    switch (type) {
        case IEC61850_BOOLEAN:
            return MmsValue_newBoolean(ipc::codec::as_bool(obj));
        case IEC61850_INT8:
        case IEC61850_INT16:
        case IEC61850_INT32:
        case IEC61850_ENUMERATED:
            return MmsValue_newIntegerFromInt32(static_cast<int32_t>(ipc::codec::as_int64(obj)));
        case IEC61850_INT64:
            return MmsValue_newIntegerFromInt64(static_cast<int64_t>(ipc::codec::as_int64(obj)));
        case IEC61850_INT8U:
        case IEC61850_INT16U:
        case IEC61850_INT32U:
            return MmsValue_newUnsignedFromUint32(static_cast<uint32_t>(ipc::codec::as_int64(obj)));
        case IEC61850_FLOAT32:
            return MmsValue_newFloat(static_cast<float>(ipc::codec::as_double(obj)));
        case IEC61850_FLOAT64:
            return MmsValue_newDouble(ipc::codec::as_double(obj));
        case IEC61850_VISIBLE_STRING_32:
        case IEC61850_VISIBLE_STRING_64:
        case IEC61850_VISIBLE_STRING_129:
        case IEC61850_VISIBLE_STRING_255:
        case IEC61850_UNICODE_STRING_255: {
            std::string value = ipc::codec::as_string(obj, "");
            return MmsValue_newVisibleString(const_cast<char*>(value.c_str()));
        }
        default:
            return nullptr;
    }
}

void create_attribute_recursive(const std::string& name, ModelNode* parent, const msgpack::object& attr_obj) {
    std::string type_str;
    std::string fc_str = "ST";

    if (auto type_obj = ipc::codec::find_key(attr_obj, "type")) {
        type_str = ipc::codec::as_string(*type_obj);
    }
    if (auto fc_obj = ipc::codec::find_key(attr_obj, "fc")) {
        fc_str = ipc::codec::as_string(*fc_obj);
    }

    auto attributes_obj = ipc::codec::find_key(attr_obj, "attributes");
    bool has_children = attributes_obj && attributes_obj->type == msgpack::type::MAP;

    DataAttributeType attr_type = has_children ? IEC61850_CONSTRUCTED : map_type(type_str);
    FunctionalConstraint fc = map_fc(fc_str);
    DataAttribute* da = DataAttribute_create(name.c_str(), parent, attr_type, fc, 0, 0, 0);

    if (has_children) {
        auto map = attributes_obj->via.map;
        for (uint32_t i = 0; i < map.size; ++i) {
            std::string child_name(map.ptr[i].key.via.str.ptr, map.ptr[i].key.via.str.size);
            create_attribute_recursive(child_name, reinterpret_cast<ModelNode*>(da), map.ptr[i].val);
        }
        return;
    }

    if (auto value_obj = ipc::codec::find_key(attr_obj, "value")) {
        MmsValue* value = create_value_from_msg(*value_obj, attr_type);
        if (value) {
            DataAttribute_setValue(da, value);
        }
    }
}

IedModel* build_model_from_dict(const msgpack::object& model_obj, std::string& out_ied_name) {
    std::string ied_name = "IED";
    if (auto name_obj = ipc::codec::find_key(model_obj, "name")) {
        ied_name = ipc::codec::as_string(*name_obj, "IED");
    }
    out_ied_name = ied_name;

    IedModel* model = IedModel_create(ied_name.c_str());
    IedModel_setIedNameForDynamicModel(model, ied_name.c_str());

    auto lds_obj = ipc::codec::find_key(model_obj, "logical_devices");
    if (!lds_obj || lds_obj->type != msgpack::type::MAP) {
        return model;
    }

    auto ld_map = lds_obj->via.map;
    for (uint32_t i = 0; i < ld_map.size; ++i) {
        std::string ld_name(ld_map.ptr[i].key.via.str.ptr, ld_map.ptr[i].key.via.str.size);
        LogicalDevice* ld = LogicalDevice_create(ld_name.c_str(), model);

        auto ln_obj = ipc::codec::find_key(ld_map.ptr[i].val, "logical_nodes");
        if (!ln_obj || ln_obj->type != msgpack::type::MAP) {
            continue;
        }

        auto ln_map = ln_obj->via.map;
        for (uint32_t j = 0; j < ln_map.size; ++j) {
            std::string ln_name(ln_map.ptr[j].key.via.str.ptr, ln_map.ptr[j].key.via.str.size);
            LogicalNode* ln = LogicalNode_create(ln_name.c_str(), ld);

            auto do_obj = ipc::codec::find_key(ln_map.ptr[j].val, "data_objects");
            if (!do_obj || do_obj->type != msgpack::type::MAP) {
                continue;
            }

            auto do_map = do_obj->via.map;
            for (uint32_t k = 0; k < do_map.size; ++k) {
                std::string do_name(do_map.ptr[k].key.via.str.ptr, do_map.ptr[k].key.via.str.size);
                DataObject* dobj = DataObject_create(do_name.c_str(), reinterpret_cast<ModelNode*>(ln), 0);

                auto attrs_obj = ipc::codec::find_key(do_map.ptr[k].val, "attributes");
                if (!attrs_obj || attrs_obj->type != msgpack::type::MAP) {
                    continue;
                }

                auto attr_map = attrs_obj->via.map;
                for (uint32_t a = 0; a < attr_map.size; ++a) {
                    std::string attr_name(attr_map.ptr[a].key.via.str.ptr, attr_map.ptr[a].key.via.str.size);
                    create_attribute_recursive(attr_name, reinterpret_cast<ModelNode*>(dobj), attr_map.ptr[a].val);
                }
            }
        }
    }

    return model;
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
            IedServer_updateVisibleStringAttributeValue(server, da, const_cast<char*>(value.c_str()));
            break;
        }
        default:
            break;
    }
}

} // namespace

namespace ipc::actions {

bool handle_server_action(
    const std::string& action,
    BackendContext& context,
    const msgpack::object& payload,
    bool has_payload,
    msgpack::packer<msgpack::sbuffer>& pk) {

    if (!has_payload || payload.type != msgpack::type::MAP) {
        LOG4CPLUS_ERROR(server_logger(),  action << " missing payload");
        pk.pack("payload");
        pk.pack_map(0);
        pk.pack("error");
        ipc::codec::pack_error(pk, "Missing payload");
        return true;
    }

    // 提取instance_id，必须提供
    std::string instance_id = extract_instance_id(payload);
    
    if (action == "server.start") {
        std::lock_guard<std::mutex> lock(context.mutex);

        // 检查instance_id是否提供
        if (instance_id.empty()) {
            LOG4CPLUS_ERROR(server_logger(), "server.start: instance_id is required");
            pk.pack("payload");
            pk.pack_map(0);
            pk.pack("error");
            ipc::codec::pack_error(pk, "instance_id is required");
            return true;
        }
        
        LOG4CPLUS_INFO(server_logger(), "server.start requested for instance " + instance_id);

        auto* inst = context.get_server_instance(instance_id);
        if (!inst || !inst->server || !inst->model) {
            LOG4CPLUS_ERROR(server_logger(), "server.start: server not initialized, call server.load_model first");
            pk.pack("payload");
            pk.pack_map(0);
            pk.pack("error");
            ipc::codec::pack_error(pk, "Server not initialized. Call server.load_model first");
            return true;
        }

        // 如果已经运行则停止
        if (inst->running) {
            IedServer_stop(inst->server);
            inst->running = false;
        }

        int port = inst->port;
        std::string ip_address = inst->ip_address;
        
        // 检查是否有新的port配置
        auto config_obj = ipc::codec::find_key(payload, "config");
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
        
        LOG4CPLUS_INFO(server_logger(), "Starting server instance " << instance_id << " on " << ip_address << ":" << port);
        IedServer_start(inst->server, port);
        inst->running = true;
        
        LOG4CPLUS_INFO(server_logger(), "Server instance " << instance_id << " started on " << ip_address << ":" << port);
        
        pk.pack("payload");
        pk.pack_map(2);
        pk.pack("success");
        pk.pack(true);
        pk.pack("instance_id");
        pk.pack(instance_id);
        pk.pack("error");
        pk.pack_nil();
        return true;
    }

    if (action == "server.stop") {
        std::lock_guard<std::mutex> lock(context.mutex);
        
        // 检查instance_id是否提供
        if (instance_id.empty()) {
            LOG4CPLUS_ERROR(server_logger(), "server.stop: instance_id is required");
            pk.pack("payload");
            pk.pack_map(0);
            pk.pack("error");
            ipc::codec::pack_error(pk, "instance_id is required");
            return true;
        }
        
        LOG4CPLUS_INFO(server_logger(), "server.stop requested for instance " + instance_id);

        auto* inst = context.get_server_instance(instance_id);
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

    if (action == "server.remove") {
        std::lock_guard<std::mutex> lock(context.mutex);
        
        // 检查instance_id是否提供
        if (instance_id.empty()) {
            LOG4CPLUS_ERROR(server_logger(), "server.remove: instance_id is required");
            pk.pack("payload");
            pk.pack_map(0);
            pk.pack("error");
            ipc::codec::pack_error(pk, "instance_id is required");
            return true;
        }
        
        LOG4CPLUS_INFO(server_logger(), "server.remove requested for instance " + instance_id);

        auto* inst = context.get_server_instance(instance_id);
        if (inst) {
            // 先停止服务
            if (inst->server) {
                if (inst->running) {
                    IedServer_stop(inst->server);
                    inst->running = false;
                }
                IedServer_destroy(inst->server);
                inst->server = nullptr;
            }
            // 释放配置
            if (inst->config) {
                IedServerConfig_destroy(inst->config);
                inst->config = nullptr;
            }
            // 释放模型
            if (inst->model) {
                IedModel_destroy(inst->model);
                inst->model = nullptr;
            }
            inst->clients.clear();
            // 从上下文中删除实例
            context.remove_server_instance(instance_id);
            LOG4CPLUS_INFO(server_logger(), "Server instance " << instance_id << " removed");
        }

        pk.pack("payload");
        ipc::codec::pack_success_payload(pk);
        pk.pack("error");
        pk.pack_nil();
        return true;
    }

    if (action == "server.load_model") {
        std::lock_guard<std::mutex> lock(context.mutex);

        // 检查instance_id是否提供
        if (instance_id.empty()) {
            LOG4CPLUS_ERROR(server_logger(), "server.load_model: instance_id is required");
            pk.pack("payload");
            pk.pack_map(0);
            pk.pack("error");
            ipc::codec::pack_error(pk, "instance_id is required");
            return true;
        }
        
        LOG4CPLUS_INFO(server_logger(), "server.load_model requested for instance " + instance_id);

        auto model_obj = ipc::codec::find_key(payload, "model");
        auto config_obj = ipc::codec::find_key(payload, "config");
        
        if (!model_obj) {
            LOG4CPLUS_ERROR(server_logger(), "server.load_model: model is required");
            pk.pack("payload");
            pk.pack_map(0);
            pk.pack("error");
            ipc::codec::pack_error(pk, "model payload is required");
            return true;
        }

        // 获取或创建实例
        auto* inst = context.get_or_create_server_instance(instance_id);
        
        // 清理旧资源
        if (inst->server) {
            IedServer_stop(inst->server);
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
        
        // 构建model
        inst->model = build_model_from_dict(*model_obj, inst->ied_name);
        
        // 创建配置
        inst->config = IedServerConfig_create();
        
        // 从config中读取参数
        int max_conn = 10;
        int port = 102;
        std::string ip_address = "0.0.0.0";
        
        if (config_obj && config_obj->type == msgpack::type::MAP) {
            if (auto max_conn_obj = ipc::codec::find_key(*config_obj, "max_connections")) {
                max_conn = static_cast<int>(ipc::codec::as_int64(*max_conn_obj, 10));
            }
            if (auto port_obj = ipc::codec::find_key(*config_obj, "port")) {
                port = static_cast<int>(ipc::codec::as_int64(*port_obj, 102));
            }
            if (auto ip_obj = ipc::codec::find_key(*config_obj, "ip_address")) {
                ip_address = ipc::codec::as_string(*ip_obj, "0.0.0.0");
            }
        }
        
        IedServerConfig_setMaxMmsConnections(inst->config, max_conn);
        
        // 创建IedServer
        inst->server = IedServer_createWithConfig(inst->model, nullptr, inst->config);
        IedServer_setConnectionIndicationHandler(inst->server, on_connection_event, inst);
        
        // 设置本地 IP 地址
        if (ip_address != "0.0.0.0") {
            IedServer_setLocalIpAddress(inst->server, ip_address.c_str());
            LOG4CPLUS_INFO(server_logger(), "Server instance " << instance_id << " configured IP: " << ip_address);
        }
        
        inst->port = port;
        inst->ip_address = ip_address;
        
        LOG4CPLUS_INFO(server_logger(), "Server instance " << instance_id << " loaded model (" << inst->ied_name << "), ready to start on " << ip_address << ":" << port);
        
        pk.pack("payload");
        pk.pack_map(2);
        pk.pack("success");
        pk.pack(true);
        pk.pack("instance_id");
        pk.pack(instance_id);
        pk.pack("error");
        pk.pack_nil();
        return true;
    }

    if (action == "server.set_data_value") {
        std::lock_guard<std::mutex> lock(context.mutex);
        
        // 检查instance_id是否提供
        if (instance_id.empty()) {
            LOG4CPLUS_ERROR(server_logger(), "server.set_data_value: instance_id is required");
            pk.pack("payload");
            pk.pack_map(0);
            pk.pack("error");
            ipc::codec::pack_error(pk, "instance_id is required");
            return true;
        }
        
        auto ref_obj = ipc::codec::find_key(payload, "reference");
        auto value_obj = ipc::codec::find_key(payload, "value");
        
        auto* inst = context.get_server_instance(instance_id);
        if (!inst || !inst->server || !inst->model || !ref_obj || !value_obj) {
            LOG4CPLUS_ERROR(server_logger(), "server.set_data_value invalid request");
            pk.pack("payload");
            pk.pack_map(0);
            pk.pack("error");
            ipc::codec::pack_error(pk, "Invalid request");
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

    if (action == "server.get_values") {
        std::lock_guard<std::mutex> lock(context.mutex);
        
        // 检查instance_id是否提供
        if (instance_id.empty()) {
            LOG4CPLUS_ERROR(server_logger(), "server.get_values: instance_id is required");
            pk.pack("payload");
            pk.pack_map(0);
            pk.pack("error");
            ipc::codec::pack_error(pk, "instance_id is required");
            return true;
        }
        
        auto refs_obj = ipc::codec::find_key(payload, "references");
        
        auto* inst = context.get_server_instance(instance_id);
        if (!inst || !inst->server || !inst->model || !refs_obj || refs_obj->type != msgpack::type::ARRAY) {
            LOG4CPLUS_ERROR(server_logger(), "server.get_values invalid request");
            pk.pack("payload");
            pk.pack_map(0);
            pk.pack("error");
            ipc::codec::pack_error(pk, "Invalid request");
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

    if (action == "server.get_clients") {
        std::lock_guard<std::mutex> lock(context.mutex);
        
        // 检查instance_id是否提供
        if (instance_id.empty()) {
            LOG4CPLUS_ERROR(server_logger(), "server.get_clients: instance_id is required");
            pk.pack("payload");
            pk.pack_map(0);
            pk.pack("error");
            ipc::codec::pack_error(pk, "instance_id is required");
            return true;
        }
        
        LOG4CPLUS_DEBUG(server_logger(), "server.get_clients requested for instance " + instance_id);
        
        auto* inst = context.get_server_instance(instance_id);
        
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
    
    if (action == "server.list_instances") {
        std::lock_guard<std::mutex> lock(context.mutex);
        LOG4CPLUS_DEBUG(server_logger(), "server.list_instances requested");
        
        pk.pack("payload");
        pk.pack_map(1);
        pk.pack("instances");
        pk.pack_array(context.server_instances.size());
        
        for (const auto& [id, inst] : context.server_instances) {
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

    return false;
}

} // namespace ipc::actions
