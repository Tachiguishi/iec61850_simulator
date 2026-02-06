#pragma once

#include <atomic>
#include <condition_variable>
#include <functional>
#include <future>
#include <memory>
#include <mutex>
#include <queue>
#include <set>
#include <string>
#include <thread>
#include <vector>

namespace ipc {

class IpcServer {
public:
    /// Asynchronous request handler type (returns a future)
    using AsyncRequestHandler = std::function<std::string(const std::string& request_bytes)>;

    /**
     * Construct IpcServer with an asynchronous request handler.
     *
     * @param socket_path Path to the Unix domain socket
     * @param handler Asynchronous request handler
     * @param thread_pool_size Number of worker threads (default = 4)
     */
    explicit IpcServer(std::string socket_path, AsyncRequestHandler handler, size_t thread_pool_size = 4);
    ~IpcServer();

    /// Start the server (blocking mode if thread_pool_size == 0)
    bool start();

    /// Stop the server
    void stop();

    /// Check if server is running
    bool is_running() const { return running_.load(); }

    /// Get the socket path
    const std::string& socket_path() const { return socket_path_; }

private:
    struct ClientTask {
        int client_fd;
        std::string request_data;
    };

    std::string socket_path_;
    AsyncRequestHandler async_handler_;
    size_t thread_pool_size_;
    int server_fd_ = -1;
    int epoll_fd_ = -1;
    std::atomic<bool> running_{false};

    // Accept thread
    std::thread accept_thread_;

    // Thread pool members
    std::vector<std::thread> worker_threads_;
    std::queue<ClientTask> task_queue_;
    std::mutex queue_mutex_;
    std::condition_variable queue_cv_;
    std::atomic<bool> pool_running_{false};

    // Client connections management
    std::set<int> client_fds_;
    std::mutex client_fds_mutex_;

    bool setup_socket();
    void accept_loop_threaded();
    void worker_thread_func();
    bool read_request(int client_fd, std::string& request_data);
    void send_response(int client_fd, const std::string& response);
    void handle_client_async(int client_fd, const std::string& request_data);
};

} // namespace ipc
