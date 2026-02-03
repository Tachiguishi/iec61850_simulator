#pragma once

#include <string>
#include <vector>
#include <mutex>
#include <unordered_map>
#include <memory>

#include <iec61850_client.h>
#include <iec61850_server.h>

struct ClientInfo {
    std::string id;
    std::string connected_at;
};

/**
 * 服务器实例上下文
 * 每个IEC61850服务器实例有独立的模型、服务器对象和客户端连接列表
 */
struct ServerInstanceContext {
    std::string instance_id;
    std::string ied_name;
    std::string ip_address = "0.0.0.0";  // 监听的 IP 地址
    
    IedModel* model = nullptr;
    IedServer server = nullptr;
    IedServerConfig config = nullptr;
    std::vector<ClientInfo> clients;
    
    int port = 102;
    bool running = false;
    
    ~ServerInstanceContext() {
        if (server) {
            IedServer_stop(server);
            IedServer_destroy(server);
        }
        if (config) {
            IedServerConfig_destroy(config);
        }
        if (model) {
            IedModel_destroy(model);
        }
    }
};

/**
 * 客户端实例上下文
 * 每个IEC61850客户端实例有独立的连接和目标信息
 */
struct ClientInstanceContext {
    std::string instance_id;
    std::string target_host;
    int target_port = 102;
    std::string ied_name = "IED";
    
    IedConnection connection = nullptr;
    bool connected = false;
    
    ~ClientInstanceContext() {
        if (connection) {
            IedConnection_close(connection);
            IedConnection_destroy(connection);
        }
    }
};

/**
 * 后端上下文
 * 管理所有服务器和客户端实例
 */
struct BackendContext {
    std::mutex mutex;

    // 多实例支持：使用instance_id作为key
    std::unordered_map<std::string, std::unique_ptr<ServerInstanceContext>> server_instances;
    std::unordered_map<std::string, std::unique_ptr<ClientInstanceContext>> client_instances;
    
    // 辅助方法：获取或创建服务器实例
    ServerInstanceContext* get_server_instance(const std::string& instance_id) {
        auto it = server_instances.find(instance_id);
        if (it != server_instances.end()) {
            return it->second.get();
        }
        return nullptr;
    }
    
    ServerInstanceContext* get_or_create_server_instance(const std::string& instance_id) {
        auto it = server_instances.find(instance_id);
        if (it != server_instances.end()) {
            return it->second.get();
        }
        auto inst = std::make_unique<ServerInstanceContext>();
        inst->instance_id = instance_id;
        auto* ptr = inst.get();
        server_instances[instance_id] = std::move(inst);
        return ptr;
    }
    
    void remove_server_instance(const std::string& instance_id) {
        server_instances.erase(instance_id);
    }
    
    // 辅助方法：获取或创建客户端实例
    ClientInstanceContext* get_client_instance(const std::string& instance_id) {
        auto it = client_instances.find(instance_id);
        if (it != client_instances.end()) {
            return it->second.get();
        }
        return nullptr;
    }
    
    ClientInstanceContext* get_or_create_client_instance(const std::string& instance_id) {
        auto it = client_instances.find(instance_id);
        if (it != client_instances.end()) {
            return it->second.get();
        }
        auto inst = std::make_unique<ClientInstanceContext>();
        inst->instance_id = instance_id;
        auto* ptr = inst.get();
        client_instances[instance_id] = std::move(inst);
        return ptr;
    }
    
    void remove_client_instance(const std::string& instance_id) {
        client_instances.erase(instance_id);
    }
};
