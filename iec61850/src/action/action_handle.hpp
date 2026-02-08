#include "action_base.hpp"

namespace ipc::actions {

class ServerLoadModelAction final : public ActionHandler {
public:
	const char* name() const override { return "server.load_model"; }
	bool handle(ActionContext& ctx, msgpack::packer<msgpack::sbuffer>& pk) override;
};

}
