#include "ipc_server.hpp"

#include <sys/socket.h>
#include <sys/un.h>
#include <unistd.h>

#include <cstring>
#include <iostream>
#include <thread>
#include <vector>

namespace ipc {

namespace {
std::string g_socket_path;

void cleanup_socket_file() {
    if (!g_socket_path.empty()) {
        ::unlink(g_socket_path.c_str());
    }
}
} // namespace

IpcServer::IpcServer(std::string socket_path, RequestHandler handler)
    : socket_path_(std::move(socket_path)), handler_(std::move(handler)) {}

IpcServer::~IpcServer() {
    stop();
}

bool IpcServer::start() {
    if (running_) {
        return true;
    }

    if (g_socket_path.empty()) {
        g_socket_path = socket_path_;
        std::atexit(cleanup_socket_file);
    }

    server_fd_ = ::socket(AF_UNIX, SOCK_STREAM, 0);
    if (server_fd_ < 0) {
        std::perror("socket");
        return false;
    }

    ::unlink(socket_path_.c_str());

    sockaddr_un addr{};
    addr.sun_family = AF_UNIX;
    std::snprintf(addr.sun_path, sizeof(addr.sun_path), "%s", socket_path_.c_str());

    if (::bind(server_fd_, reinterpret_cast<sockaddr*>(&addr), sizeof(addr)) < 0) {
        std::perror("bind");
        ::close(server_fd_);
        server_fd_ = -1;
        return false;
    }

    if (::listen(server_fd_, 8) < 0) {
        std::perror("listen");
        ::close(server_fd_);
        server_fd_ = -1;
        return false;
    }

    running_ = true;
    std::thread(&IpcServer::run_loop, this).detach();
    return true;
}

void IpcServer::stop() {
    if (!running_) {
        return;
    }
    running_ = false;
    if (server_fd_ >= 0) {
        ::close(server_fd_);
        server_fd_ = -1;
    }
    ::unlink(socket_path_.c_str());
}

void IpcServer::run_loop() {
    while (running_) {
        int client_fd = ::accept(server_fd_, nullptr, nullptr);
        if (client_fd < 0) {
            if (running_) {
                std::perror("accept");
            }
            continue;
        }

        // Read length-prefixed frame
        uint32_t length_be = 0;
        ssize_t read_bytes = ::read(client_fd, &length_be, sizeof(length_be));
        if (read_bytes != sizeof(length_be)) {
            ::close(client_fd);
            continue;
        }

        uint32_t length = __builtin_bswap32(length_be);
        std::vector<char> buffer(length);
        size_t offset = 0;
        while (offset < length) {
            ssize_t chunk = ::read(client_fd, buffer.data() + offset, length - offset);
            if (chunk <= 0) {
                break;
            }
            offset += static_cast<size_t>(chunk);
        }

        if (offset != length) {
            ::close(client_fd);
            continue;
        }

        std::string response;
        handler_(std::string(buffer.data(), buffer.size()), response);

        uint32_t resp_len = static_cast<uint32_t>(response.size());
        uint32_t resp_len_be = __builtin_bswap32(resp_len);
        ::write(client_fd, &resp_len_be, sizeof(resp_len_be));
        if (!response.empty()) {
            ::write(client_fd, response.data(), response.size());
        }

        ::close(client_fd);
    }
}

} // namespace ipc
