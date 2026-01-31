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

IpcServer::IpcServer(std::string socket_path, RequestHandler handler, size_t thread_pool_size)
    : socket_path_(std::move(socket_path)),
      sync_handler_(std::move(handler)),
      thread_pool_size_(thread_pool_size) {}

IpcServer::IpcServer(std::string socket_path, AsyncRequestHandler handler, size_t thread_pool_size)
    : socket_path_(std::move(socket_path)),
      async_handler_(std::move(handler)),
      thread_pool_size_(thread_pool_size > 0 ? thread_pool_size : 4) {}

IpcServer::~IpcServer() {
    stop();
}

bool IpcServer::setup_socket() {
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

    return true;
}

bool IpcServer::start() {
    if (running_) {
        return true;
    }

    if (!setup_socket()) {
        return false;
    }

    running_ = true;

    if (thread_pool_size_ > 0) {
        // Start worker thread pool for concurrent handling
        pool_running_ = true;
        for (size_t i = 0; i < thread_pool_size_; ++i) {
            worker_threads_.emplace_back(&IpcServer::worker_thread_func, this);
        }
        accept_thread_ = std::thread(&IpcServer::accept_loop_threaded, this);
    } else {
        // Single-threaded synchronous mode
        accept_thread_ = std::thread(&IpcServer::accept_loop, this);
    }

    return true;
}

void IpcServer::stop() {
    if (!running_) {
        return;
    }
    running_ = false;

    // Stop thread pool
    if (pool_running_) {
        pool_running_ = false;
        queue_cv_.notify_all();
        for (auto& t : worker_threads_) {
            if (t.joinable()) {
                t.join();
            }
        }
        worker_threads_.clear();
    }

    // Close server socket to unblock accept()
    if (server_fd_ >= 0) {
        ::shutdown(server_fd_, SHUT_RDWR);
        ::close(server_fd_);
        server_fd_ = -1;
    }

    // Wait for accept thread
    if (accept_thread_.joinable()) {
        accept_thread_.join();
    }

    ::unlink(socket_path_.c_str());
}

bool IpcServer::read_request(int client_fd, std::string& request_data) {
    // Read length-prefixed frame
    uint32_t length_be = 0;
    ssize_t read_bytes = ::read(client_fd, &length_be, sizeof(length_be));
    if (read_bytes != sizeof(length_be)) {
        return false;
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
        return false;
    }

    request_data.assign(buffer.data(), buffer.size());
    return true;
}

void IpcServer::send_response(int client_fd, const std::string& response) {
    uint32_t resp_len = static_cast<uint32_t>(response.size());
    uint32_t resp_len_be = __builtin_bswap32(resp_len);
    ::write(client_fd, &resp_len_be, sizeof(resp_len_be));
    if (!response.empty()) {
        ::write(client_fd, response.data(), response.size());
    }
}

void IpcServer::handle_client_sync(int client_fd) {
    std::string request_data;
    if (!read_request(client_fd, request_data)) {
        ::close(client_fd);
        return;
    }

    std::string response;
    if (async_handler_) {
        // Use async handler but wait for result (sync wrapper)
        try {
            auto future = async_handler_(request_data);
            response = future.get();
        } catch (const std::exception& e) {
            std::cerr << "Handler error: " << e.what() << std::endl;
        }
    } else if (sync_handler_) {
        sync_handler_(request_data, response);
    }

    send_response(client_fd, response);
    ::close(client_fd);
}

void IpcServer::handle_client_async(int client_fd, const std::string& request_data) {
    std::string response;

    if (async_handler_) {
        try {
            auto future = async_handler_(request_data);
            response = future.get();
        } catch (const std::exception& e) {
            std::cerr << "Async handler error: " << e.what() << std::endl;
        }
    } else if (sync_handler_) {
        sync_handler_(request_data, response);
    }

    send_response(client_fd, response);
    ::close(client_fd);
}

void IpcServer::worker_thread_func() {
    while (pool_running_) {
        ClientTask task;
        {
            std::unique_lock<std::mutex> lock(queue_mutex_);
            queue_cv_.wait(lock, [this] { return !task_queue_.empty() || !pool_running_; });

            if (!pool_running_ && task_queue_.empty()) {
                return;
            }

            task = std::move(task_queue_.front());
            task_queue_.pop();
        }

        handle_client_async(task.client_fd, task.request_data);
    }
}

void IpcServer::accept_loop() {
    while (running_) {
        int client_fd = ::accept(server_fd_, nullptr, nullptr);
        if (client_fd < 0) {
            if (running_) {
                std::perror("accept");
            }
            continue;
        }

        handle_client_sync(client_fd);
    }
}

void IpcServer::accept_loop_threaded() {
    while (running_) {
        int client_fd = ::accept(server_fd_, nullptr, nullptr);
        if (client_fd < 0) {
            if (running_) {
                std::perror("accept");
            }
            continue;
        }

        std::string request_data;
        if (!read_request(client_fd, request_data)) {
            ::close(client_fd);
            continue;
        }

        // Queue task for worker thread
        {
            std::lock_guard<std::mutex> lock(queue_mutex_);
            task_queue_.push({client_fd, std::move(request_data)});
        }
        queue_cv_.notify_one();
    }
}

} // namespace ipc
