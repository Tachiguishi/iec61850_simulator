#include "logger.hpp"

#include <log4cplus/logger.h>
#include <log4cplus/consoleappender.h>

log4cplus::Logger& core_logger() {
	static log4cplus::Logger logger = []{
		log4cplus::Logger l = log4cplus::Logger::getInstance(LOG4CPLUS_TEXT("iec61850_core"));
		log4cplus::tstring pattern = LOG4CPLUS_TEXT("%D{%Y-%m-%d %H:%M:%S %Q} %p[%t]: %m%n");
		log4cplus::SharedAppenderPtr appender(new log4cplus::ConsoleAppender());
		std::unique_ptr<log4cplus::Layout> layout(new log4cplus::PatternLayout(pattern));
		appender->setLayout(std::move(layout));
		l.addAppender(appender);
		l.setLogLevel(log4cplus::ALL_LOG_LEVEL);
		return l;
	}();
	return logger;
}
