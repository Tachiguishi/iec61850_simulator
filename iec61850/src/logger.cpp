#include "logger.hpp"

#include <filesystem>

#include <log4cplus/configurator.h>
#include <log4cplus/helpers/loglog.h>

log4cplus::Logger& core_logger() {
	static log4cplus::Logger logger = log4cplus::Logger::getInstance(LOG4CPLUS_TEXT("iec61850_core"));
	return logger;
}

log4cplus::Logger& server_logger() {
	static log4cplus::Logger logger = log4cplus::Logger::getInstance(LOG4CPLUS_TEXT("iec61850_core.server"));
	return logger;
}

log4cplus::Logger& client_logger() {
	static log4cplus::Logger logger = log4cplus::Logger::getInstance(LOG4CPLUS_TEXT("iec61850_core.client"));
	return logger;
}

static std::filesystem::path resolve_config_path(const std::string& config_path) {
	std::filesystem::path path(config_path);
	if (path.is_absolute()) {
		return path;
	}

	std::filesystem::path exe_path = std::filesystem::current_path();
	std::filesystem::path resolved = exe_path / path;
	return resolved;
}

void init_logging(const std::string& config_path) {
	try {
		auto resolved = resolve_config_path(config_path);
		if (std::filesystem::exists(resolved)) {
			std::filesystem::create_directories("logs");
			log4cplus::PropertyConfigurator::doConfigure(LOG4CPLUS_STRING_TO_TSTRING(resolved.string()));
			return;
		}
	} catch (...) {
		log4cplus::helpers::LogLog::getLogLog()->error(LOG4CPLUS_TEXT("Failed to load logging config"));
	}

	log4cplus::BasicConfigurator fallback;
	fallback.configure();
	log4cplus::Logger::getRoot().setLogLevel(log4cplus::INFO_LOG_LEVEL);
}
