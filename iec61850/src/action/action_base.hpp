#pragma once

#include "../core_context.hpp"

#include <msgpack.hpp>

#include <string>

namespace ipc::actions {

struct ActionContext {
	const std::string& action;
	BackendContext& context;
	const msgpack::object& payload;
	bool has_payload;
};

class ActionHandler {
public:
	virtual ~ActionHandler() = default;
	virtual const char* name() const = 0;
	virtual bool handle(ActionContext& ctx, msgpack::packer<msgpack::sbuffer>& pk) = 0;

protected:
	bool ensure_payload_map(const ActionContext& ctx, msgpack::packer<msgpack::sbuffer>& pk);
	void pack_error_response(msgpack::packer<msgpack::sbuffer>& pk, const std::string& error_msg);
	std::string validate_and_extract_instance_id(
	const msgpack::object& payload,
	const std::string& action,
	msgpack::packer<msgpack::sbuffer>& pk,
	bool& error_occurred);
	std::string extract_instance_id(const msgpack::object& payload);
};

} // namespace ipc::actions
