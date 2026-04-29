#include "action_base.hpp"

namespace ipc::actions {

class ServerConfigAction : public ActionHandler {
public:
	ActionMethod name() const override { return ActionMethod::ServerConfig; }
	bool handle(ActionContext& ctx, nlohmann::json& response) override;

protected:
	bool init_iedServer(ServerInstanceContext* inst, const std::string& instance_id, nlohmann::json& response);
};

class ServerLoadModelAction final : public ServerConfigAction {
public:
	ActionMethod name() const override { return ActionMethod::ServerLoadModel; }
	bool handle(ActionContext& ctx, nlohmann::json& response) override;
};

}
