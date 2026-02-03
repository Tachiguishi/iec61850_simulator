cmake_minimum_required(VERSION 3.18)
project(iec61850_backend LANGUAGES CXX)
set(VERSION "0.1.0")

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

option(DEBUG_BUILD "Build with debug info" ON)
option(BUILD_CORE_TESTS "Build iec61850 core tests" ${DEBUG_BUILD})

set(CMAKE_BUILD_TYPE Release CACHE STRING "Build type" FORCE)
include(FetchContent)

set(FETCHCONTENT_QUIET OFF)

FetchContent_Declare(
	libiec61850
	GIT_REPOSITORY git@github.com:mz-automation/libiec61850.git
	GIT_TAG v1.6
	GIT_SHALLOW TRUE
)
set(BUILD_EXAMPLES OFF CACHE BOOL "Build libiec61850 examples" FORCE)

FetchContent_Declare(
	msgpack
	GIT_REPOSITORY git@github.com:msgpack/msgpack-c.git
	GIT_TAG cpp-7.0.0
	GIT_SHALLOW TRUE
)
set(MSGPACK_CXX17 ON CACHE BOOL "Use C++17 features" FORCE)
set(MSGPACK_USE_BOOST OFF CACHE BOOL "Disable Boost usage" FORCE)
set(MSGPACK_BUILD_DOCS OFF CACHE BOOL "Disable building docs" FORCE)

FetchContent_Declare(
	log4cplus
	GIT_REPOSITORY git@github.com:log4cplus/log4cplus.git
	GIT_TAG REL_2_1_2
	GIT_SHALLOW TRUE
	GIT_SUBMODULES_RECURSE TRUE
)
set(WITH_UNIT_TESTS OFF CACHE BOOL "log4cplus unit tests" FORCE)
set(LOG4CPLUS_BUILD_TESTING OFF CACHE BOOL "log4cplus testing" FORCE)
set(LOG4CPLUS_BUILD_LOGGINGSERVER OFF CACHE BOOL "log4cplus logging server" FORCE)

FetchContent_MakeAvailable(libiec61850 msgpack log4cplus)

# Find libnl
find_package(PkgConfig REQUIRED)
pkg_check_modules(LIBNL REQUIRED libnl-3.0 libnl-route-3.0)

if(DEBUG_BUILD)
	set(CMAKE_BUILD_TYPE Debug CACHE STRING "Build type" FORCE)
endif()

add_subdirectory(./src)

if(BUILD_CORE_TESTS)
	enable_testing()
	add_subdirectory(./tests)
endif()
