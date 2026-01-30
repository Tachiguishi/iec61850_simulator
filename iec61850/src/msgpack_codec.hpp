#pragma once

#include <msgpack.hpp>

#include <string>

namespace ipc::codec {

struct Request {
    std::string id;
    std::string action;
    msgpack::object payload;
    bool has_payload = false;
    msgpack::object_handle handle;
};

Request decode_request(const std::string& bytes);

const msgpack::object* find_key(const msgpack::object& map_obj, const std::string& key);
std::string as_string(const msgpack::object& obj, const std::string& fallback = "");
int64_t as_int64(const msgpack::object& obj, int64_t fallback = 0);
bool as_bool(const msgpack::object& obj, bool fallback = false);
double as_double(const msgpack::object& obj, double fallback = 0.0);

void pack_error(msgpack::packer<msgpack::sbuffer>& pk, const std::string& message);
void pack_success_payload(msgpack::packer<msgpack::sbuffer>& pk);

} // namespace ipc::codec
