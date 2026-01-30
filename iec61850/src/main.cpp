#include "ipc_server.hpp"

#include <msgpack.hpp>

#include <iec61850_client.h>
#include <iec61850_dynamic_model.h>
#include <iec61850_server.h>

#include <algorithm>
#include <chrono>
#include <ctime>
#include <iostream>
#include <mutex>
#include <optional>
#include <string>
#include <unordered_map>
#include <vector>

#include <unistd.h>

namespace {

struct ClientInfo {
    std::string id;
    std::string connected_at;
};

struct BackendContext {
    std::mutex mutex;

    IedModel* server_model = nullptr;
    IedServer server = nullptr;
    IedServerConfig server_config = nullptr;
    std::vector<ClientInfo> clients;

    IedConnection client_connection = nullptr;
    std::string client_ied_name = "IED";
};

std::string now_iso() {
    auto now = std::chrono::system_clock::now();
    std::time_t tt = std::chrono::system_clock::to_time_t(now);
    std::tm tm{};
    gmtime_r(&tt, &tm);
    char buffer[32] = {0};
    std::strftime(buffer, sizeof(buffer), "%Y-%m-%dT%H:%M:%SZ", &tm);
    return buffer;
}

const msgpack::object* find_key(const msgpack::object& map_obj, const std::string& key) {
    if (map_obj.type != msgpack::type::MAP) {
        return nullptr;
    }

    auto map = map_obj.via.map;
    for (uint32_t i = 0; i < map.size; ++i) {
        if (map.ptr[i].key.type == msgpack::type::STR) {
            std::string k(map.ptr[i].key.via.str.ptr, map.ptr[i].key.via.str.size);
            if (k == key) {
                return &map.ptr[i].val;
            }
        }
    }
    return nullptr;
}

std::string as_string(const msgpack::object& obj, const std::string& fallback = "") {
    if (obj.type == msgpack::type::STR) {
        return std::string(obj.via.str.ptr, obj.via.str.size);
    }
    return fallback;
}

int64_t as_int64(const msgpack::object& obj, int64_t fallback = 0) {
    if (obj.type == msgpack::type::POSITIVE_INTEGER) {
        return static_cast<int64_t>(obj.via.u64);
    }
    if (obj.type == msgpack::type::NEGATIVE_INTEGER) {
        return static_cast<int64_t>(obj.via.i64);
    }
    return fallback;
}

bool as_bool(const msgpack::object& obj, bool fallback = false) {
    if (obj.type == msgpack::type::BOOLEAN) {
        return obj.via.boolean;
    }
    return fallback;
}

double as_double(const msgpack::object& obj, double fallback = 0.0) {
    if (obj.type == msgpack::type::FLOAT32 || obj.type == msgpack::type::FLOAT64) {
        return obj.via.f64;
    }
    if (obj.type == msgpack::type::POSITIVE_INTEGER) {
        return static_cast<double>(obj.via.u64);
    }
    if (obj.type == msgpack::type::NEGATIVE_INTEGER) {
        return static_cast<double>(obj.via.i64);
    }
    return fallback;
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
            return MmsValue_newBoolean(as_bool(obj));
        case IEC61850_INT8:
        case IEC61850_INT16:
        case IEC61850_INT32:
        case IEC61850_ENUMERATED:
            return MmsValue_newIntegerFromInt32(static_cast<int32_t>(as_int64(obj)));
        case IEC61850_INT64:
            return MmsValue_newIntegerFromInt64(static_cast<int64_t>(as_int64(obj)));
        case IEC61850_INT8U:
        case IEC61850_INT16U:
        case IEC61850_INT32U:
            return MmsValue_newUnsignedFromUint32(static_cast<uint32_t>(as_int64(obj)));
        case IEC61850_FLOAT32:
            return MmsValue_newFloat(static_cast<float>(as_double(obj)));
        case IEC61850_FLOAT64:
            return MmsValue_newDouble(as_double(obj));
        case IEC61850_VISIBLE_STRING_32:
        case IEC61850_VISIBLE_STRING_64:
        case IEC61850_VISIBLE_STRING_129:
        case IEC61850_VISIBLE_STRING_255:
        case IEC61850_UNICODE_STRING_255: {
            std::string value = as_string(obj, "");
            return MmsValue_newVisibleString(const_cast<char*>(value.c_str()));
        }
        default:
            return nullptr;
    }
}

