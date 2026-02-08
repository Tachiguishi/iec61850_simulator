#include <gtest/gtest.h>

#include "action/action.hpp"
#include "logger.hpp"
#include "msgpack_codec.hpp"
#include "test_helpers.hpp"

#include <iec61850_dynamic_model.h>
#include <iec61850_model.h>
#include <msgpack.hpp>

#include <functional>
#include <mutex>
#include <string>
#include <unordered_set>
#include <vector>

namespace {

msgpack::object_handle pack_map(const std::function<void(msgpack::packer<msgpack::sbuffer>&)>& pack_fn,
                                msgpack::sbuffer& buffer) {
    msgpack::packer<msgpack::sbuffer> pk(&buffer);
    pack_fn(pk);
    return msgpack::unpack(buffer.data(), buffer.size());
}

msgpack::object_handle make_payload(const std::function<void(msgpack::packer<msgpack::sbuffer>&)>& pack_fn) {
    msgpack::sbuffer buffer;
    return pack_map(pack_fn, buffer);
}

msgpack::object_handle execute_action(
    const std::string& action,
    BackendContext& context,
    const msgpack::object& payload,
    bool has_payload,
    msgpack::object& out_response) {
    msgpack::sbuffer request_buffer;
    msgpack::packer<msgpack::sbuffer> pk(&request_buffer);

    pk.pack_map(has_payload ? 3 : 2);
    pk.pack("id");
    pk.pack("test-id");
    pk.pack("action");
    pk.pack(action);
    if (has_payload) {
        pk.pack("payload");
        pk.pack(payload);
    }

    std::string request_bytes(request_buffer.data(), request_buffer.size());
    std::string response_bytes = ipc::actions::handle_action(request_bytes, context);
    auto response_handle = msgpack::unpack(response_bytes.data(), response_bytes.size());
    out_response = response_handle.get();
    return response_handle;
}

const msgpack::object* find_key(const msgpack::object& map_obj, const std::string& key) {
    return ipc::codec::find_key(map_obj, key);
}

std::string get_error_message(const msgpack::object& response) {
    const msgpack::object* error_obj = find_key(response, "error");
    if (!error_obj || error_obj->type != msgpack::type::MAP) {
        return "";
    }
    const msgpack::object* msg_obj = find_key(*error_obj, "message");
    if (!msg_obj) {
        return "";
    }
    return ipc::codec::as_string(*msg_obj, "");
}

bool get_success_flag(const msgpack::object& response) {
    const msgpack::object* payload_obj = find_key(response, "payload");
    if (!payload_obj || payload_obj->type != msgpack::type::MAP) {
        return false;
    }
    const msgpack::object* success_obj = find_key(*payload_obj, "success");
    if (!success_obj || success_obj->type != msgpack::type::BOOLEAN) {
        return false;
    }
    return success_obj->via.boolean;
}

class LoggingEnvironment final : public ::testing::Environment {
public:
    void SetUp() override {
        static std::once_flag once;
        std::call_once(once, []() { init_logging("../src/log4cplus.ini"); });
    }
};

::testing::Environment* const kLoggingEnvironment = ::testing::AddGlobalTestEnvironment(new LoggingEnvironment());

} // namespace

TEST(ActionServer, StartMissingPayloadReturnsError) {
    BackendContext context;
    msgpack::object dummy;
    msgpack::object response;

    execute_action("server.start", context, dummy, false, response);

    EXPECT_EQ(get_error_message(response), "Missing payload");
}

TEST(ActionServer, LoadModelMissingPayloadReturnsError) {
    BackendContext context;
    msgpack::object dummy;
    msgpack::object response;

    execute_action("server.load_model", context, dummy, false, response);

    EXPECT_EQ(get_error_message(response), "Missing payload");
}

TEST(ActionServer, LoadDefaultModelReturnsSuccess) {
    BackendContext context;

    auto payload_handle = make_payload([](msgpack::packer<msgpack::sbuffer>& pk) {
      pack_default_model_payload(pk);
    });

    msgpack::object response;
    execute_action("server.load_model", context, payload_handle.get(), true, response);

    EXPECT_TRUE(get_success_flag(response));
    EXPECT_EQ(get_error_message(response), "");
}

