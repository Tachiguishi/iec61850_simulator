aux_source_directory(. SRC_LIST)
add_executable(iec61850_core ${SRC_LIST})

target_include_directories(iec61850_core PRIVATE
	${libiec61850_SOURCE_DIR}/src/iec61850/inc
	${libiec61850_SOURCE_DIR}/src/common/inc
	${libiec61850_SOURCE_DIR}/src/mms/inc
	${libiec61850_SOURCE_DIR}/src/logging
	${libiec61850_SOURCE_DIR}/hal/inc
	${msgpack_SOURCE_DIR}/include
)
target_link_libraries(iec61850_core PRIVATE iec61850)

string(TIMESTAMP CURRENT_TIMESTAMP "%Y-%m-%d %H:%M:%S")
execute_process(
	COMMAND git describe --tags --always --dirty
	OUTPUT_VARIABLE GIT_VERSION
	OUTPUT_STRIP_TRAILING_WHITESPACE
	ERROR_QUIET
)
if(NOT GIT_VERSION)
	set(GIT_VERSION "unknown")
endif()

# msgpack-c is header-only; enforce no-Boost usage at compile time
target_compile_definitions(iec61850_core PRIVATE
	MSGPACK_NO_BOOST=1
	VERSION_STRING="${VERSION}"
	GIT_VERSION_STRING="${GIT_VERSION}"
	BUILD_TIMESTAMP="${CURRENT_TIMESTAMP}"
)
