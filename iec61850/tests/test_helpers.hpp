#pragma once

#include "core_context.hpp"
#include "nlohmann_json.hpp"

#include <functional>
#include <msgpack.hpp>
#include <string>

msgpack::object_handle pack_msgpack_object(const std::function<void(msgpack::packer<msgpack::sbuffer>&)>& pack_fn);
void pack_json_value(msgpack::packer<msgpack::sbuffer>& pk, const nlohmann::json& value);
msgpack::object_handle make_payload_from_json(const nlohmann::json& value);
nlohmann::json unpack_msgpack_bytes_to_json(const std::string& bytes);
nlohmann::json execute_action_json(const std::string& action, BackendContext& context);
nlohmann::json execute_action_json(const std::string& action, BackendContext& context, const msgpack::object& payload, bool has_payload = true);

void pack_default_model_payload(msgpack::packer<msgpack::sbuffer>& pk);

void pack_payload_from_json_file(msgpack::packer<msgpack::sbuffer>& pk, const std::string& model_path);
