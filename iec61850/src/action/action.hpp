#pragma once

#include "../core_context.hpp"
#include "msgpack_codec.hpp"
#include <string>

namespace ipc::actions {

std::string handle_action(ipc::codec::Request& request, BackendContext& context);

} // namespace ipc::actions
