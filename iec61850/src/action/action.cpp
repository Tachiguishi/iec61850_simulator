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