TEST(ActionServer, LoadReportModelReturnsSuccess) {
    BackendContext context;

    auto payload_handle = make_payload([](msgpack::packer<msgpack::sbuffer>& pk) {
        pack_payload_from_json_file(pk, "report_goose_ied.json");
    });

    msgpack::object response;
    execute_action("server.load_model", context, payload_handle.get(), true, response);

    EXPECT_TRUE(get_success_flag(response));
    EXPECT_EQ(get_error_message(response), "");

    auto* server = context.get_server_instance("default_instance");
    ASSERT_NE(server, nullptr);
    ASSERT_NE(server->model, nullptr);

    auto* logical_device = IedModel_getDeviceByInst(server->model, "GenericIO");
    ASSERT_NE(logical_device, nullptr);

    auto* lln0 = LogicalDevice_getLogicalNode(logical_device, "LLN0");
    ASSERT_NE(lln0, nullptr);

    const std::vector<std::string> data_set_names = {"Events", "Events2", "Events3", "AnalogValues"};
    for (const auto& name : data_set_names) {
        EXPECT_NE(LogicalNode_getDataSet(lln0, name.c_str()), nullptr);
    }

    auto has_rcb = [server, lln0](const std::string& name) {
        for (auto* rcb = server->model->rcbs; rcb; rcb = rcb->sibling) {
            if (rcb->parent == lln0 && rcb->name && name == rcb->name) {
                return true;
            }
        }
        return false;
    };

    auto has_gse = [server, lln0](const std::string& name) {
        for (auto* gse = server->model->gseCBs; gse; gse = gse->sibling) {
            if (gse->parent == lln0 && gse->name && name == gse->name) {
                return true;
            }
        }
        return false;
    };

    EXPECT_TRUE(has_rcb("EventsRCB"));
    EXPECT_TRUE(has_rcb("AnalogValuesRCB"));
    EXPECT_TRUE(has_gse("gcbEvents"));
    EXPECT_TRUE(has_gse("gcbAnalogValues"));

    std::unordered_set<std::string> events_fcdas = {
        "GenericIO/GGIO1.SPCSO1.stVal",
        "GenericIO/GGIO1.SPCSO2.stVal",
        "GenericIO/GGIO1.SPCSO3.stVal",
        "GenericIO/GGIO1.SPCSO4.stVal",
    };
    std::unordered_set<std::string> events2_fcdas = {
        "GenericIO/GGIO1.SPCSO1.",
        "GenericIO/GGIO1.SPCSO2.",
        "GenericIO/GGIO1.SPCSO3.",
        "GenericIO/GGIO1.SPCSO4.",
    };
    std::unordered_set<std::string> events3_fcdas = {
        "GenericIO/GGIO1.SPCSO1.stVal",
        "GenericIO/GGIO1.SPCSO1.q",
        "GenericIO/GGIO1.SPCSO2.stVal",
        "GenericIO/GGIO1.SPCSO2.q",
        "GenericIO/GGIO1.SPCSO3.stVal",
        "GenericIO/GGIO1.SPCSO3.q",
        "GenericIO/GGIO1.SPCSO4.stVal",
        "GenericIO/GGIO1.SPCSO4.q",
    };
    std::unordered_set<std::string> analog_fcdas = {
        "GenericIO/GGIO1.AnIn1.",
        "GenericIO/GGIO1.AnIn2.",
        "GenericIO/GGIO1.AnIn3.",
        "GenericIO/GGIO1.AnIn4.",
    };

    auto assert_fcdas = [](DataSet* data_set, const std::unordered_set<std::string>& expected) {
        std::unordered_set<std::string> actual;
        for (auto* entry = DataSet_getFirstEntry(data_set); entry; entry = DataSetEntry_getNext(entry)) {
            std::string ref = entry->logicalDeviceName ? entry->logicalDeviceName : "";
            ref += "/";
            ref += entry->variableName ? entry->variableName : "";
            if (entry->index >= 0) {
                ref += "[" + std::to_string(entry->index) + "]";
            }
            if (entry->componentName) {
                ref += ".";
                ref += entry->componentName;
            }
            actual.insert(ref);
        }
        EXPECT_EQ(actual, expected);
    };

    assert_fcdas(LogicalNode_getDataSet(lln0, "Events"), events_fcdas);
    assert_fcdas(LogicalNode_getDataSet(lln0, "Events2"), events2_fcdas);
    assert_fcdas(LogicalNode_getDataSet(lln0, "Events3"), events3_fcdas);
    assert_fcdas(LogicalNode_getDataSet(lln0, "AnalogValues"), analog_fcdas);

    auto* data_node = IedModel_getModelNodeByShortObjectReference(
        server->model, "GenericIO/GGIO1.SPCSO1.stVal");
    EXPECT_NE(data_node, nullptr);
}

