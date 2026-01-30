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

namespace ipc::actions {

bool handle_client_action(
    const std::string& action,
    BackendContext& context,
    const msgpack::object& payload,
    bool,
    msgpack::packer<msgpack::sbuffer>& pk) {
    if (action == "client.connect") {
        std::lock_guard<std::mutex> lock(context.mutex);
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

        LOG4CPLUS_INFO(client_logger(), "client.connect to " << host << ":" << port);

        if (context.client_connection) {
            IedConnection_destroy(context.client_connection);
            context.client_connection = nullptr;
        }

        context.client_connection = IedConnection_create();
        if (cfg_obj && cfg_obj->type == msgpack::type::MAP) {
            if (auto timeout_obj = ipc::codec::find_key(*cfg_obj, "timeout_ms")) {
                IedConnection_setConnectTimeout(context.client_connection, static_cast<int>(ipc::codec::as_int64(*timeout_obj, 5000)));
                IedConnection_setRequestTimeout(context.client_connection, static_cast<int>(ipc::codec::as_int64(*timeout_obj, 5000)));
            }
        }

        IedClientError error = IED_ERROR_OK;
        IedConnection_connect(context.client_connection, &error, host.c_str(), port);
        if (error == IED_ERROR_OK) {
            LOG4CPLUS_INFO(client_logger(), "client.connect success");
            pk.pack("payload");
            ipc::codec::pack_success_payload(pk);
            pk.pack("error");
            pk.pack_nil();
        } else {
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
        LOG4CPLUS_INFO(client_logger(), "client.disconnect requested");
        if (context.client_connection) {
            IedConnection_close(context.client_connection);
            IedConnection_destroy(context.client_connection);
            context.client_connection = nullptr;
        }
        pk.pack("payload");
        ipc::codec::pack_success_payload(pk);
        pk.pack("error");
        pk.pack_nil();
        return true;
    }

    if (action == "client.browse") {
        std::lock_guard<std::mutex> lock(context.mutex);
        if (!context.client_connection) {
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
            pack_model(pk, context.client_connection, context.client_ied_name);
            pk.pack("error");
            pk.pack_nil();
        }
        return true;
    }

    if (action == "client.read") {
        std::lock_guard<std::mutex> lock(context.mutex);
        auto ref_obj = ipc::codec::find_key(payload, "reference");
        if (!context.client_connection || !ref_obj) {
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
            value = IedConnection_readObject(context.client_connection, &error, reference.c_str(), fc);
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
        auto refs_obj = ipc::codec::find_key(payload, "references");
        if (!context.client_connection || !refs_obj || refs_obj->type != msgpack::type::ARRAY) {
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
                value = IedConnection_readObject(context.client_connection, &error, reference.c_str(), fc);
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
        auto ref_obj = ipc::codec::find_key(payload, "reference");
        auto value_obj = ipc::codec::find_key(payload, "value");
        if (!context.client_connection || !ref_obj || !value_obj) {
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
                IedConnection_writeBooleanValue(context.client_connection, &error, reference.c_str(), fc, value_obj->via.boolean);
                if (error == IED_ERROR_OK) {
                    success = true;
                    break;
                }
            }
        } else if (value_obj->type == msgpack::type::FLOAT32 || value_obj->type == msgpack::type::FLOAT64) {
            double v = value_obj->via.f64;
            std::vector<FunctionalConstraint> fcs = {IEC61850_FC_SP, IEC61850_FC_CF, IEC61850_FC_ST, IEC61850_FC_MX};
            for (auto fc : fcs) {
                IedConnection_writeFloatValue(context.client_connection, &error, reference.c_str(), fc, static_cast<float>(v));
                if (error == IED_ERROR_OK) {
                    success = true;
                    break;
                }
            }
        } else if (value_obj->type == msgpack::type::STR) {
            std::string value = ipc::codec::as_string(*value_obj, "");
            std::vector<FunctionalConstraint> fcs = {IEC61850_FC_SP, IEC61850_FC_CF, IEC61850_FC_ST, IEC61850_FC_MX};
            for (auto fc : fcs) {
                IedConnection_writeVisibleStringValue(context.client_connection, &error, reference.c_str(), fc, const_cast<char*>(value.c_str()));
                if (error == IED_ERROR_OK) {
                    success = true;
                    break;
                }
            }
        } else {
            int64_t v = ipc::codec::as_int64(*value_obj);
            std::vector<FunctionalConstraint> fcs = {IEC61850_FC_SP, IEC61850_FC_CF, IEC61850_FC_ST, IEC61850_FC_MX};
            for (auto fc : fcs) {
                IedConnection_writeInt32Value(context.client_connection, &error, reference.c_str(), fc, static_cast<int32_t>(v));
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

    return false;
}

} // namespace ipc::actions
