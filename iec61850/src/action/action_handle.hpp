#include "action_base.hpp"

namespace ipc::actions {

class ServerLoadModelAction final : public ActionHandler {
public:
	const char* name() const override { return "server.load_model"; }
	bool handle(ActionContext& ctx, nlohmann::json& response) override;
};

}
