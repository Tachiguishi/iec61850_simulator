#pragma once

#include "core_context.hpp"

#include <msgpack.hpp>

namespace ipc::actions {

bool handle_client_action(
    const std::string& action,
    BackendContext& context,
    const msgpack::object& payload,
    bool has_payload,
    msgpack::packer<msgpack::sbuffer>& pk);

} // namespace ipc::actions
