#include "ipc_server.hpp"
#include "action_client.hpp"
#include "action_server.hpp"
#include "core_context.hpp"
#include "logger.hpp"
#include "msgpack_codec.hpp"

#include <log4cplus/initializer.h>
#include <log4cplus/loggingmacros.h>

#include <cstring>
#include <iostream>
#include <string>

#include <signal.h>
#include <sys/prctl.h>
#include <unistd.h>

int main(int argc, char** argv) {
    log4cplus::Initializer log_initializer;

    bool enable_pdeathsig = false;
    std::string socket_path = "/tmp/iec61850_simulator.sock";
    std::string config_path = "log4cplus.ini";

    for (int i = 1; i < argc; ++i) {
        if (strcmp(argv[i], "-v") == 0 || strcmp(argv[i], "--version") == 0) {
            std::cout << "Version: " << VERSION_STRING << std::endl;
            std::cout << "Commit: " << GIT_VERSION_STRING << std::endl;
            std::cout << "Build Time: " << BUILD_TIMESTAMP << std::endl;
            return 0;
        }

        if (strcmp(argv[i], "--pdeathsig") == 0) {
            enable_pdeathsig = true;
            continue;
        }

        if (strcmp(argv[i], "--config") == 0 && i + 1 < argc) {
            config_path = argv[++i];
            continue;
        }

        if (strncmp(argv[i], "--config=", 9) == 0) {
            config_path = argv[i] + 9;
            continue;
        }

        if (strcmp(argv[i], "--socket") == 0 && i + 1 < argc) {
            socket_path = argv[++i];
            continue;
        }

        if (strncmp(argv[i], "--socket=", 9) == 0) {
            socket_path = argv[i] + 9;
            continue;
        }

        if (argv[i][0] != '-') {
            socket_path = argv[i];
        }
    }

#ifdef __linux__
    if (enable_pdeathsig) {
        prctl(PR_SET_PDEATHSIG, SIGTERM);
        if (getppid() == 1) {
            return 1;
        }
    }
#endif

    init_logging(config_path);

    LOG4CPLUS_INFO(core_logger(), "iec61850_core starting");
    LOG4CPLUS_INFO(core_logger(), "Version: " << VERSION_STRING << ", Commit: " << GIT_VERSION_STRING);
    LOG4CPLUS_INFO(core_logger(), "Build Time: " << BUILD_TIMESTAMP);
    LOG4CPLUS_INFO(core_logger(), "Socket: " << socket_path);
    LOG4CPLUS_INFO(core_logger(), "Parent death signal: " << (enable_pdeathsig ? "enabled" : "disabled"));

    auto* context = new BackendContext();

    ipc::IpcServer server(socket_path, [context](const std::string& request_bytes, std::string& response_bytes) {
        msgpack::sbuffer buffer;
        msgpack::packer<msgpack::sbuffer> pk(&buffer);

        ipc::codec::Request request;
        try {
            request = ipc::codec::decode_request(request_bytes);
        } catch (const std::exception& exc) {
            LOG4CPLUS_ERROR(core_logger(), "Decode error: " << exc.what());
            pk.pack_map(4);
            pk.pack("id");
            pk.pack("");
            pk.pack("type");
            pk.pack("response");
            pk.pack("payload");
            pk.pack_map(0);
            pk.pack("error");
            ipc::codec::pack_error(pk, std::string("Decode error: ") + exc.what());
            response_bytes.assign(buffer.data(), buffer.size());
            return;
        }

        LOG4CPLUS_DEBUG(core_logger(), "IPC action: " << request.action << " id=" << request.id);

        pk.pack_map(4);
        pk.pack("id");
        pk.pack(request.id);
        pk.pack("type");
        pk.pack("response");

        if (!ipc::actions::handle_server_action(request.action, *context, request.payload, request.has_payload, pk) &&
            !ipc::actions::handle_client_action(request.action, *context, request.payload, request.has_payload, pk)) {
            LOG4CPLUS_WARN(core_logger(), "Unknown action: " << request.action);
            pk.pack("payload");
            pk.pack_map(0);
            pk.pack("error");
            ipc::codec::pack_error(pk, "Unknown action");
        }

        response_bytes.assign(buffer.data(), buffer.size());
    });

    if (!server.start()) {
        LOG4CPLUS_ERROR(core_logger(), "Failed to start IPC server");
        return 1;
    }

    LOG4CPLUS_INFO(core_logger(), "IPC server started at " << socket_path);

    while (true) {
        ::sleep(1);
    }

    return 0;
}
