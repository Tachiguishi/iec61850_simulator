#include "ipc_server.hpp"

#include <sys/epoll.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <unistd.h>

#include <cstring>
#include <iostream>
#include <thread>
#include <vector>

namespace ipc {

IpcServer::IpcServer(std::string socket_path, AsyncRequestHandler handler, size_t thread_pool_size)
    : socket_path_(std::move(socket_path)),
      async_handler_(std::move(handler)),
      thread_pool_size_(thread_pool_size > 0 ? thread_pool_size : 4) {}

IpcServer::~IpcServer() {
    stop();
}

bool IpcServer::setup_socket() {
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

    // Create epoll instance for monitoring client connections
    epoll_fd_ = ::epoll_create1(EPOLL_CLOEXEC);
    if (epoll_fd_ < 0) {
        std::perror("epoll_create1");
        ::close(server_fd_);
        server_fd_ = -1;
        return false;
    }

    // Add server socket to epoll for accepting connections
    epoll_event ev{};
    ev.events = EPOLLIN;
    ev.data.fd = server_fd_;
    if (::epoll_ctl(epoll_fd_, EPOLL_CTL_ADD, server_fd_, &ev) < 0) {
        std::perror("epoll_ctl ADD server_fd");
        ::close(epoll_fd_);
        epoll_fd_ = -1;
        ::close(server_fd_);
        server_fd_ = -1;
        return false;
    }

    running_ = true;

    // Start worker thread pool for concurrent handling
    pool_running_ = true;
    for (size_t i = 0; i < thread_pool_size_; ++i) {
        worker_threads_.emplace_back(&IpcServer::worker_thread_func, this);
    }

    // Start accept/epoll thread
    accept_thread_ = std::thread(&IpcServer::accept_loop_threaded, this);

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

    // Close server socket to unblock epoll_wait()
    if (server_fd_ >= 0) {
        ::shutdown(server_fd_, SHUT_RDWR);
        ::close(server_fd_);
        server_fd_ = -1;
    }

    // Close all client connections
    {
        std::lock_guard<std::mutex> lock(client_fds_mutex_);
        for (int fd : client_fds_) {
            ::close(fd);
        }
        client_fds_.clear();
    }

    // Close epoll
    if (epoll_fd_ >= 0) {
        ::close(epoll_fd_);
        epoll_fd_ = -1;
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

void IpcServer::handle_client_async(int client_fd, const std::string& request_data) {
    std::string response;

    try {
        response = async_handler_(request_data);
    } catch (const std::exception& e) {
        std::cerr << "Async handler error: " << e.what() << std::endl;
    }

    send_response(client_fd, response);
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

void IpcServer::accept_loop_threaded() {
    // 使用 epoll 在单个线程中高效处理所有连接和请求
    // Use epoll to efficiently handle all connections and requests in a single thread
    const int MAX_EVENTS = 32;
    epoll_event events[MAX_EVENTS];

    while (running_) {
        int nfds = ::epoll_wait(epoll_fd_, events, MAX_EVENTS, 1000); // 1s timeout
        if (nfds < 0) {
            if (running_) {
                std::perror("epoll_wait");
            }
            continue;
        }

        for (int i = 0; i < nfds; ++i) {
            int fd = events[i].data.fd;

            if (fd == server_fd_) {
                // New client connection
                int client_fd = ::accept(server_fd_, nullptr, nullptr);
                if (client_fd < 0) {
                    std::perror("accept");
                    continue;
                }

                // Add client socket to epoll for monitoring
                epoll_event cli_ev{};
                cli_ev.events = EPOLLIN | EPOLLRDHUP;
                cli_ev.data.fd = client_fd;
                if (::epoll_ctl(epoll_fd_, EPOLL_CTL_ADD, client_fd, &cli_ev) < 0) {
                    std::perror("epoll_ctl ADD client_fd");
                    ::close(client_fd);
                    continue;
                }

                // Record the client connection
                {
                    std::lock_guard<std::mutex> lock(client_fds_mutex_);
                    client_fds_.insert(client_fd);
                }
            } else {
                // Client connection has data to read or is closed
                if (events[i].events & (EPOLLRDHUP | EPOLLERR | EPOLLHUP)) {
                    // Connection closed by peer or error
                    ::epoll_ctl(epoll_fd_, EPOLL_CTL_DEL, fd, nullptr);
                    ::close(fd);

                    {
                        std::lock_guard<std::mutex> lock(client_fds_mutex_);
                        client_fds_.erase(fd);
                    }
                    continue;
                }

                if (events[i].events & EPOLLIN) {
                    // Data available to read
                    std::string request_data;
                    if (!read_request(fd, request_data)) {
                        // Read failed, close connection
                        ::epoll_ctl(epoll_fd_, EPOLL_CTL_DEL, fd, nullptr);
                        ::close(fd);

                        {
                            std::lock_guard<std::mutex> lock(client_fds_mutex_);
                            client_fds_.erase(fd);
                        }
                        continue;
                    }

                    // Queue the task for worker thread pool
                    {
                        std::lock_guard<std::mutex> lock(queue_mutex_);
                        task_queue_.push({fd, std::move(request_data)});
                    }
                    queue_cv_.notify_one();
                }
            }
        }
    }
}

} // namespace ipc
