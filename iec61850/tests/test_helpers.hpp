#pragma once

#include <msgpack.hpp>

void pack_default_model_payload(msgpack::packer<msgpack::sbuffer>& pk);

void pack_payload_from_json_file(msgpack::packer<msgpack::sbuffer>& pk, const std::string& model_path);
