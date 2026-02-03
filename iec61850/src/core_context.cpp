#include "core_context.hpp"
#include "network_config.hpp"
#include "logger.hpp"

#include <log4cplus/loggingmacros.h>

namespace {
    auto& logger() {
        static auto logger = log4cplus::Logger::getInstance("core");
        return logger;
    }
}

ServerInstanceContext::~ServerInstanceContext() {
    // IP配置由server.remove显式清理，这里只清理IEC61850资源
    
    // 清理IEC61850资源
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
