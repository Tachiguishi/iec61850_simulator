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

class ActionServerModelTest : public ::testing::Test {
protected:
    BackendContext context;
};

class ActionServerOperationTest : public ::testing::Test {
protected:
    BackendContext context;

    void SetUp() override {
        nlohmann::json response = execute_action_json("server.load_model", context, load_model_payload_from_file("report_goose_ied.json", false));
        ASSERT_TRUE(get_success_flag(response)) << "Failed to load model: " << get_error_message(response);
    }
};

} // namespace

TEST_F(ActionServerModelTest, LoadDefaultModelReturnsSuccess) {
    nlohmann::json response = execute_action_json("server.load_model", context, load_model_payload_from_file("default_ied.json", true));

    EXPECT_TRUE(get_success_flag(response));
    EXPECT_EQ(get_error_message(response), "");
}

TEST_F(ActionServerModelTest, ReloadModelReplacesExistingModel) {
    nlohmann::json response1 = execute_action_json("server.load_model", context, load_model_payload_from_file("default_ied.json", true));
    EXPECT_TRUE(get_success_flag(response1));
    EXPECT_EQ(get_error_message(response1), "");

    auto* inst = context.get_server_instance("default_instance");
    ASSERT_NE(inst, nullptr);
    ASSERT_NE(inst->model, nullptr);

    auto* original_model = inst->model;

    nlohmann::json response2 = execute_action_json("server.load_model", context, load_model_payload_from_file("report_goose_ied.json", true));
    EXPECT_TRUE(get_success_flag(response2));
    EXPECT_EQ(get_error_message(response2), "");

    ASSERT_NE(inst->model, nullptr);
    EXPECT_NE(inst->model, original_model);
}