void create_attribute_recursive(const std::string& name, ModelNode* parent, const msgpack::object& attr_obj) {
    std::string type_str;
    std::string fc_str = "ST";

    if (auto type_obj = find_key(attr_obj, "type")) {
        type_str = as_string(*type_obj);
    }
    if (auto fc_obj = find_key(attr_obj, "fc")) {
        fc_str = as_string(*fc_obj);
    }

    auto attributes_obj = find_key(attr_obj, "attributes");
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

    if (auto value_obj = find_key(attr_obj, "value")) {
        MmsValue* value = create_value_from_msg(*value_obj, attr_type);
        if (value) {
            DataAttribute_setValue(da, value);
        }
    }
}

IedModel* build_model_from_dict(const msgpack::object& model_obj, std::string& out_ied_name) {
    std::string ied_name = "IED";
    if (auto name_obj = find_key(model_obj, "name")) {
        ied_name = as_string(*name_obj, "IED");
    }
    out_ied_name = ied_name;

    IedModel* model = IedModel_create(ied_name.c_str());
    IedModel_setIedNameForDynamicModel(model, ied_name.c_str());

    auto lds_obj = find_key(model_obj, "logical_devices");
    if (!lds_obj || lds_obj->type != msgpack::type::MAP) {
        return model;
    }

    auto ld_map = lds_obj->via.map;
    for (uint32_t i = 0; i < ld_map.size; ++i) {
        std::string ld_name(ld_map.ptr[i].key.via.str.ptr, ld_map.ptr[i].key.via.str.size);
        LogicalDevice* ld = LogicalDevice_create(ld_name.c_str(), model);

        auto ln_obj = find_key(ld_map.ptr[i].val, "logical_nodes");
        if (!ln_obj || ln_obj->type != msgpack::type::MAP) {
            continue;
        }

        auto ln_map = ln_obj->via.map;
        for (uint32_t j = 0; j < ln_map.size; ++j) {
            std::string ln_name(ln_map.ptr[j].key.via.str.ptr, ln_map.ptr[j].key.via.str.size);
            LogicalNode* ln = LogicalNode_create(ln_name.c_str(), ld);

            auto do_obj = find_key(ln_map.ptr[j].val, "data_objects");
            if (!do_obj || do_obj->type != msgpack::type::MAP) {
                continue;
            }

            auto do_map = do_obj->via.map;
            for (uint32_t k = 0; k < do_map.size; ++k) {
                std::string do_name(do_map.ptr[k].key.via.str.ptr, do_map.ptr[k].key.via.str.size);
                DataObject* dobj = DataObject_create(do_name.c_str(), reinterpret_cast<ModelNode*>(ln), 0);

                auto attrs_obj = find_key(do_map.ptr[k].val, "attributes");
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
    auto* ctx = static_cast<BackendContext*>(param);
    std::lock_guard<std::mutex> lock(ctx->mutex);

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

void pack_error(msgpack::packer<msgpack::sbuffer>& pk, const std::string& message) {
    pk.pack_map(1);
    pk.pack("message");
    pk.pack(message);
}

void pack_success_payload(msgpack::packer<msgpack::sbuffer>& pk) {
    pk.pack_map(1);
    pk.pack("success");
    pk.pack(true);
}

void pack_value(msgpack::packer<msgpack::sbuffer>& pk, const msgpack::object& obj) {
    if (obj.type == msgpack::type::BOOLEAN) {
        pk.pack(obj.via.boolean);
    } else if (obj.type == msgpack::type::STR) {
        pk.pack(std::string(obj.via.str.ptr, obj.via.str.size));
    } else if (obj.type == msgpack::type::FLOAT32 || obj.type == msgpack::type::FLOAT64) {
        pk.pack(obj.via.f64);
    } else if (obj.type == msgpack::type::POSITIVE_INTEGER) {
        pk.pack(obj.via.u64);
    } else if (obj.type == msgpack::type::NEGATIVE_INTEGER) {
        pk.pack(obj.via.i64);
    } else if (obj.type == msgpack::type::NIL) {
        pk.pack_nil();
    } else {
        pk.pack_nil();
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

void pack_model(msgpack::packer<msgpack::sbuffer>& pk, IedConnection connection, const std::string& ied_name) {
    pk.pack_map(2);
    pk.pack("ied_name");
    pk.pack(ied_name);
    pk.pack("logical_devices");

    IedClientError error = IED_ERROR_OK;
    LinkedList ld_list = IedConnection_getLogicalDeviceList(connection, &error);
    if (error != IED_ERROR_OK || ld_list == nullptr) {
        pk.pack_map(0);
        return;
    }

    std::vector<std::string> ld_names;
    for (LinkedList element = ld_list; element; element = element->next) {
        auto* name = static_cast<char*>(element->data);
        if (name) {
            ld_names.emplace_back(name);
        }
    }
    LinkedList_destroy(ld_list);

    pk.pack_map(ld_names.size());

    for (const auto& ld_name : ld_names) {
        pk.pack(ld_name);
        pk.pack_map(2);
        pk.pack("description");
        pk.pack("");
        pk.pack("logical_nodes");

        LinkedList ln_list = IedConnection_getLogicalDeviceDirectory(connection, &error, ld_name.c_str());
        if (error != IED_ERROR_OK || ln_list == nullptr) {
            pk.pack_map(0);
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

        pk.pack_map(ln_names.size());
        for (const auto& ln_name : ln_names) {
            pk.pack(ln_name);
            pk.pack_map(3);
            pk.pack("class");
            pk.pack("");
            pk.pack("description");
            pk.pack("");
            pk.pack("data_objects");

            std::string ln_ref = ld_name + "/" + ln_name;
            LinkedList do_list = IedConnection_getLogicalNodeVariables(connection, &error, ln_ref.c_str());
            if (error != IED_ERROR_OK || do_list == nullptr) {
                pk.pack_map(0);
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

            pk.pack_map(do_names.size());
            for (const auto& do_name : do_names) {
                pk.pack(do_name);
                pk.pack_map(3);
                pk.pack("cdc");
                pk.pack("");
                pk.pack("description");
                pk.pack("");
                pk.pack("attributes");

                std::string do_ref = ln_ref + "." + do_name;
                LinkedList attr_list = IedConnection_getDataDirectory(connection, &error, do_ref.c_str());
                if (error != IED_ERROR_OK || attr_list == nullptr) {
                    pk.pack_map(0);
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

                pk.pack_map(attrs.size());
                for (const auto& attr : attrs) {
                    pk.pack(attr);
                    pk.pack_map(1);
                    pk.pack("name");
                    pk.pack(attr);
                }
            }
        }
    }
}

void update_attribute_value(IedServer server, DataAttribute* da, const msgpack::object& value_obj) {
    if (!da || !server) {
        return;
    }
    DataAttributeType type = DataAttribute_getType(da);
    switch (type) {
        case IEC61850_BOOLEAN:
            IedServer_updateBooleanAttributeValue(server, da, as_bool(value_obj));
            break;
        case IEC61850_INT8:
        case IEC61850_INT16:
        case IEC61850_INT32:
        case IEC61850_ENUMERATED:
            IedServer_updateInt32AttributeValue(server, da, static_cast<int32_t>(as_int64(value_obj)));
            break;
        case IEC61850_INT64:
            IedServer_updateInt64AttributeValue(server, da, static_cast<int64_t>(as_int64(value_obj)));
            break;
        case IEC61850_INT8U:
        case IEC61850_INT16U:
        case IEC61850_INT32U:
            IedServer_updateUnsignedAttributeValue(server, da, static_cast<uint32_t>(as_int64(value_obj)));
            break;
        case IEC61850_FLOAT32:
            IedServer_updateFloatAttributeValue(server, da, static_cast<float>(as_double(value_obj)));
            break;
        case IEC61850_FLOAT64:
            IedServer_updateFloatAttributeValue(server, da, static_cast<float>(as_double(value_obj)));
            break;
        case IEC61850_VISIBLE_STRING_32:
        case IEC61850_VISIBLE_STRING_64:
        case IEC61850_VISIBLE_STRING_129:
        case IEC61850_VISIBLE_STRING_255:
        case IEC61850_UNICODE_STRING_255: {
            std::string value = as_string(value_obj, "");
            IedServer_updateVisibleStringAttributeValue(server, da, const_cast<char*>(value.c_str()));
            break;
        }
        default:
            break;
    }
}

} // namespace

int main(int argc, char** argv) {
    for(int i = 1; i < argc; ++i) {
        if(strcmp(argv[i], "-v") == 0 || strcmp(argv[i], "--version") == 0) {
            std::cout << "Version: " << VERSION_STRING << std::endl;
            std::cout << "Commit: " << GIT_VERSION_STRING << std::endl;
            std::cout << "Build Time: " << BUILD_TIMESTAMP << std::endl;
            return 0;
        }
    }

    std::string socket_path = "/tmp/iec61850_simulator.sock";
    if (argc > 1) {
        socket_path = argv[1];
    }

    auto* context = new BackendContext();

    ipc::IpcServer server(socket_path, [context](const std::string& request_bytes, std::string& response_bytes) {
        msgpack::sbuffer buffer;
        msgpack::packer<msgpack::sbuffer> pk(&buffer);

        std::string request_id = "";
        std::string action = "";
        msgpack::object payload_obj;
        bool has_payload = false;
        msgpack::object_handle handle;

        try {
            handle = msgpack::unpack(request_bytes.data(), request_bytes.size());
            msgpack::object root = handle.get();

            if (auto id_obj = find_key(root, "id")) {
                request_id = as_string(*id_obj, "");
            }
            if (auto action_obj = find_key(root, "action")) {
                action = as_string(*action_obj, "");
            }
            if (auto payload_ptr = find_key(root, "payload")) {
                payload_obj = *payload_ptr;
                has_payload = true;
            }

        } catch (const std::exception& exc) {
            pk.pack_map(4);
            pk.pack("id");
            pk.pack(request_id);
            pk.pack("type");
            pk.pack("response");
            pk.pack("payload");
            pk.pack_map(0);
            pk.pack("error");
            pack_error(pk, std::string("Decode error: ") + exc.what());
            response_bytes.assign(buffer.data(), buffer.size());
            return;
        }

        pk.pack_map(4);
        pk.pack("id");
        pk.pack(request_id);
        pk.pack("type");
        pk.pack("response");

        if (action == "server.start") {
            std::lock_guard<std::mutex> lock(context->mutex);
            if (!has_payload || payload_obj.type != msgpack::type::MAP) {
                pk.pack("payload");
                pk.pack_map(0);
                pk.pack("error");
                pack_error(pk, "Missing payload");
            } else {
                auto config_obj = find_key(payload_obj, "config");
                auto model_obj = find_key(payload_obj, "model");
                if (!config_obj || !model_obj) {
                    pk.pack("payload");
                    pk.pack_map(0);
                    pk.pack("error");
                    pack_error(pk, "Invalid payload");
                } else {
                    if (context->server) {
                        IedServer_stop(context->server);
                        IedServer_destroy(context->server);
                        context->server = nullptr;
                    }
                    if (context->server_config) {
                        IedServerConfig_destroy(context->server_config);
                        context->server_config = nullptr;
                    }
                    if (context->server_model) {
                        IedModel_destroy(context->server_model);
                        context->server_model = nullptr;
                    }

                    std::string ied_name;
                    context->server_model = build_model_from_dict(*model_obj, ied_name);
                    context->server_config = IedServerConfig_create();

                    if (auto max_conn_obj = find_key(*config_obj, "max_connections")) {
                        IedServerConfig_setMaxMmsConnections(context->server_config, static_cast<int>(as_int64(*max_conn_obj, 10)));
                    }

                    context->server = IedServer_createWithConfig(context->server_model, nullptr, context->server_config);
                    IedServer_setConnectionIndicationHandler(context->server, on_connection_event, context);

                    int port = 102;
                    if (auto port_obj = find_key(*config_obj, "port")) {
                        port = static_cast<int>(as_int64(*port_obj, 102));
                    }
                    IedServer_start(context->server, port);

                    pk.pack("payload");
                    pack_success_payload(pk);
                    pk.pack("error");
                    pk.pack_nil();
                }
            }
        } else if (action == "server.stop") {
            std::lock_guard<std::mutex> lock(context->mutex);
            if (context->server) {
                IedServer_stop(context->server);
                IedServer_destroy(context->server);
                context->server = nullptr;
            }
            if (context->server_config) {
                IedServerConfig_destroy(context->server_config);
                context->server_config = nullptr;
            }
            if (context->server_model) {
                IedModel_destroy(context->server_model);
                context->server_model = nullptr;
            }
            context->clients.clear();

            pk.pack("payload");
            pack_success_payload(pk);
            pk.pack("error");
            pk.pack_nil();
        } else if (action == "server.load_model") {
            std::lock_guard<std::mutex> lock(context->mutex);
            if (!has_payload) {
                pk.pack("payload");
                pk.pack_map(0);
                pk.pack("error");
                pack_error(pk, "Missing payload");
            } else if (auto model_obj = find_key(payload_obj, "model")) {
                if (context->server_model) {
                    IedModel_destroy(context->server_model);
                }
                std::string ied_name;
                context->server_model = build_model_from_dict(*model_obj, ied_name);
                pk.pack("payload");
                pack_success_payload(pk);
                pk.pack("error");
                pk.pack_nil();
            } else {
                pk.pack("payload");
                pk.pack_map(0);
                pk.pack("error");
                pack_error(pk, "Invalid model payload");
            }
        } else if (action == "server.set_data_value") {
            std::lock_guard<std::mutex> lock(context->mutex);
            auto ref_obj = find_key(payload_obj, "reference");
            auto value_obj = find_key(payload_obj, "value");
            if (!context->server || !context->server_model || !ref_obj || !value_obj) {
                pk.pack("payload");
                pk.pack_map(0);
                pk.pack("error");
                pack_error(pk, "Invalid request");
            } else {
                std::string reference = as_string(*ref_obj, "");
                ModelNode* node = IedModel_getModelNodeByObjectReference(context->server_model, reference.c_str());
                if (node && ModelNode_getType(node) == DataAttributeModelType) {
                    auto* da = reinterpret_cast<DataAttribute*>(node);
                    IedServer_lockDataModel(context->server);
                    update_attribute_value(context->server, da, *value_obj);
                    IedServer_unlockDataModel(context->server);
                }
                pk.pack("payload");
                pack_success_payload(pk);
                pk.pack("error");
                pk.pack_nil();
            }
        } else if (action == "server.get_values") {
            std::lock_guard<std::mutex> lock(context->mutex);
            auto refs_obj = find_key(payload_obj, "references");
            if (!context->server || !context->server_model || !refs_obj || refs_obj->type != msgpack::type::ARRAY) {
                pk.pack("payload");
                pk.pack_map(0);
                pk.pack("error");
                pack_error(pk, "Invalid request");
            } else {
                pk.pack("payload");
                pk.pack_map(1);
                pk.pack("values");
                pk.pack_map(refs_obj->via.array.size);

                for (uint32_t i = 0; i < refs_obj->via.array.size; ++i) {
                    std::string reference = as_string(refs_obj->via.array.ptr[i]);
                    pk.pack(reference);
                    ModelNode* node = IedModel_getModelNodeByObjectReference(context->server_model, reference.c_str());
                    if (node && ModelNode_getType(node) == DataAttributeModelType) {
                        pack_attribute_value(pk, context->server, reinterpret_cast<DataAttribute*>(node));
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
            }
        } else if (action == "server.get_clients") {
            std::lock_guard<std::mutex> lock(context->mutex);
            pk.pack("payload");
            pk.pack_map(1);
            pk.pack("clients");
            pk.pack_array(context->clients.size());
            for (const auto& client : context->clients) {
                pk.pack_map(2);
                pk.pack("id");
                pk.pack(client.id);
                pk.pack("connected_at");
                pk.pack(client.connected_at);
            }
            pk.pack("error");
            pk.pack_nil();
        } else if (action == "client.connect") {
            std::lock_guard<std::mutex> lock(context->mutex);
            auto host_obj = find_key(payload_obj, "host");
            auto port_obj = find_key(payload_obj, "port");
            auto cfg_obj = find_key(payload_obj, "config");
            if (!host_obj || !port_obj) {
                pk.pack("payload");
                pk.pack_map(0);
                pk.pack("error");
                pack_error(pk, "Invalid request");
            } else {
                std::string host = as_string(*host_obj, "");
                int port = static_cast<int>(as_int64(*port_obj, 102));

                if (context->client_connection) {
                    IedConnection_destroy(context->client_connection);
                    context->client_connection = nullptr;
                }

                context->client_connection = IedConnection_create();
                if (cfg_obj && cfg_obj->type == msgpack::type::MAP) {
                    if (auto timeout_obj = find_key(*cfg_obj, "timeout_ms")) {
                        IedConnection_setConnectTimeout(context->client_connection, static_cast<int>(as_int64(*timeout_obj, 5000)));
                        IedConnection_setRequestTimeout(context->client_connection, static_cast<int>(as_int64(*timeout_obj, 5000)));
                    }
                }

                IedClientError error = IED_ERROR_OK;
                IedConnection_connect(context->client_connection, &error, host.c_str(), port);
                if (error == IED_ERROR_OK) {
                    pk.pack("payload");
                    pack_success_payload(pk);
                    pk.pack("error");
                    pk.pack_nil();
                } else {
                    pk.pack("payload");
                    pk.pack_map(0);
                    pk.pack("error");
                    pack_error(pk, IedClientError_toString(error));
                }
            }
        } else if (action == "client.disconnect") {
            std::lock_guard<std::mutex> lock(context->mutex);
            if (context->client_connection) {
                IedConnection_close(context->client_connection);
                IedConnection_destroy(context->client_connection);
                context->client_connection = nullptr;
            }
            pk.pack("payload");
            pack_success_payload(pk);
            pk.pack("error");
            pk.pack_nil();
        } else if (action == "client.browse") {
            std::lock_guard<std::mutex> lock(context->mutex);
            if (!context->client_connection) {
                pk.pack("payload");
                pk.pack_map(0);
                pk.pack("error");
                pack_error(pk, "Client not connected");
            } else {
                pk.pack("payload");
                pk.pack_map(1);
                pk.pack("model");
                pack_model(pk, context->client_connection, context->client_ied_name);
                pk.pack("error");
                pk.pack_nil();
            }
        } else if (action == "client.read") {
            std::lock_guard<std::mutex> lock(context->mutex);
            auto ref_obj = find_key(payload_obj, "reference");
            if (!context->client_connection || !ref_obj) {
                pk.pack("payload");
                pk.pack_map(0);
                pk.pack("error");
                pack_error(pk, "Invalid request");
            } else {
                std::string reference = as_string(*ref_obj, "");
                std::vector<FunctionalConstraint> fcs = {IEC61850_FC_ST, IEC61850_FC_MX, IEC61850_FC_SP, IEC61850_FC_CF};
                IedClientError error = IED_ERROR_OK;
                MmsValue* value = nullptr;
                for (auto fc : fcs) {
                    value = IedConnection_readObject(context->client_connection, &error, reference.c_str(), fc);
                    if (error == IED_ERROR_OK && value) {
                        break;
                    }
                }

                pk.pack("payload");
                pk.pack_map(1);
                pk.pack("value");
                if (error == IED_ERROR_OK && value) {
                    pk.pack_map(4);
                    pk.pack("value");
                    MmsType type = MmsValue_getType(value);
                    if (type == MMS_BOOLEAN) {
                        pk.pack(MmsValue_getBoolean(value));
                    } else if (type == MMS_INTEGER) {
                        pk.pack(MmsValue_toInt64(value));
                    } else if (type == MMS_UNSIGNED) {
                        pk.pack(MmsValue_toUint32(value));
                    } else if (type == MMS_FLOAT) {
                        pk.pack(MmsValue_toDouble(value));
                    } else if (type == MMS_VISIBLE_STRING || type == MMS_STRING) {
                        pk.pack(MmsValue_toString(value));
                    } else {
                        pk.pack_nil();
                    }
                    pk.pack("quality");
                    pk.pack(0);
                    pk.pack("timestamp");
                    pk.pack_nil();
                    pk.pack("error");
                    pk.pack_nil();
                } else {
                    pk.pack_map(4);
                    pk.pack("value");
                    pk.pack_nil();
                    pk.pack("quality");
                    pk.pack(0);
                    pk.pack("timestamp");
                    pk.pack_nil();
                    pk.pack("error");
                    pk.pack(IedClientError_toString(error));
                }
                pk.pack("error");
                pk.pack_nil();

                if (value) {
                    MmsValue_delete(value);
                }
            }
        } else if (action == "client.read_batch") {
            std::lock_guard<std::mutex> lock(context->mutex);
            auto refs_obj = find_key(payload_obj, "references");
            if (!context->client_connection || !refs_obj || refs_obj->type != msgpack::type::ARRAY) {
                pk.pack("payload");
                pk.pack_map(0);
                pk.pack("error");
                pack_error(pk, "Invalid request");
            } else {
                pk.pack("payload");
                pk.pack_map(1);
                pk.pack("values");
                pk.pack_map(refs_obj->via.array.size);

                for (uint32_t i = 0; i < refs_obj->via.array.size; ++i) {
                    std::string reference = as_string(refs_obj->via.array.ptr[i], "");
                    pk.pack(reference);
                    std::vector<FunctionalConstraint> fcs = {IEC61850_FC_ST, IEC61850_FC_MX, IEC61850_FC_SP, IEC61850_FC_CF};
                    IedClientError error = IED_ERROR_OK;
                    MmsValue* value = nullptr;
                    for (auto fc : fcs) {
                        value = IedConnection_readObject(context->client_connection, &error, reference.c_str(), fc);
                        if (error == IED_ERROR_OK && value) {
                            break;
                        }
                    }

                    pk.pack_map(4);
                    pk.pack("value");
                    if (error == IED_ERROR_OK && value) {
                        MmsType type = MmsValue_getType(value);
                        if (type == MMS_BOOLEAN) {
                            pk.pack(MmsValue_getBoolean(value));
                        } else if (type == MMS_INTEGER) {
                            pk.pack(MmsValue_toInt64(value));
                        } else if (type == MMS_UNSIGNED) {
                            pk.pack(MmsValue_toUint32(value));
                        } else if (type == MMS_FLOAT) {
                            pk.pack(MmsValue_toDouble(value));
                        } else if (type == MMS_VISIBLE_STRING || type == MMS_STRING) {
                            pk.pack(MmsValue_toString(value));
                        } else {
                            pk.pack_nil();
                        }
                    } else {
                        pk.pack_nil();
                    }
                    pk.pack("quality");
                    pk.pack(0);
                    pk.pack("timestamp");
                    pk.pack_nil();
                    pk.pack("error");
                    if (error == IED_ERROR_OK) {
                        pk.pack_nil();
                    } else {
                        pk.pack(IedClientError_toString(error));
                    }

                    if (value) {
                        MmsValue_delete(value);
                    }
                }
                pk.pack("error");
                pk.pack_nil();
            }
        } else if (action == "client.write") {
            std::lock_guard<std::mutex> lock(context->mutex);
            auto ref_obj = find_key(payload_obj, "reference");
            auto value_obj = find_key(payload_obj, "value");
            if (!context->client_connection || !ref_obj || !value_obj) {
                pk.pack("payload");
                pk.pack_map(0);
                pk.pack("error");
                pack_error(pk, "Invalid request");
            } else {
                std::string reference = as_string(*ref_obj, "");
                IedClientError error = IED_ERROR_OK;
                bool success = false;
                if (value_obj->type == msgpack::type::BOOLEAN) {
                    std::vector<FunctionalConstraint> fcs = {IEC61850_FC_SP, IEC61850_FC_CF, IEC61850_FC_ST, IEC61850_FC_MX};
                    for (auto fc : fcs) {
                        IedConnection_writeBooleanValue(context->client_connection, &error, reference.c_str(), fc, value_obj->via.boolean);
                        if (error == IED_ERROR_OK) {
                            success = true;
                            break;
                        }
                    }
                } else if (value_obj->type == msgpack::type::FLOAT32 || value_obj->type == msgpack::type::FLOAT64) {
                    double v = value_obj->via.f64;
                    std::vector<FunctionalConstraint> fcs = {IEC61850_FC_SP, IEC61850_FC_CF, IEC61850_FC_ST, IEC61850_FC_MX};
                    for (auto fc : fcs) {
                        IedConnection_writeFloatValue(context->client_connection, &error, reference.c_str(), fc, static_cast<float>(v));
                        if (error == IED_ERROR_OK) {
                            success = true;
                            break;
                        }
                    }
                } else if (value_obj->type == msgpack::type::STR) {
                    std::string value = as_string(*value_obj, "");
                    std::vector<FunctionalConstraint> fcs = {IEC61850_FC_SP, IEC61850_FC_CF, IEC61850_FC_ST, IEC61850_FC_MX};
                    for (auto fc : fcs) {
                        IedConnection_writeVisibleStringValue(context->client_connection, &error, reference.c_str(), fc, const_cast<char*>(value.c_str()));
                        if (error == IED_ERROR_OK) {
                            success = true;
                            break;
                        }
                    }
                } else {
                    int64_t v = as_int64(*value_obj);
                    std::vector<FunctionalConstraint> fcs = {IEC61850_FC_SP, IEC61850_FC_CF, IEC61850_FC_ST, IEC61850_FC_MX};
                    for (auto fc : fcs) {
                        IedConnection_writeInt32Value(context->client_connection, &error, reference.c_str(), fc, static_cast<int32_t>(v));
                        if (error == IED_ERROR_OK) {
                            success = true;
                            break;
                        }
                    }
                }

                pk.pack("payload");
                pk.pack_map(1);
                pk.pack("success");
                pk.pack(success);
                pk.pack("error");
                if (success) {
                    pk.pack_nil();
                } else {
                    pack_error(pk, IedClientError_toString(error));
                }
            }
        } else {
            pk.pack("payload");
            pk.pack_map(0);
            pk.pack("error");
            pack_error(pk, "Unknown action");
        }

        response_bytes.assign(buffer.data(), buffer.size());
    });

    if (!server.start()) {
        std::cerr << "Failed to start IPC server" << std::endl;
        return 1;
    }

    std::cout << "IEC61850 backend started at " << socket_path << std::endl;

    while (true) {
        ::sleep(1);
    }

    return 0;
}
