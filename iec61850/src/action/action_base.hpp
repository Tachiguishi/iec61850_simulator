#pragma once

#include "../core_context.hpp"

#include "nlohmann_json.hpp"

#include <string>

namespace ipc::actions {

enum class ActionMethod {
	ServerStart,		// 启动服务
	ServerStop,			// 停止服务
	ServerRemove,		// 移除服务实例
	ServerLoadModel,	// 加载模型
	ServerConfig,		// 配置服务实例
	ServerSetDataValue,	// 设置数据值
	ServerRead,			// 读取数据值
	ServerGetClients,	// 获取客户端列表
	ServerListInstances,	// 列出实例
	ServerGetInterfaces,	// 获取接口
	ServerSetInterface,	// 设置接口

	ClientConnect,		// 连接客户端
	ClientDisconnect,	// 断开客户端
	ClientBrowse,		// 浏览客户端
	ClientRead,			// 读取客户端数据
	ClientReadBatch,	// 批量读取客户端数据
	ClientWrite,		// 写入客户端数据
	ClientListInstances,	// 列出客户端实例
};

struct ActionContext {
	const std::string& action;
	BackendContext& context;
	const nlohmann::json& payload;
};

class ActionHandler {
public:
	virtual ~ActionHandler() = default;
	virtual ActionMethod name() const = 0;
	virtual bool handle(ActionContext& ctx, nlohmann::json& response) = 0;

protected:
	bool check_payload_existence(const ActionContext& ctx, nlohmann::json& response);
	void pack_error_response(nlohmann::json& response, const std::string& error_msg);
	std::string validate_and_extract_instance_id(
	const nlohmann::json& payload,
	const std::string& action,
	nlohmann::json& response,
	bool& error_occurred);
	std::string extract_instance_id(const nlohmann::json& payload);
};

} // namespace ipc::actions
