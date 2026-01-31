#include <gtest/gtest.h>

#include "action_server.hpp"
#include "logger.hpp"
#include "msgpack_codec.hpp"

#include <msgpack.hpp>

#include <functional>
#include <mutex>

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
    msgpack::sbuffer buffer;
    msgpack::packer<msgpack::sbuffer> pk(&buffer);

    pk.pack_map(4);
    pk.pack("id");
    pk.pack("test-id");
    pk.pack("type");
    pk.pack("response");

    bool handled = ipc::actions::handle_server_action(action, context, payload, has_payload, pk);
    EXPECT_TRUE(handled);

    auto response_handle = msgpack::unpack(buffer.data(), buffer.size());
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

TEST(ActionServer, LoadModelMissingPayloadReturnsSuccess) {
    BackendContext context;

    auto payload_handle = make_payload([](msgpack::packer<msgpack::sbuffer>& pk) {
        pk.pack_map(1);
        pk.pack("model");
        pk.pack_map(2);
        pk.pack("name");
        pk.pack("IED");
        pk.pack("logical_devices");
        pk.pack_map(0);
    });

    msgpack::object response;
    execute_action("server.load_model", context, payload_handle.get(), true, response);

    EXPECT_TRUE(get_success_flag(response));
    EXPECT_EQ(get_error_message(response), "");
}

TEST(ActionServer, SetDataValueInvalidRequestReturnsError) {
    BackendContext context;

    auto payload_handle = make_payload([](msgpack::packer<msgpack::sbuffer>& pk) {
        pk.pack_map(2);
        pk.pack("reference");
        pk.pack("PROT/XCBR1.Pos.stVal");
        pk.pack("value");
        pk.pack(1);
    });

    msgpack::object response;
    execute_action("server.set_data_value", context, payload_handle.get(), true, response);

    EXPECT_EQ(get_error_message(response), "Invalid request");
}

TEST(ActionServer, GetValuesInvalidRequestReturnsError) {
    BackendContext context;

    auto payload_handle = make_payload([](msgpack::packer<msgpack::sbuffer>& pk) {
        pk.pack_map(1);
        pk.pack("references");
        pk.pack_array(1);
        pk.pack("PROT/XCBR1.Pos.stVal");
    });

    msgpack::object response;
    execute_action("server.get_values", context, payload_handle.get(), true, response);

    EXPECT_EQ(get_error_message(response), "Invalid request");
}

TEST(ActionServer, GetClientsReturnsPayload) {
    BackendContext context;
    context.clients.push_back({"client-1", "2026-01-31T00:00:00Z"});

    msgpack::object dummy;
    msgpack::object response;
    execute_action("server.get_clients", context, dummy, false, response);

    const msgpack::object* payload_obj = find_key(response, "payload");
    ASSERT_TRUE(payload_obj);
    const msgpack::object* clients_obj = find_key(*payload_obj, "clients");
    ASSERT_TRUE(clients_obj);
    ASSERT_EQ(clients_obj->type, msgpack::type::ARRAY);
    EXPECT_EQ(clients_obj->via.array.size, 1u);
}
