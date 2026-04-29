#pragma once

#include "core_context.hpp"
#include "nlohmann_json.hpp"

#include <string>

nlohmann::json execute_action_json(const std::string& action, BackendContext& context, const nlohmann::json& payload = nlohmann::json{});

nlohmann::json load_model_payload_from_file(const std::string& model_path);
