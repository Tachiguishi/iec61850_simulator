#pragma once

#include "../core_context.hpp"
#include <msgpack.hpp>
#include <string>

namespace ipc::actions {

std::string handle_action(const std::string& request_bytes, BackendContext& context);

} // namespace ipc::actions
