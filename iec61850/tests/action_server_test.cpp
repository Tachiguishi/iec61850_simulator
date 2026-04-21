#include <gtest/gtest.h>

#include "action/action.hpp"
#include "logger.hpp"
#include "nlohmann_json.hpp"
#include "test_helpers.hpp"

#include <iec61850_dynamic_model.h>
#include <iec61850_model.h>

#include <mutex>
#include <string>
#include <unordered_set>
#include <vector>

namespace {

std::string get_error_message(const nlohmann::json& response) {
    auto error_it = response.find("error");
    if (error_it == response.end() || error_it->is_null() || !error_it->is_object()) {
        return "";
    }
    return error_it->value("message", "");
}

bool get_success_flag(const nlohmann::json& response) {
    auto result_it = response.find("result");
    if (result_it == response.end() || !result_it->is_object()) {
        return false;
    }
    return result_it->value("success", false);
}

void assert_fcdas(DataSet* data_set, const std::unordered_set<std::string>& expected) {
    ASSERT_NE(data_set, nullptr);
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
}

class LoggingEnvironment final : public ::testing::Environment {
public:
    void SetUp() override {
        static std::once_flag once;
        std::call_once(once, []() { init_logging("../src/log4cplus.ini"); });
    }
};

::testing::Environment* const kLoggingEnvironment = ::testing::AddGlobalTestEnvironment(new LoggingEnvironment());

class ActionServerSharedContextTest : public ::testing::Test {
protected:
    static BackendContext context;
};

BackendContext ActionServerSharedContextTest::context;

} // namespace

TEST(ActionServer, StartMissingPayloadReturnsError) {
    BackendContext context;
    nlohmann::json response = execute_action_json("server.start", context);

    EXPECT_EQ(get_error_message(response), "Missing payload");
}

TEST(ActionServer, LoadModelMissingPayloadReturnsError) {
    BackendContext context;
    nlohmann::json response = execute_action_json("server.load_model", context);

    EXPECT_EQ(get_error_message(response), "Missing payload");
}

TEST_F(ActionServerSharedContextTest, LoadDefaultModelReturnsSuccess) {

        auto payload_handle = pack_msgpack_object([](msgpack::packer<msgpack::sbuffer>& pk) {
      pack_default_model_payload(pk);
    });

        nlohmann::json response = execute_action_json("server.load_model", context, payload_handle.get());

    EXPECT_TRUE(get_success_flag(response));
    EXPECT_EQ(get_error_message(response), "");
}

TEST_F(ActionServerSharedContextTest, LoadReportModelReturnsSuccess) {

    auto payload_handle = pack_msgpack_object([](msgpack::packer<msgpack::sbuffer>& pk) {
        pack_payload_from_json_file(pk, "report_goose_ied.json");
    });

    nlohmann::json response = execute_action_json("server.load_model", context, payload_handle.get());

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
        "GenericIO/GGIO1.SPCSO1",
        "GenericIO/GGIO1.SPCSO2",
        "GenericIO/GGIO1.SPCSO3",
        "GenericIO/GGIO1.SPCSO4",
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
        "GenericIO/GGIO1.AnIn1",
        "GenericIO/GGIO1.AnIn2",
        "GenericIO/GGIO1.AnIn3",
        "GenericIO/GGIO1.AnIn4",
    };

    assert_fcdas(LogicalNode_getDataSet(lln0, "Events"), events_fcdas);
    assert_fcdas(LogicalNode_getDataSet(lln0, "Events2"), events2_fcdas);
    assert_fcdas(LogicalNode_getDataSet(lln0, "Events3"), events3_fcdas);
    assert_fcdas(LogicalNode_getDataSet(lln0, "AnalogValues"), analog_fcdas);

    auto* data_node = IedModel_getModelNodeByShortObjectReference(
        server->model, "GenericIO/GGIO1.SPCSO1.stVal");
    EXPECT_NE(data_node, nullptr);
}

