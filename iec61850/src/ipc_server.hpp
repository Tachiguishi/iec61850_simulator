#pragma once

#include <atomic>
#include <condition_variable>
#include <functional>
#include <future>
#include <memory>
#include <mutex>
#include <queue>
#include <string>
#include <thread>
#include <vector>

namespace ipc {

class IpcServer {
public:
    /// Synchronous request handler type
    using RequestHandler = std::function<void(const std::string& request_bytes, std::string& response_bytes)>;

    /// Asynchronous request handler type (returns a future)
    using AsyncRequestHandler = std::function<std::future<std::string>(const std::string& request_bytes)>;

    /**
     * Construct IpcServer with a request handler.
     *
     * @param socket_path Path to the Unix domain socket
     * @param handler Request handler (sync or async)
     * @param thread_pool_size Number of worker threads (0 = single-threaded sync mode)
     */
    explicit IpcServer(std::string socket_path, RequestHandler handler, size_t thread_pool_size = 0);
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
    RequestHandler sync_handler_;
    AsyncRequestHandler async_handler_;
    size_t thread_pool_size_;
    int server_fd_ = -1;
    std::atomic<bool> running_{false};

    // Accept thread
    std::thread accept_thread_;

    // Thread pool members
    std::vector<std::thread> worker_threads_;
    std::queue<ClientTask> task_queue_;
    std::mutex queue_mutex_;
    std::condition_variable queue_cv_;
    std::atomic<bool> pool_running_{false};

    bool setup_socket();
    void accept_loop();
    void accept_loop_threaded();
    void worker_thread_func();
    bool read_request(int client_fd, std::string& request_data);
    void send_response(int client_fd, const std::string& response);
    void handle_client_sync(int client_fd);
    void handle_client_async(int client_fd, const std::string& request_data);
};

} // namespace ipc
