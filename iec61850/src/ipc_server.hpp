#pragma once

#include <functional>
#include <string>

namespace ipc {

class IpcServer {
public:
    using RequestHandler = std::function<void(const std::string& request_bytes, std::string& response_bytes)>;

    IpcServer(std::string socket_path, RequestHandler handler);
    ~IpcServer();

    bool start();
    void stop();

private:
    std::string socket_path_;
    RequestHandler handler_;
    int server_fd_ = -1;
    bool running_ = false;

    void run_loop();
};

} // namespace ipc