TEST_F(ActionServerSharedContextTest, LoadControlModelReturnsSuccess) {

    auto payload_handle = pack_msgpack_object([](msgpack::packer<msgpack::sbuffer>& pk) {
        pack_payload_from_json_file(pk, "control_ied.json");
    });

    nlohmann::json response = execute_action_json("server.load_model", context, payload_handle.get());

    EXPECT_TRUE(get_success_flag(response));
    EXPECT_EQ(get_error_message(response), "");

    auto* server = context.get_server_instance("default_instance");
    ASSERT_NE(server, nullptr);
    ASSERT_NE(server->model, nullptr);

    auto* logical_device = IedModel_getDeviceByInst(server->model, "GenericIO");
    ASSERT_NE(logical_device, nullptr);

    auto* lln0 = LogicalDevice_getLogicalNode(logical_device, "LLN0");
    ASSERT_NE(lln0, nullptr);

    EXPECT_NE(LogicalNode_getDataSet(lln0, "ControlEvents"), nullptr);

    bool has_rcb = false;
    for (auto* rcb = server->model->rcbs; rcb; rcb = rcb->sibling) {
        if (rcb->parent == lln0 && rcb->name && std::string(rcb->name) == "ControlEventsRCB") {
            has_rcb = true;
            break;
        }
    }
    EXPECT_TRUE(has_rcb);

    bool has_gse = false;
    for (auto* gse = server->model->gseCBs; gse; gse = gse->sibling) {
        if (gse->parent == lln0) {
            has_gse = true;
            break;
        }
    }
    EXPECT_FALSE(has_gse);

    std::unordered_set<std::string> control_fcdas = {
        "GenericIO/GGIO1.SPCSO1.stVal",
        "GenericIO/GGIO1.SPCSO2.stVal",
        "GenericIO/GGIO1.SPCSO3.stVal",
        "GenericIO/GGIO1.SPCSO4.stVal",
        "GenericIO/GGIO1.SPCSO5.stVal",
        "GenericIO/GGIO1.SPCSO6.stVal",
        "GenericIO/GGIO1.SPCSO7.stVal",
        "GenericIO/GGIO1.SPCSO8.stVal",
        "GenericIO/GGIO1.SPCSO9.stVal",
        "GenericIO/GGIO1.SPCSO2.stSeld",
        "GenericIO/GGIO1.SPCSO2.opRcvd",
        "GenericIO/GGIO1.SPCSO2.opOk",
    };

    assert_fcdas(LogicalNode_getDataSet(lln0, "ControlEvents"), control_fcdas);

    auto* data_node = IedModel_getModelNodeByShortObjectReference(
        server->model, "GenericIO/GGIO1.SPCSO2.stSeld");
    EXPECT_NE(data_node, nullptr);
}

TEST_F(ActionServerSharedContextTest, LoadSettingGroupModelReturnsSuccess) {

    auto payload_handle = pack_msgpack_object([](msgpack::packer<msgpack::sbuffer>& pk) {
        pack_payload_from_json_file(pk, "setting_group_ied.json");
    });

    nlohmann::json response = execute_action_json("server.load_model", context, payload_handle.get());

    EXPECT_TRUE(get_success_flag(response));
    EXPECT_EQ(get_error_message(response), "");

    auto* server = context.get_server_instance("default_instance");
    ASSERT_NE(server, nullptr);
    ASSERT_NE(server->model, nullptr);

    auto* logical_device = IedModel_getDeviceByInst(server->model, "PROT");
    ASSERT_NE(logical_device, nullptr);

    auto* lln0 = LogicalDevice_getLogicalNode(logical_device, "LLN0");
    ASSERT_NE(lln0, nullptr);

    bool has_rcb = false;
    for (auto* rcb = server->model->rcbs; rcb; rcb = rcb->sibling) {
        if (rcb->parent == lln0) {
            has_rcb = true;
            break;
        }
    }
    EXPECT_FALSE(has_rcb);

    bool has_gse = false;
    for (auto* gse = server->model->gseCBs; gse; gse = gse->sibling) {
        if (gse->parent == lln0) {
            has_gse = true;
            break;
        }
    }
    EXPECT_FALSE(has_gse);

    EXPECT_EQ(LogicalNode_getDataSet(lln0, "SettingGroup"), nullptr);
    EXPECT_NE(LogicalDevice_getSettingGroupControlBlock(logical_device), nullptr);

    auto* data_node = IedModel_getModelNodeByShortObjectReference(
        server->model, "PROT/LLN0.Mod.stVal");
    EXPECT_NE(data_node, nullptr);
}

