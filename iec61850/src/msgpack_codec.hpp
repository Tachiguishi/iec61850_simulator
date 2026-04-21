#pragma once

#include "nlohmann_json.hpp"
#include <msgpack.hpp>

#include <string>

namespace ipc::codec {

struct Request {
    std::string id;
    std::string action;
    nlohmann::json payload;
    bool has_payload = false;
};

Request decode_request(const std::string& bytes);
std::string encode_response_bytes(const nlohmann::json& response_json);

void encode_msgpack_from_json(const nlohmann::json& json, msgpack::packer<msgpack::sbuffer>& pk);

const nlohmann::json* find_key(const nlohmann::json& map_obj, const std::string& key);
std::string as_string(const nlohmann::json& obj, const std::string& fallback = "");
int64_t as_int64(const nlohmann::json& obj, int64_t fallback = 0);
bool as_bool(const nlohmann::json& obj, bool fallback = false);
double as_double(const nlohmann::json& obj, double fallback = 0.0);

nlohmann::json make_error(const std::string& message);
nlohmann::json make_success_payload();

} // namespace ipc::codec
