#pragma once

#include <msgpack.hpp>

void pack_default_model_payload(msgpack::packer<msgpack::sbuffer>& pk);
