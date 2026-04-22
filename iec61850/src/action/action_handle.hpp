#include "action_base.hpp"

namespace ipc::actions {

class ServerLoadModelAction final : public ActionHandler {
public:
	ActionMethod name() const override { return ActionMethod::ServerLoadModel; }
	bool handle(ActionContext& ctx, nlohmann::json& response) override;
};

}
