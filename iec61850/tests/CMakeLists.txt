
set(OLD_CMAKE_BUILD_TYPE ${CMAKE_BUILD_TYPE})
set(CMAKE_BUILD_TYPE Release CACHE STRING "Build type" FORCE)

include(FetchContent)

FetchContent_Declare(
  googletest
  GIT_REPOSITORY git@github.com:google/googletest.git
  GIT_TAG v1.17.0
  GIT_SHALLOW TRUE
)
set(gtest_force_shared_crt ON CACHE BOOL "" FORCE)
FetchContent_MakeAvailable(googletest)

set(CMAKE_BUILD_TYPE ${OLD_CMAKE_BUILD_TYPE} CACHE STRING "Build type" FORCE)

option(ENABLE_COVERAGE "Enable coverage reporting" ON)
include(${CMAKE_CURRENT_LIST_DIR}/cmake/coverage.cmake)
include(${CMAKE_CURRENT_LIST_DIR}/cmake/capability.cmake)

add_compile_definitions(
  MSGPACK_NO_BOOST
)

include_directories(${CMAKE_CURRENT_SOURCE_DIR}
  ${CMAKE_SOURCE_DIR}/src
  ${LIBNL_INCLUDE_DIRS}
)

add_executable(network_config_tests
  network_config_test.cpp
  ${CMAKE_SOURCE_DIR}/src/network_config.cpp
  ${CMAKE_SOURCE_DIR}/src/logger.cpp
)

set_capabilities_for(network_config_tests)

target_link_libraries(network_config_tests PRIVATE
  GTest::gtest
  GTest::gtest_main
  ${LIBNL_LIBRARIES}
)

if(TARGET log4cplus::log4cplus)
  target_link_libraries(network_config_tests PRIVATE log4cplus::log4cplus)
elseif(TARGET log4cplus)
  target_link_libraries(network_config_tests PRIVATE log4cplus)
endif()

aux_source_directory(${CMAKE_SOURCE_DIR}/src/action ACTION_SRC_LIST)

add_executable(action_server_tests
  action_server_test.cpp
  test_helpers.cpp
  ${CMAKE_SOURCE_DIR}/src/msgpack_codec.cpp
  ${CMAKE_SOURCE_DIR}/src/logger.cpp
  ${CMAKE_SOURCE_DIR}/src/core_context.cpp
  ${CMAKE_SOURCE_DIR}/src/network_config.cpp
  ${ACTION_SRC_LIST}
)

target_link_libraries(action_server_tests PRIVATE
  iec61850
  GTest::gtest
  GTest::gtest_main
  ${LIBNL_LIBRARIES}
)

set_capabilities_for(action_server_tests)

if(ENABLE_COVERAGE)
  enable_coverage_for(network_config_tests)
  enable_coverage_for(action_server_tests)
endif()

if(TARGET msgpackc-cxx)
  target_link_libraries(action_server_tests PRIVATE msgpackc-cxx)
endif()

if(TARGET log4cplus::log4cplus)
  target_link_libraries(action_server_tests PRIVATE log4cplus::log4cplus)
elseif(TARGET log4cplus)
  target_link_libraries(action_server_tests PRIVATE log4cplus)
endif()

include(GoogleTest)
gtest_discover_tests(network_config_tests)
gtest_discover_tests(action_server_tests)