TEST(ActionServer, SetDataValueInvalidRequestReturnsError) {
    BackendContext context;

    auto payload_handle = pack_msgpack_object([](msgpack::packer<msgpack::sbuffer>& pk) {
        pk.pack_map(3);
        pk.pack("instance_id");
        pk.pack("default_instance");
        pk.pack("reference");
        pk.pack("PROT/XCBR1.Pos.stVal");
        pk.pack("value");
        pk.pack(1);
    });

    nlohmann::json response = execute_action_json("server.set_data_value", context, payload_handle.get());

    EXPECT_EQ(get_error_message(response), "Invalid request: missing server, model, reference, or value");
}

TEST(ActionServer, GetValuesInvalidRequestReturnsError) {
    BackendContext context;

    auto payload_handle = pack_msgpack_object([](msgpack::packer<msgpack::sbuffer>& pk) {
        pk.pack_map(2);
        pk.pack("instance_id");
        pk.pack("default_instance");
        pk.pack("references");
        pk.pack_array(1);
        pk.pack("PROT/XCBR1.Pos.stVal");
    });

    nlohmann::json response = execute_action_json("server.get_values", context, payload_handle.get());

    EXPECT_EQ(get_error_message(response), "Invalid request: missing server, model, or references array");
}

TEST(ActionServer, GetClientsReturnsPayload) {
    BackendContext context;
    ServerInstanceContext* server = context.get_or_create_server_instance("server-1");
    server->clients.push_back({"client-1", "2026-01-31T00:00:00Z"});

    auto payload_handle = pack_msgpack_object([](msgpack::packer<msgpack::sbuffer>& pk) {
        pk.pack_map(1);
        pk.pack("instance_id");
        pk.pack("server-1");
    });

    nlohmann::json response = execute_action_json("server.get_clients", context, payload_handle.get());

    ASSERT_TRUE(response.contains("result"));
    ASSERT_TRUE(response["result"].contains("clients"));
    ASSERT_TRUE(response["result"]["clients"].is_array());
    EXPECT_EQ(response["result"]["clients"].size(), 1u);
}

TEST(ActionServer, LoadModelAndStartServerReturnsSuccess) {
    BackendContext context;

    auto payload_handle = pack_msgpack_object([](msgpack::packer<msgpack::sbuffer>& pk) {
        pack_payload_from_json_file(pk, "report_goose_ied.json");
    });

    nlohmann::json response = execute_action_json("server.load_model", context, payload_handle.get());

    EXPECT_TRUE(get_success_flag(response));
    EXPECT_EQ(get_error_message(response), "");

    auto start_payload = pack_msgpack_object([](msgpack::packer<msgpack::sbuffer>& pk) {
        pk.pack_map(1);
        pk.pack("instance_id");
        pk.pack("default_instance");
    });

    response = execute_action_json("server.start", context, start_payload.get());

    EXPECT_TRUE(get_success_flag(response));
    EXPECT_EQ(get_error_message(response), "");

    // 检测服务器状态
    auto* server = context.get_server_instance("default_instance");
    ASSERT_NE(server, nullptr);
    EXPECT_TRUE(server->running);
}
