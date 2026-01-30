cmake_minimum_required(VERSION 3.16)
project(iec61850_backend LANGUAGES CXX)
set(VERSION "0.1.0")

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

include(FetchContent)

set(FETCHCONTENT_QUIET OFF)

FetchContent_Declare(
	libiec61850
	GIT_REPOSITORY git@github.com:mz-automation/libiec61850.git
	GIT_TAG v1.6
	GIT_SHALLOW TRUE
)

FetchContent_Declare(
	msgpack
	GIT_REPOSITORY git@github.com:msgpack/msgpack-c.git
	GIT_TAG cpp-7.0.0
	GIT_SHALLOW TRUE
)

set(BUILD_EXAMPLES OFF CACHE BOOL "Build libiec61850 examples" FORCE)
set(MSGPACK_CXX17 ON CACHE BOOL "Use C++17 features" FORCE)
set(MSGPACK_USE_BOOST OFF CACHE BOOL "Disable Boost usage" FORCE)
set(MSGPACK_BUILD_DOCS OFF CACHE BOOL "Disable building docs" FORCE)
FetchContent_MakeAvailable(libiec61850 msgpack)

add_subdirectory(./src)
enable_testing()
add_subdirectory(./tests)
