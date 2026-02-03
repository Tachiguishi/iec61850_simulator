#include "action_client.hpp"

#include "logger.hpp"
#include "msgpack_codec.hpp"

#include <iec61850_client.h>

#include <log4cplus/loggingmacros.h>

#include <vector>

namespace {

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

} // namespace

namespace {

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

} // namespace

namespace ipc::actions {

bool handle_client_action(
    const std::string& action,
    BackendContext& context,
    const msgpack::object& payload,
    bool,
    msgpack::packer<msgpack::sbuffer>& pk) {
    
    // 提取instance_id，必须提供
    std::string instance_id = extract_instance_id(payload);
    
    if (action == "client.connect") {
        std::lock_guard<std::mutex> lock(context.mutex);
        
        // 检查instance_id是否提供
        if (instance_id.empty()) {
            LOG4CPLUS_ERROR(client_logger(), "client.connect: instance_id is required");
            pk.pack("payload");
            pk.pack_map(0);
            pk.pack("error");
            ipc::codec::pack_error(pk, "instance_id is required");
            return true;
        }
        auto host_obj = ipc::codec::find_key(payload, "host");
        auto port_obj = ipc::codec::find_key(payload, "port");
        auto cfg_obj = ipc::codec::find_key(payload, "config");
        if (!host_obj || !port_obj) {
            LOG4CPLUS_ERROR(client_logger(), "client.connect invalid request");
            pk.pack("payload");
            pk.pack_map(0);
            pk.pack("error");
            ipc::codec::pack_error(pk, "Invalid request");
            return true;
        }

        std::string host = ipc::codec::as_string(*host_obj, "");
        int port = static_cast<int>(ipc::codec::as_int64(*port_obj, 102));

        LOG4CPLUS_INFO(client_logger(), "client.connect to " << host << ":" << port << " for instance " + instance_id);

        auto* inst = context.get_or_create_client_instance(instance_id);
        
        // 清理旧连接
        if (inst->connection) {
            IedConnection_close(inst->connection);
            IedConnection_destroy(inst->connection);
            inst->connection = nullptr;
        }
        
        inst->connection = IedConnection_create();
        inst->target_host = host;
        inst->target_port = port;
        IedConnection connection = inst->connection;
        
        if (cfg_obj && cfg_obj->type == msgpack::type::MAP) {
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
            pk.pack("payload");
            pk.pack_map(2);
            pk.pack("success");
            pk.pack(true);
            pk.pack("instance_id");
            pk.pack(instance_id);
            pk.pack("error");
            pk.pack_nil();
        } else {
            inst->connected = false;
            LOG4CPLUS_ERROR(client_logger(), "client.connect failed: " << IedClientError_toString(error));
            pk.pack("payload");
            pk.pack_map(0);
            pk.pack("error");
            ipc::codec::pack_error(pk, IedClientError_toString(error));
        }
        return true;
    }

    if (action == "client.disconnect") {
        std::lock_guard<std::mutex> lock(context.mutex);
        
        // 检查instance_id是否提供
        if (instance_id.empty()) {
            LOG4CPLUS_ERROR(client_logger(), "client.disconnect: instance_id is required");
            pk.pack("payload");
            pk.pack_map(0);
            pk.pack("error");
            ipc::codec::pack_error(pk, "instance_id is required");
            return true;
        }
        
        LOG4CPLUS_INFO(client_logger(), "client.disconnect requested for instance " + instance_id);
        
        auto* inst = context.get_client_instance(instance_id);
        if (inst && inst->connection) {
            IedConnection_close(inst->connection);
            IedConnection_destroy(inst->connection);
            inst->connection = nullptr;
            inst->connected = false;
            context.remove_client_instance(instance_id);
        }
        pk.pack("payload");
        ipc::codec::pack_success_payload(pk);
        pk.pack("error");
        pk.pack_nil();
        return true;
    }

    if (action == "client.browse") {
        std::lock_guard<std::mutex> lock(context.mutex);
        
        // 检查instance_id是否提供
        if (instance_id.empty()) {
            LOG4CPLUS_ERROR(client_logger(), "client.browse: instance_id is required");
            pk.pack("payload");
            pk.pack_map(0);
            pk.pack("error");
            ipc::codec::pack_error(pk, "instance_id is required");
            return true;
        }
        
        auto* inst = context.get_client_instance(instance_id);
        IedConnection connection = inst ? inst->connection : nullptr;
        std::string ied_name = inst ? inst->ied_name : "IED";
        
        if (!connection) {
            LOG4CPLUS_ERROR(client_logger(), "client.browse when not connected");
            pk.pack("payload");
            pk.pack_map(0);
            pk.pack("error");
            ipc::codec::pack_error(pk, "Client not connected");
        } else {
            LOG4CPLUS_DEBUG(client_logger(), "client.browse requested");
            pk.pack("payload");
            pk.pack_map(1);
            pk.pack("model");
            pack_model(pk, connection, ied_name);
            pk.pack("error");
            pk.pack_nil();
        }
        return true;
    }

    if (action == "client.read") {
        std::lock_guard<std::mutex> lock(context.mutex);
        
        // 检查instance_id是否提供
        if (instance_id.empty()) {
            LOG4CPLUS_ERROR(client_logger(), "client.read: instance_id is required");
            pk.pack("payload");
            pk.pack_map(0);
            pk.pack("error");
            ipc::codec::pack_error(pk, "instance_id is required");
            return true;
        }
        
        auto ref_obj = ipc::codec::find_key(payload, "reference");
        
        auto* inst = context.get_client_instance(instance_id);
        IedConnection connection = inst ? inst->connection : nullptr;
        
        if (!connection || !ref_obj) {
            LOG4CPLUS_ERROR(client_logger(), "client.read invalid request");
            pk.pack("payload");
            pk.pack_map(0);
            pk.pack("error");
            ipc::codec::pack_error(pk, "Invalid request");
            return true;
        }

        std::string reference = ipc::codec::as_string(*ref_obj, "");
        LOG4CPLUS_DEBUG(client_logger(), "client.read " << reference);
        std::vector<FunctionalConstraint> fcs = {IEC61850_FC_ST, IEC61850_FC_MX, IEC61850_FC_SP, IEC61850_FC_CF};
        IedClientError error = IED_ERROR_OK;
        MmsValue* value = nullptr;
        for (auto fc : fcs) {
            value = IedConnection_readObject(connection, &error, reference.c_str(), fc);
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
        return true;
    }

    if (action == "client.read_batch") {
        std::lock_guard<std::mutex> lock(context.mutex);
        
        // 检查instance_id是否提供
        if (instance_id.empty()) {
            LOG4CPLUS_ERROR(client_logger(), "client.read_batch: instance_id is required");
            pk.pack("payload");
            pk.pack_map(0);
            pk.pack("error");
            ipc::codec::pack_error(pk, "instance_id is required");
            return true;
        }
        
        auto refs_obj = ipc::codec::find_key(payload, "references");
        
        auto* inst = context.get_client_instance(instance_id);
        IedConnection connection = inst ? inst->connection : nullptr;
        
        if (!connection || !refs_obj || refs_obj->type != msgpack::type::ARRAY) {
            LOG4CPLUS_ERROR(client_logger(), "client.read_batch invalid request");
            pk.pack("payload");
            pk.pack_map(0);
            pk.pack("error");
            ipc::codec::pack_error(pk, "Invalid request");
            return true;
        }

        LOG4CPLUS_DEBUG(client_logger(), "client.read_batch requested");
        pk.pack("payload");
        pk.pack_map(1);
        pk.pack("values");
        pk.pack_map(refs_obj->via.array.size);

        for (uint32_t i = 0; i < refs_obj->via.array.size; ++i) {
            std::string reference = ipc::codec::as_string(refs_obj->via.array.ptr[i], "");
            pk.pack(reference);
            std::vector<FunctionalConstraint> fcs = {IEC61850_FC_ST, IEC61850_FC_MX, IEC61850_FC_SP, IEC61850_FC_CF};
            IedClientError error = IED_ERROR_OK;
            MmsValue* value = nullptr;
            for (auto fc : fcs) {
                value = IedConnection_readObject(connection, &error, reference.c_str(), fc);
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
        return true;
    }

    if (action == "client.write") {
        std::lock_guard<std::mutex> lock(context.mutex);
        
        // 检查instance_id是否提供
        if (instance_id.empty()) {
            LOG4CPLUS_ERROR(client_logger(), "client.write: instance_id is required");
            pk.pack("payload");
            pk.pack_map(0);
            pk.pack("error");
            ipc::codec::pack_error(pk, "instance_id is required");
            return true;
        }
        
        auto ref_obj = ipc::codec::find_key(payload, "reference");
        auto value_obj = ipc::codec::find_key(payload, "value");
        
        auto* inst = context.get_client_instance(instance_id);
        IedConnection connection = inst ? inst->connection : nullptr;
        
        if (!connection || !ref_obj || !value_obj) {
            LOG4CPLUS_ERROR(client_logger(), "client.write invalid request");
            pk.pack("payload");
            pk.pack_map(0);
            pk.pack("error");
            ipc::codec::pack_error(pk, "Invalid request");
            return true;
        }

        std::string reference = ipc::codec::as_string(*ref_obj, "");
        LOG4CPLUS_DEBUG(client_logger(), "client.write " << reference);
        IedClientError error = IED_ERROR_OK;
        bool success = false;
        if (value_obj->type == msgpack::type::BOOLEAN) {
            std::vector<FunctionalConstraint> fcs = {IEC61850_FC_SP, IEC61850_FC_CF, IEC61850_FC_ST, IEC61850_FC_MX};
            for (auto fc : fcs) {
                IedConnection_writeBooleanValue(connection, &error, reference.c_str(), fc, value_obj->via.boolean);
                if (error == IED_ERROR_OK) {
                    success = true;
                    break;
                }
            }
        } else if (value_obj->type == msgpack::type::FLOAT32 || value_obj->type == msgpack::type::FLOAT64) {
            double v = value_obj->via.f64;
            std::vector<FunctionalConstraint> fcs = {IEC61850_FC_SP, IEC61850_FC_CF, IEC61850_FC_ST, IEC61850_FC_MX};
            for (auto fc : fcs) {
                IedConnection_writeFloatValue(connection, &error, reference.c_str(), fc, static_cast<float>(v));
                if (error == IED_ERROR_OK) {
                    success = true;
                    break;
                }
            }
        } else if (value_obj->type == msgpack::type::STR) {
            std::string value = ipc::codec::as_string(*value_obj, "");
            std::vector<FunctionalConstraint> fcs = {IEC61850_FC_SP, IEC61850_FC_CF, IEC61850_FC_ST, IEC61850_FC_MX};
            for (auto fc : fcs) {
                IedConnection_writeVisibleStringValue(connection, &error, reference.c_str(), fc, const_cast<char*>(value.c_str()));
                if (error == IED_ERROR_OK) {
                    success = true;
                    break;
                }
            }
        } else {
            int64_t v = ipc::codec::as_int64(*value_obj);
            std::vector<FunctionalConstraint> fcs = {IEC61850_FC_SP, IEC61850_FC_CF, IEC61850_FC_ST, IEC61850_FC_MX};
            for (auto fc : fcs) {
                IedConnection_writeInt32Value(connection, &error, reference.c_str(), fc, static_cast<int32_t>(v));
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
            LOG4CPLUS_INFO(client_logger(), "client.write success");
            pk.pack_nil();
        } else {
            LOG4CPLUS_ERROR(client_logger(), "client.write failed: " << IedClientError_toString(error));
            ipc::codec::pack_error(pk, IedClientError_toString(error));
        }
        return true;
    }
    
    if (action == "client.list_instances") {
        std::lock_guard<std::mutex> lock(context.mutex);
        LOG4CPLUS_DEBUG(client_logger(), "client.list_instances requested");
        
        pk.pack("payload");
        pk.pack_map(1);
        pk.pack("instances");
        pk.pack_array(context.client_instances.size());
        
        for (const auto& [id, inst] : context.client_instances) {
            pk.pack_map(4);
            pk.pack("instance_id");
            pk.pack(id);
            pk.pack("state");
            pk.pack(inst->connected ? "CONNECTED" : "DISCONNECTED");
            pk.pack("target_host");
            pk.pack(inst->target_host);
            pk.pack("target_port");
            pk.pack(inst->target_port);
        }
        
        pk.pack("error");
        pk.pack_nil();
        return true;
    }

    return false;
}

} // namespace ipc::actions
