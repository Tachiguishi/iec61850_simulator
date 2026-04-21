#include "msgpack_codec.hpp"

#include <stdexcept>

namespace ipc::codec {

namespace {

nlohmann::json to_json(const msgpack::object& obj) {
    switch (obj.type) {
        case msgpack::type::NIL:
            return nullptr;
        case msgpack::type::BOOLEAN:
            return obj.via.boolean;
        case msgpack::type::POSITIVE_INTEGER:
            return obj.via.u64;
        case msgpack::type::NEGATIVE_INTEGER:
            return obj.via.i64;
        case msgpack::type::FLOAT32:
        case msgpack::type::FLOAT64:
            return obj.via.f64;
        case msgpack::type::STR:
            return std::string(obj.via.str.ptr, obj.via.str.size);
        case msgpack::type::BIN:
            return std::string(obj.via.bin.ptr, obj.via.bin.size);
        case msgpack::type::ARRAY: {
            nlohmann::json arr = nlohmann::json::array();
            auto array = obj.via.array;
            for (uint32_t i = 0; i < array.size; ++i) {
                arr.push_back(to_json(array.ptr[i]));
            }
            return arr;
        }
        case msgpack::type::MAP: {
            nlohmann::json map = nlohmann::json::object();
            auto m = obj.via.map;
            for (uint32_t i = 0; i < m.size; ++i) {
                if (m.ptr[i].key.type != msgpack::type::STR) {
                    continue;
                }
                std::string key(m.ptr[i].key.via.str.ptr, m.ptr[i].key.via.str.size);
                map[key] = to_json(m.ptr[i].val);
            }
            return map;
        }
        default:
            return nullptr;
    }
}

} // namespace

Request decode_request(const std::string& bytes) {
    Request req;
    msgpack::object_handle handle = msgpack::unpack(bytes.data(), bytes.size());
    msgpack::object root = handle.get();
    nlohmann::json root_json = to_json(root);

    if (auto id_obj = find_key(root_json, "id")) {
        req.id = as_string(*id_obj, "");
    }
    if (auto method_obj = find_key(root_json, "method")) {
        req.action = as_string(*method_obj, "");
    }
    if (auto payload_ptr = find_key(root_json, "params")) {
        req.payload = *payload_ptr;
        req.has_payload = true;
    }

    return req;
}

std::string encode_response_bytes(const nlohmann::json& response_json) {
    msgpack::sbuffer buffer;
    msgpack::packer<msgpack::sbuffer> pk(&buffer);

    encode_msgpack_from_json(response_json, pk);
    return std::string(buffer.data(), buffer.size());
}

void encode_msgpack_from_json(const nlohmann::json& json, msgpack::packer<msgpack::sbuffer>& pk){
    const auto pack_json = [&pk](const nlohmann::json& value, const auto& self) -> void {
        if (value.is_null()) {
        pk.pack_nil();
        return;
        }
        if (value.is_boolean()) {
        pk.pack(value.get<bool>());
        return;
        }
        if (value.is_number_integer()) {
        pk.pack(value.get<int64_t>());
        return;
        }
        if (value.is_number_unsigned()) {
        pk.pack(value.get<uint64_t>());
        return;
        }
        if (value.is_number_float()) {
        pk.pack(value.get<double>());
        return;
        }
        if (value.is_string()) {
        pk.pack(value.get<std::string>());
        return;
        }
        if (value.is_array()) {
        pk.pack_array(value.size());
        for (const auto& item : value) {
            self(item, self);
        }
        return;
        }
        if (value.is_object()) {
        pk.pack_map(value.size());
        for (auto it = value.begin(); it != value.end(); ++it) {
            pk.pack(it.key());
            self(it.value(), self);
        }
        return;
        }

        throw std::runtime_error("Unsupported JSON value while packing msgpack");
    };

    pack_json(json, pack_json);
}

const nlohmann::json* find_key(const nlohmann::json& map_obj, const std::string& key) {
    if (!map_obj.is_object()) {
        return nullptr;
    }
    auto it = map_obj.find(key);
    if (it == map_obj.end()) {
        return nullptr;
    }
    return &(*it);
}

std::string as_string(const nlohmann::json& obj, const std::string& fallback) {
    if (obj.is_string()) {
        return obj.get<std::string>();
    }
    return fallback;
}

int64_t as_int64(const nlohmann::json& obj, int64_t fallback) {
    if (obj.is_number_integer()) {
        return obj.get<int64_t>();
    }
    if (obj.is_number_unsigned()) {
        return static_cast<int64_t>(obj.get<uint64_t>());
    }
    return fallback;
}

bool as_bool(const nlohmann::json& obj, bool fallback) {
    if (obj.is_boolean()) {
        return obj.get<bool>();
    }
    return fallback;
}

double as_double(const nlohmann::json& obj, double fallback) {
    if (obj.is_number()) {
        return obj.get<double>();
    }
    return fallback;
}

nlohmann::json make_error(const std::string& message) {
    return nlohmann::json{{"message", message}};
}

nlohmann::json make_success_payload() {
    return nlohmann::json{{"success", true}};
}

} // namespace ipc::codec
