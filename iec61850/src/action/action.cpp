#include "action.hpp"

#include "action_base.hpp"
#include "action_registry.hpp"
#include "logger.hpp"
#include "msgpack_codec.hpp"

#include <log4cplus/loggingmacros.h>

namespace ipc::actions {

namespace {

ActionRegistry& get_registry() {
	static ActionRegistry registry = [] {
		ActionRegistry reg;
		register_client_actions(reg);
		register_server_actions(reg);
		return reg;
	}();

	return registry;
}

} // namespace

bool ActionHandler::ensure_payload_map(const ActionContext& ctx, msgpack::packer<msgpack::sbuffer>& pk) {
	if (!ctx.has_payload || ctx.payload.type != msgpack::type::MAP) {
		LOG4CPLUS_ERROR(server_logger(), ctx.action << " missing payload");
		pack_error_response(pk, "Missing payload");
		return false;
	}
	return true;
}

void ActionHandler::pack_error_response(msgpack::packer<msgpack::sbuffer>& pk, const std::string& error_msg){
	pk.pack("payload");
	pk.pack_map(0);
	pk.pack("error");
	ipc::codec::pack_error(pk, error_msg);
}

std::string ActionHandler::validate_and_extract_instance_id(
    const msgpack::object& payload,
    const std::string& action,
    msgpack::packer<msgpack::sbuffer>& pk,
    bool& error_occurred) {
    std::string instance_id = extract_instance_id(payload);
    if (instance_id.empty()) {
        LOG4CPLUS_ERROR(server_logger(), action << ": instance_id is required");
        pack_error_response(pk, "instance_id is required");
        error_occurred = true;
        return "";
    }
    error_occurred = false;
    return instance_id;
}

std::string ActionHandler::extract_instance_id(const msgpack::object& payload) {
    if (auto id_obj = ipc::codec::find_key(payload, "instance_id")) {
        std::string id = ipc::codec::as_string(*id_obj, "");
        if (!id.empty()) {
            return id;
        }
    }
    return "";
}

std::string handle_action(const std::string& request_bytes, BackendContext& context) {
	
	msgpack::sbuffer buffer;
	msgpack::packer<msgpack::sbuffer> pk(&buffer);
	std::string response_bytes;

	ipc::codec::Request request;
	try {
		request = ipc::codec::decode_request(request_bytes);
	} catch (const std::exception& exc) {
		LOG4CPLUS_ERROR(core_logger(), "Decode error: " << exc.what());
		pk.pack_map(4);
		pk.pack("id");
		pk.pack("");
		pk.pack("type");
		pk.pack("response");
		pk.pack("payload");
		pk.pack_map(0);
		pk.pack("error");
		ipc::codec::pack_error(pk, std::string("Decode error: ") + exc.what());
		response_bytes.assign(buffer.data(), buffer.size());
		return response_bytes;
	}

	LOG4CPLUS_INFO(core_logger(), "IPC action: " << request.action << " id=" << request.id);

	pk.pack_map(4);
	pk.pack("id");
	pk.pack(request.id);
	pk.pack("type");
	pk.pack("response");
	ActionContext ctx{request.action, context, request.payload, request.has_payload};
	ActionHandler* handler = get_registry().find(request.action);
	if (!handler) {
		LOG4CPLUS_WARN(core_logger(), "Unknown action: " << request.action);
		pk.pack("payload");
		pk.pack_map(0);
		pk.pack("error");
		ipc::codec::pack_error(pk, "Unknown action");
		return response_bytes;
	}
	handler->handle(ctx, pk);

	response_bytes.assign(buffer.data(), buffer.size());
	return response_bytes;
}

} // namespace ipc::actions
