aux_source_directory(. SRC_LIST)
aux_source_directory(action ACTION_SRC_LIST)
list(APPEND SRC_LIST ${ACTION_SRC_LIST})
add_executable(iec61850_core ${SRC_LIST})

target_include_directories(iec61850_core PRIVATE
	${LIBNL_INCLUDE_DIRS}
	${CMAKE_CURRENT_SOURCE_DIR}
)
target_link_libraries(iec61850_core PRIVATE iec61850 ${LIBNL_LIBRARIES})

if(TARGET msgpackc-cxx)
	target_link_libraries(iec61850_core PRIVATE msgpackc-cxx)
endif()

if(TARGET log4cplus::log4cplus)
	target_link_libraries(iec61850_core PRIVATE log4cplus::log4cplus)
elseif(TARGET log4cplus)
	target_link_libraries(iec61850_core PRIVATE log4cplus)
endif()

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

add_custom_command(TARGET iec61850_core POST_BUILD
	COMMAND ${CMAKE_COMMAND} -E copy_if_different
		"${CMAKE_CURRENT_SOURCE_DIR}/log4cplus.ini"
		"$<TARGET_FILE_DIR:iec61850_core>/log4cplus.ini"
	COMMAND ${CMAKE_COMMAND} -E echo "Copied log4cplus.ini to $<TARGET_FILE_DIR:iec61850_core>"
)
