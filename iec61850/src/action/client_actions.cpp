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

std::string extract_instance_id(const msgpack::object& payload) {
    if (auto id_obj = ipc::codec::find_key(payload, "instance_id")) {
        std::string id = ipc::codec::as_string(*id_obj, "");
        if (!id.empty()) {
            return id;
        }
    }
    return "";
}

bool require_instance_id(const msgpack::object& payload,
                         const std::string& action,
                         msgpack::packer<msgpack::sbuffer>& pk,
                         std::string& instance_id) {
    instance_id = extract_instance_id(payload);
    if (instance_id.empty()) {
        LOG4CPLUS_ERROR(client_logger(), action << ": instance_id is required");
        pk.pack("payload");
        pk.pack_map(0);
        pk.pack("error");
        ipc::codec::pack_error(pk, "instance_id is required");
        return false;
    }
    return true;
}

} // namespace

namespace ipc::actions {

class ClientConnectAction final : public ActionHandler {
public:
    const char* name() const override { return "client.connect"; }

    bool handle(ActionContext& ctx, msgpack::packer<msgpack::sbuffer>& pk) override {
        std::lock_guard<std::mutex> lock(ctx.context.mutex);

        std::string instance_id;
        if (!require_instance_id(ctx.payload, ctx.action, pk, instance_id)) {
            return true;
        }

        auto host_obj = ipc::codec::find_key(ctx.payload, "host");
        auto port_obj = ipc::codec::find_key(ctx.payload, "port");
        auto cfg_obj = ipc::codec::find_key(ctx.payload, "config");
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
};

class ClientDisconnectAction final : public ActionHandler {
public:
    const char* name() const override { return "client.disconnect"; }

    bool handle(ActionContext& ctx, msgpack::packer<msgpack::sbuffer>& pk) override {
        std::lock_guard<std::mutex> lock(ctx.context.mutex);

        std::string instance_id;
        if (!require_instance_id(ctx.payload, ctx.action, pk, instance_id)) {
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
        pk.pack("payload");
        ipc::codec::pack_success_payload(pk);
        pk.pack("error");
        pk.pack_nil();
        return true;
    }
};

class ClientBrowseAction final : public ActionHandler {
public:
    const char* name() const override { return "client.browse"; }

    bool handle(ActionContext& ctx, msgpack::packer<msgpack::sbuffer>& pk) override {
        std::lock_guard<std::mutex> lock(ctx.context.mutex);

        std::string instance_id;
        if (!require_instance_id(ctx.payload, ctx.action, pk, instance_id)) {
            return true;
        }

        auto* inst = ctx.context.get_client_instance(instance_id);
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
};

class ClientReadAction final : public ActionHandler {
public:
    const char* name() const override { return "client.read"; }

    bool handle(ActionContext& ctx, msgpack::packer<msgpack::sbuffer>& pk) override {
        std::lock_guard<std::mutex> lock(ctx.context.mutex);

        std::string instance_id;
        if (!require_instance_id(ctx.payload, ctx.action, pk, instance_id)) {
            return true;
        }

        auto ref_obj = ipc::codec::find_key(ctx.payload, "reference");

        auto* inst = ctx.context.get_client_instance(instance_id);
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
};

class ClientReadBatchAction final : public ActionHandler {
public:
    const char* name() const override { return "client.read_batch"; }

    bool handle(ActionContext& ctx, msgpack::packer<msgpack::sbuffer>& pk) override {
        std::lock_guard<std::mutex> lock(ctx.context.mutex);

        std::string instance_id;
        if (!require_instance_id(ctx.payload, ctx.action, pk, instance_id)) {
            return true;
        }

        auto refs_obj = ipc::codec::find_key(ctx.payload, "references");

        auto* inst = ctx.context.get_client_instance(instance_id);
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
};

class ClientWriteAction final : public ActionHandler {
public:
    const char* name() const override { return "client.write"; }

    bool handle(ActionContext& ctx, msgpack::packer<msgpack::sbuffer>& pk) override {
        std::lock_guard<std::mutex> lock(ctx.context.mutex);

        std::string instance_id;
        if (!require_instance_id(ctx.payload, ctx.action, pk, instance_id)) {
            return true;
        }

        auto ref_obj = ipc::codec::find_key(ctx.payload, "reference");
        auto value_obj = ipc::codec::find_key(ctx.payload, "value");

        auto* inst = ctx.context.get_client_instance(instance_id);
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
};

class ClientListInstancesAction final : public ActionHandler {
public:
    const char* name() const override { return "client.list_instances"; }

    bool handle(ActionContext& ctx, msgpack::packer<msgpack::sbuffer>& pk) override {
        std::lock_guard<std::mutex> lock(ctx.context.mutex);
        LOG4CPLUS_DEBUG(client_logger(), "client.list_instances requested");

        pk.pack("payload");
        pk.pack_map(1);
        pk.pack("instances");
        pk.pack_array(ctx.context.client_instances.size());

        for (const auto& entry : ctx.context.client_instances) {
            const auto& id = entry.first;
            const auto& inst = entry.second;
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
