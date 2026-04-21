#pragma once

#include "../core_context.hpp"

#include "nlohmann_json.hpp"

#include <string>

namespace ipc::actions {

struct ActionContext {
	const std::string& action;
	BackendContext& context;
	const nlohmann::json& payload;
	bool has_payload;
};

class ActionHandler {
public:
	virtual ~ActionHandler() = default;
	virtual const char* name() const = 0;
	virtual bool handle(ActionContext& ctx, nlohmann::json& response) = 0;

protected:
	bool ensure_payload_map(const ActionContext& ctx, nlohmann::json& response);
	void pack_error_response(nlohmann::json& response, const std::string& error_msg);
	std::string validate_and_extract_instance_id(
	const nlohmann::json& payload,
	const std::string& action,
	nlohmann::json& response,
	bool& error_occurred);
	std::string extract_instance_id(const nlohmann::json& payload);
};

} // namespace ipc::actions