TEST(ActionServer, LoadControlModelReturnsSuccess) {
    BackendContext context;

    auto payload_handle = make_payload([](msgpack::packer<msgpack::sbuffer>& pk) {
        pack_payload_from_json_file(pk, "control_ied.json");
    });

    msgpack::object response;
    execute_action("server.load_model", context, payload_handle.get(), true, response);

    EXPECT_TRUE(get_success_flag(response));
    EXPECT_EQ(get_error_message(response), "");
}

TEST(ActionServer, LoadSettingGroupModelReturnsSuccess) {
    BackendContext context;

    auto payload_handle = make_payload([](msgpack::packer<msgpack::sbuffer>& pk) {
        pack_payload_from_json_file(pk, "setting_group_ied.json");
    });

    msgpack::object response;
    execute_action("server.load_model", context, payload_handle.get(), true, response);

    EXPECT_TRUE(get_success_flag(response));
    EXPECT_EQ(get_error_message(response), "");
}

TEST(ActionServer, SetDataValueInvalidRequestReturnsError) {
    BackendContext context;

    auto payload_handle = make_payload([](msgpack::packer<msgpack::sbuffer>& pk) {
        pk.pack_map(3);
        pk.pack("instance_id");
        pk.pack("default_instance");
        pk.pack("reference");
        pk.pack("PROT/XCBR1.Pos.stVal");
        pk.pack("value");
        pk.pack(1);
    });

    msgpack::object response;
    execute_action("server.set_data_value", context, payload_handle.get(), true, response);

    EXPECT_EQ(get_error_message(response), "Invalid request: missing server, model, reference, or value");
}

TEST(ActionServer, GetValuesInvalidRequestReturnsError) {
    BackendContext context;

    auto payload_handle = make_payload([](msgpack::packer<msgpack::sbuffer>& pk) {
        pk.pack_map(2);
        pk.pack("instance_id");
        pk.pack("default_instance");
        pk.pack("references");
        pk.pack_array(1);
        pk.pack("PROT/XCBR1.Pos.stVal");
    });

    msgpack::object response;
    execute_action("server.get_values", context, payload_handle.get(), true, response);

    EXPECT_EQ(get_error_message(response), "Invalid request: missing server, model, or references array");
}

TEST(ActionServer, GetClientsReturnsPayload) {
    BackendContext context;
    ServerInstanceContext* server = context.get_or_create_server_instance("server-1");
    server->clients.push_back({"client-1", "2026-01-31T00:00:00Z"});

    auto payload_handle = make_payload([](msgpack::packer<msgpack::sbuffer>& pk) {
        pk.pack_map(1);
        pk.pack("instance_id");
        pk.pack("server-1");
    });

    msgpack::object response;
    execute_action("server.get_clients", context, payload_handle.get(), true, response);

    const msgpack::object* payload_obj = find_key(response, "payload");
    ASSERT_TRUE(payload_obj);
    const msgpack::object* clients_obj = find_key(*payload_obj, "clients");
    ASSERT_TRUE(clients_obj);
    ASSERT_EQ(clients_obj->type, msgpack::type::ARRAY);
    EXPECT_EQ(clients_obj->via.array.size, 1u);
}
