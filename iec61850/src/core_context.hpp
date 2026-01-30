#pragma once

#include <string>
#include <vector>
#include <mutex>

#include <iec61850_client.h>
#include <iec61850_server.h>

struct ClientInfo {
    std::string id;
    std::string connected_at;
};

struct BackendContext {
    std::mutex mutex;

    IedModel* server_model = nullptr;
    IedServer server = nullptr;
    IedServerConfig server_config = nullptr;
    std::vector<ClientInfo> clients;

    IedConnection client_connection = nullptr;
    std::string client_ied_name = "IED";
};
