
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

add_executable(action_server_tests
  action_server_test.cpp
  test_helpers.cpp
  ../src/action_server.cpp
  ../src/msgpack_codec.cpp
  ../src/logger.cpp
)

add_compile_definitions(
  MSGPACK_NO_BOOST
)

option(ENABLE_COVERAGE "Enable coverage reporting" ON)
include(${CMAKE_CURRENT_LIST_DIR}/../cmake/coverage.cmake)

target_include_directories(action_server_tests PRIVATE
  ${CMAKE_CURRENT_SOURCE_DIR}
  ${CMAKE_CURRENT_SOURCE_DIR}/../src
  ${libiec61850_SOURCE_DIR}/src/iec61850/inc
  ${libiec61850_SOURCE_DIR}/src/common/inc
  ${libiec61850_SOURCE_DIR}/src/mms/inc
  ${libiec61850_SOURCE_DIR}/src/logging
  ${libiec61850_SOURCE_DIR}/hal/inc
  ${msgpack_SOURCE_DIR}/include
)

target_link_libraries(action_server_tests PRIVATE
  iec61850
  GTest::gtest
  GTest::gtest_main
)

if(ENABLE_COVERAGE)
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
gtest_discover_tests(action_server_tests)