TEST_F(ActionServerModelTest, LoadReportModelReturnsSuccess) {
    nlohmann::json response = execute_action_json("server.load_model", context, load_model_payload_from_file("report_goose_ied.json", true));

    EXPECT_TRUE(get_success_flag(response));
    EXPECT_EQ(get_error_message(response), "");

    auto* inst = context.get_server_instance("default_instance");
    ASSERT_NE(inst, nullptr);
    ASSERT_NE(inst->model, nullptr);

    auto* logical_device = IedModel_getDeviceByInst(inst->model, "GenericIO");
    ASSERT_NE(logical_device, nullptr);

    auto* lln0 = LogicalDevice_getLogicalNode(logical_device, "LLN0");
    ASSERT_NE(lln0, nullptr);

    const std::vector<std::string> data_set_names = {"Events", "Events2", "Events3", "AnalogValues"};
    for (const auto& name : data_set_names) {
        EXPECT_NE(LogicalNode_getDataSet(lln0, name.c_str()), nullptr);
    }

    auto has_rcb = [inst, lln0](const std::string& name) {
        for (auto* rcb = inst->model->rcbs; rcb; rcb = rcb->sibling) {
            if (rcb->parent == lln0 && rcb->name && name == rcb->name) {
                return true;
            }
        }
        return false;
    };

    auto has_gse = [inst, lln0](const std::string& name) {
        for (auto* gse = inst->model->gseCBs; gse; gse = gse->sibling) {
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
        inst->model, "GenericIO/GGIO1.SPCSO1.stVal");
    EXPECT_NE(data_node, nullptr);
}

TEST_F(ActionServerModelTest, LoadControlModelReturnsSuccess) {

    nlohmann::json response = execute_action_json("server.load_model", context, load_model_payload_from_file("control_ied.json", true));

    EXPECT_TRUE(get_success_flag(response));
    EXPECT_EQ(get_error_message(response), "");

    auto* inst = context.get_server_instance("default_instance");
    ASSERT_NE(inst, nullptr);
    ASSERT_NE(inst->model, nullptr);

    auto* logical_device = IedModel_getDeviceByInst(inst->model, "GenericIO");
    ASSERT_NE(logical_device, nullptr);

    auto* lln0 = LogicalDevice_getLogicalNode(logical_device, "LLN0");
    ASSERT_NE(lln0, nullptr);

    EXPECT_NE(LogicalNode_getDataSet(lln0, "ControlEvents"), nullptr);

    bool has_rcb = false;
    for (auto* rcb = inst->model->rcbs; rcb; rcb = rcb->sibling) {
        if (rcb->parent == lln0 && rcb->name && std::string(rcb->name) == "ControlEventsRCB") {
            has_rcb = true;
            break;
        }
    }
    EXPECT_TRUE(has_rcb);

    bool has_gse = false;
    for (auto* gse = inst->model->gseCBs; gse; gse = gse->sibling) {
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
        inst->model, "GenericIO/GGIO1.SPCSO2.stSeld");
    EXPECT_NE(data_node, nullptr);
}

TEST_F(ActionServerModelTest, LoadSettingGroupModelReturnsSuccess) {
    nlohmann::json response = execute_action_json("server.load_model", context, load_model_payload_from_file("setting_group_ied.json", false));

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

TEST_F(ActionServerModelTest, StartServerReturnsSuccess) {
    nlohmann::json response0 = execute_action_json("server.load_model", context, load_model_payload_from_file("default_ied.json", false));
    nlohmann::json response = execute_action_json("server.start", context, {
        {"instance_id", "default_instance"},
        {"config", {
            {"ip_address", "192.168.8.100"},
            {"port", 102},
            {"max_connections", 5},
        }}
    });

    EXPECT_TRUE(get_success_flag(response));
    EXPECT_EQ(get_error_message(response), "");

    // 检测服务器状态
    auto* server = context.get_server_instance("default_instance");
    ASSERT_NE(server, nullptr);
    EXPECT_TRUE(server->running);
}

TEST_F(ActionServerModelTest, StartMissingPayloadReturnsError) {
    nlohmann::json response = execute_action_json("server.start", context);

    EXPECT_EQ(get_error_message(response), "Missing payload");
}

TEST_F(ActionServerOperationTest, ReadValuesInvalidRequestReturnsError) {
    BackendContext localContext;
    nlohmann::json payload = {
        {"instance_id", "default_instance"},
        {"items", nlohmann::json::array({{{"reference", "PROT/XCBR1.Pos.stVal"}}})}
    };
    nlohmann::json response = execute_action_json("server.read", localContext, payload);

    EXPECT_EQ(get_error_message(response), "Invalid request: missing server, model, or references array");
}

TEST_F(ActionServerOperationTest, ReadValuesNonExistentReferenceReturnsError) {
    nlohmann::json payload = {
        {"instance_id", "default_instance"},
        {"items", nlohmann::json::array({
                {
                    {"reference", "simpleIOGenericIO/GGIO1.NonExistent"}
                },
                {
                    {"reference", "simpleIOGenericIO/GGIO1.AnIn1"},
                    {"fc", "ST"}
                }
            })
        }
    };

    nlohmann::json response = execute_action_json("server.read", context, payload);

    EXPECT_EQ(get_error_message(response), "");
    ASSERT_TRUE(response.contains("result")) << "Response does not contain 'result': " << response.dump(2);
    ASSERT_TRUE(response["result"].is_array()) << "'result' is not an array: " << response.dump(2);
    ASSERT_EQ(response["result"].size(), 2u) << "Expected 2 items in 'result', got " << response["result"].size() << ": " << response.dump(2);
    EXPECT_EQ(response["result"][0]["reference"], "simpleIOGenericIO/GGIO1.NonExistent") << "Reference in response does not match request: " << response.dump(2);
    EXPECT_EQ(response["result"][0]["error"], "Reference not found") << "Expected error message for non-existent reference: " << response.dump(2);

    EXPECT_EQ(response["result"][1]["reference"], "simpleIOGenericIO/GGIO1.AnIn1") << "Reference in response does not match request: " << response.dump(2);
    EXPECT_EQ(response["result"][1]["fc"], "ST") << "Functional constraint in response does not match request: " << response.dump(2);
    EXPECT_EQ(response["result"][1]["error"], "Failed to read value for reference with functional constraint: ST") << "Expected error message for valid reference with unsupported functional constraint: " << response.dump(2);
    EXPECT_FALSE(response["result"][1].contains("value")) << "Did not expect value for valid reference with missing value: " << response.dump(2);
}

/*
 *
{
  "id": "test-id",
  "result": [
    {
      "fc": "MX",
      "reference": "simpleIOGenericIO/GGIO1.AnIn1",
      "value": {
        "mag": {
          "f": 0.0
        },
        "q": "0000000000000",
        "t": "19700101000000.000Z"
      }
    },
    {
      "fc": "ST",
      "reference": "simpleIOGenericIO/GGIO1.SPCSO1",
      "value": {
        "q": "0000000000000",
        "stVal": false,
        "t": "19700101000000.000Z"
      }
    },
    {
      "fc": "ST",
      "reference": "simpleIOGenericIO/GGIO1.SPCSO1.q",
      "value": "0000000000000"
    }
  ]
}
 */
TEST_F(ActionServerOperationTest, ReadValuesValidReferenceReturnsValue) {
    nlohmann::json payload = {
        {"instance_id", "default_instance"},
        {"items", nlohmann::json::array({
            {
                {"reference", "simpleIOGenericIO/GGIO1.AnIn1"},
                {"fc", "MX"}
            },
            {
                {"reference", "simpleIOGenericIO/GGIO1.SPCSO1"},
                {"fc", "ST"}
            },
            {
                {"reference", "simpleIOGenericIO/GGIO1.SPCSO1.q"},
                {"fc", "ST"}
            }
        })}
    };
    nlohmann::json response = execute_action_json("server.read", context, payload);

    EXPECT_EQ(get_error_message(response), "");
    ASSERT_TRUE(response.contains("result")) << "Response does not contain 'result': " << response.dump(2);
    ASSERT_TRUE(response["result"].is_array()) << "'result' is not an array: " << response.dump(2);
    ASSERT_EQ(response["result"].size(), 3u) << "Expected 3 items in 'result', got " << response["result"].size() << ": " << response.dump(2);
    ASSERT_EQ(response["result"][0]["reference"], "simpleIOGenericIO/GGIO1.AnIn1") << "Reference in response does not match request: " << response.dump(2);
    ASSERT_EQ(response["result"][0]["fc"], "MX") << "Functional constraint in response does not match request: " << response.dump(2);
    ASSERT_FALSE(response["result"][0].contains("error")) << "Did not expect error for valid reference: " << response.dump(2);
    ASSERT_TRUE(response["result"][0].contains("value")) << "Response item does not contain 'value': " << response.dump(2); 

    ASSERT_EQ(response["result"][1]["reference"], "simpleIOGenericIO/GGIO1.SPCSO1") << "Reference in response does not match request: " << response.dump(2);
    ASSERT_EQ(response["result"][1]["fc"], "ST") << "Functional constraint in response does not match request: " << response.dump(2);
    ASSERT_FALSE(response["result"][1].contains("error")) << "Did not expect error for valid reference: " << response.dump(2);
    ASSERT_TRUE(response["result"][1].contains("value")) << "Response item does not contain 'value': " << response.dump(2);

    ASSERT_EQ(response["result"][2]["reference"], "simpleIOGenericIO/GGIO1.SPCSO1.q") << "Reference in response does not match request: " << response.dump(2);
    ASSERT_EQ(response["result"][2]["fc"], "ST") << "Functional constraint in response does not match request: " << response.dump(2);
    ASSERT_FALSE(response["result"][2].contains("error")) << "Did not expect error for valid reference: " << response.dump(2);
    ASSERT_TRUE(response["result"][2].contains("value")) << "Response item does not contain 'value': " << response.dump(2);
}

TEST_F(ActionServerOperationTest, WriteValuesInvalidRequestReturnsError) {
    BackendContext localContext;
    nlohmann::json payload = {
        {"instance_id", "default_instance"},
        {"items", nlohmann::json::array({
            {
                {"reference", "PROT/XCBR1.Pos.stVal"},
                {"value", 1}
            }
        })}
    };
    nlohmann::json response = execute_action_json("server.write", localContext, payload);

    EXPECT_EQ(get_error_message(response), "Invalid request: missing server, model, or items array");
}

TEST_F(ActionServerOperationTest, WriteValuesNonExistentReferenceReturnsError) {
    nlohmann::json payload = {
        {"instance_id", "default_instance"},
        {"items", nlohmann::json::array({
            {
                {"reference", "simpleIOGenericIO/GGIO1.NonExistent"},
                {"value", 1}
            }
        })}
    };
    nlohmann::json response = execute_action_json("server.write", context, payload);

    EXPECT_EQ(get_error_message(response), "");
    ASSERT_TRUE(response.contains("result")) << "Response does not contain 'result': " << response.dump(2);
    ASSERT_TRUE(response["result"].is_array()) << "'result' is not an array: " << response.dump(2);
    ASSERT_EQ(response["result"].size(), 1u) << "Expected 1 item in 'result', got " << response["result"].size() << ": " << response.dump(2);
    EXPECT_EQ(response["result"][0]["reference"], "simpleIOGenericIO/GGIO1.NonExistent") << "Reference in response does not match request: " << response.dump(2);
    EXPECT_EQ(response["result"][0]["success"], false) << "Expected write failure for invalid reference: " << response.dump(2);
    EXPECT_EQ(response["result"][0]["error"], "Reference not found") << "Expected error message for non-existent reference: " << response.dump(2);
}

/*
{
"items":[
    {
      "fc": "MX",
      "reference": "simpleIOGenericIO/GGIO1.AnIn1",
      "value": {
        "mag": {
          "f": 0.0
        },
        "q": "0000000000000",
        "t": "19700101000000.000Z"
      }
    },
    {
      "fc": "ST",
      "reference": "simpleIOGenericIO/GGIO1.SPCSO1",
      "value": {
        "q": "0000000000000",
        "stVal": false,
        "t": "19700101000000.000Z"
      }
    },
    {
      "fc": "ST",
      "reference": "simpleIOGenericIO/GGIO1.SPCSO1.q",
      "value": "0000000000000"
    }
  ]
}
*/
TEST_F(ActionServerOperationTest, WriteValuesBatchReturnsPerItemResults) {
    nlohmann::json payload = {
        {"instance_id", "default_instance"},
        {"items", nlohmann::json::array({
            {
                {"reference", "simpleIOGenericIO/GGIO1.AnIn1"},
                {"fc", "MX"},
                {"value", {
                    {"mag", {{"f", 42.0}}},
                    {"q", "0100000000100"},
                    {"t", "20240103010709.213Z"}
                }}
            },
            {
                {"reference", "simpleIOGenericIO/GGIO1.SPCSO1"},
                {"fc", "ST"},
                {"value", {
                    {"q", "0000000000000"},
                    {"stVal", true},
                    {"t", "20240101000000.000Z"}
                }}
            },
            {
                {"reference", "simpleIOGenericIO/GGIO1.SPCSO1.q"},
                {"fc", "ST"},
                {"value", "0000000000000"}
            }
        })}
    };
    nlohmann::json response = execute_action_json("server.write", context, payload);

    EXPECT_EQ(get_error_message(response), "");
    ASSERT_TRUE(response.contains("result")) << "Response does not contain 'result': " << response.dump(2);
    ASSERT_TRUE(response["result"].is_array()) << "'result' is not an array: " << response.dump(2);
    ASSERT_EQ(response["result"].size(), 3u) << "Expected 3 items in 'result', got " << response["result"].size() << ": " << response.dump(2);

    ASSERT_EQ(response["result"][0]["reference"], "simpleIOGenericIO/GGIO1.AnIn1") << "Reference in response does not match request: " << response.dump(2);
    ASSERT_EQ(response["result"][0]["success"], true) << "Expected write success for valid reference: " << response.dump(2);
    ASSERT_FALSE(response["result"][0].contains("error")) << "Did not expect error for valid reference: " << response.dump(2);

    ASSERT_EQ(response["result"][1]["reference"], "simpleIOGenericIO/GGIO1.SPCSO1") << "Reference in response does not match request: " << response.dump(2);
    ASSERT_EQ(response["result"][1]["success"], true) << "Expected write success for valid reference: " << response.dump(2);
    ASSERT_FALSE(response["result"][1].contains("error")) << "Did not expect error for valid reference: " << response.dump(2);

    ASSERT_EQ(response["result"][2]["reference"], "simpleIOGenericIO/GGIO1.SPCSO1.q") << "Reference in response does not match request: " << response.dump(2);
    ASSERT_EQ(response["result"][2]["success"], true) << "Expected write success for valid reference: " << response.dump(2);
    ASSERT_FALSE(response["result"][2].contains("error")) << "Did not expect error for valid reference: " << response.dump(2);

    nlohmann::json read_payload = {
        {"instance_id", "default_instance"},
        {"items", nlohmann::json::array({
            {
                {"reference", "simpleIOGenericIO/GGIO1.SPCSO1.stVal"},
                {"fc", "ST"}
            },
            {
                {"reference", "simpleIOGenericIO/GGIO1.AnIn1"},
                {"fc", "MX"},
            }
        })}
    };
    nlohmann::json read_response = execute_action_json("server.read", context, read_payload);

    ASSERT_EQ(get_error_message(read_response), "");
    ASSERT_TRUE(read_response.contains("result")) << "Read response does not contain 'result': " << read_response.dump(2);
    ASSERT_TRUE(read_response["result"].is_array()) << "Read 'result' is not an array: " << read_response.dump(2);
    ASSERT_EQ(read_response["result"].size(), 2u) << "Expected 2 items in read 'result', got " << read_response["result"].size() << ": " << read_response.dump(2);
    ASSERT_EQ(read_response["result"][0]["value"], true) << "Expected updated boolean value after write: " << read_response.dump(2);

    ASSERT_TRUE(read_response["result"][1]["value"].contains("mag")) << "Expected 'mag' in read value for analog reference: " << read_response.dump(2);
    ASSERT_TRUE(read_response["result"][1]["value"]["mag"].contains("f")) << "Expected 'f' in 'mag' for analog reference: " << read_response.dump(2);
    ASSERT_EQ(read_response["result"][1]["value"]["mag"]["f"], 42.0) << "Expected updated float value after write: " << read_response.dump(2);
    ASSERT_EQ(read_response["result"][1]["value"]["q"], "0100000000100") << "Expected updated quality value after write: " << read_response.dump(2);
    ASSERT_EQ(read_response["result"][1]["value"]["t"], "20240103010709.213Z") << "Expected updated timestamp value after write: " << read_response.dump(2);
}

TEST(ActionServer, GetClientsReturnsPayload) {
    BackendContext context;
    ServerInstanceContext* server = context.get_or_create_server_instance("server-1");
    server->clients.push_back({"client-1", "2026-01-31T00:00:00Z"});

    nlohmann::json response = execute_action_json("server.get_clients", context, {{"instance_id", "server-1"}});

    ASSERT_TRUE(response.contains("result"));
    ASSERT_TRUE(response["result"].contains("clients"));
    ASSERT_TRUE(response["result"]["clients"].is_array());
    EXPECT_EQ(response["result"]["clients"].size(), 1u);
}

