#pragma once

#include "../core_context.hpp"

#include <msgpack.hpp>

#include <string>

namespace ipc::actions {

struct ActionContext {
    const std::string& action;
    BackendContext& context;
    const msgpack::object& payload;
    bool has_payload;
};

class ActionHandler {
public:
    virtual ~ActionHandler() = default;
    virtual const char* name() const = 0;
    virtual bool handle(ActionContext& ctx, msgpack::packer<msgpack::sbuffer>& pk) = 0;
};

} // namespace ipc::actions
