#pragma once

#include <string>
#include <log4cplus/logger.h>

log4cplus::Logger& core_logger();
void init_logging(const std::string& config_path);
