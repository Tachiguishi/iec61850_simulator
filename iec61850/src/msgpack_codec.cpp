#include "msgpack_codec.hpp"

namespace ipc::codec {

Request decode_request(const std::string& bytes) {
    Request req;
    req.handle = msgpack::unpack(bytes.data(), bytes.size());
    msgpack::object root = req.handle.get();

    if (auto id_obj = find_key(root, "id")) {
        req.id = as_string(*id_obj, "");
    }
    if (auto action_obj = find_key(root, "action")) {
        req.action = as_string(*action_obj, "");
    }
    if (auto payload_ptr = find_key(root, "payload")) {
        req.payload = *payload_ptr;
        req.has_payload = true;
    }

    return req;
}

const msgpack::object* find_key(const msgpack::object& map_obj, const std::string& key) {
    if (map_obj.type != msgpack::type::MAP) {
        return nullptr;
    }

    auto map = map_obj.via.map;
    for (uint32_t i = 0; i < map.size; ++i) {
        if (map.ptr[i].key.type == msgpack::type::STR) {
            std::string k(map.ptr[i].key.via.str.ptr, map.ptr[i].key.via.str.size);
            if (k == key) {
                return &map.ptr[i].val;
            }
        }
    }
    return nullptr;
}

std::string as_string(const msgpack::object& obj, const std::string& fallback) {
    if (obj.type == msgpack::type::STR) {
        return std::string(obj.via.str.ptr, obj.via.str.size);
    }
    return fallback;
}

int64_t as_int64(const msgpack::object& obj, int64_t fallback) {
    if (obj.type == msgpack::type::POSITIVE_INTEGER) {
        return static_cast<int64_t>(obj.via.u64);
    }
    if (obj.type == msgpack::type::NEGATIVE_INTEGER) {
        return static_cast<int64_t>(obj.via.i64);
    }
    return fallback;
}

bool as_bool(const msgpack::object& obj, bool fallback) {
    if (obj.type == msgpack::type::BOOLEAN) {
        return obj.via.boolean;
    }
    return fallback;
}

double as_double(const msgpack::object& obj, double fallback) {
    if (obj.type == msgpack::type::FLOAT32 || obj.type == msgpack::type::FLOAT64) {
        return obj.via.f64;
    }
    if (obj.type == msgpack::type::POSITIVE_INTEGER) {
        return static_cast<double>(obj.via.u64);
    }
    if (obj.type == msgpack::type::NEGATIVE_INTEGER) {
        return static_cast<double>(obj.via.i64);
    }
    return fallback;
}

void pack_error(msgpack::packer<msgpack::sbuffer>& pk, const std::string& message) {
    pk.pack_map(1);
    pk.pack("message");
    pk.pack(message);
}

void pack_success_payload(msgpack::packer<msgpack::sbuffer>& pk) {
    pk.pack_map(1);
    pk.pack("success");
    pk.pack(true);
}

} // namespace ipc::codec
