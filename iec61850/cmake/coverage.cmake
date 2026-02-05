function(enable_coverage_for target_name)
  if(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
    target_compile_options(${target_name} PRIVATE -O0 -g --coverage)
    target_link_options(${target_name} PRIVATE --coverage)
  else()
    message(FATAL_ERROR "Coverage is only supported with GCC/Clang")
  endif()

  find_program(LCOV_EXECUTABLE lcov)
  find_program(GENHTML_EXECUTABLE genhtml)
  if(NOT LCOV_EXECUTABLE OR NOT GENHTML_EXECUTABLE)
    message(FATAL_ERROR "lcov/genhtml not found. Please install lcov.")
  endif()

  if(NOT TARGET coverage)
    add_custom_target(coverage
      COMMAND ${LCOV_EXECUTABLE} --directory . --zerocounters
      COMMAND ${CMAKE_CTEST_COMMAND} --output-on-failure
      COMMAND ${LCOV_EXECUTABLE} --directory . --capture --output-file coverage.info
              --ignore-errors mismatch
              --rc geninfo_unexecuted_blocks=1
      COMMAND ${LCOV_EXECUTABLE} --remove coverage.info
              '/usr/*'
              '${CMAKE_BINARY_DIR}/_deps/*'
              '${CMAKE_SOURCE_DIR}/tests/*'
              --output-file coverage.info
      COMMAND ${GENHTML_EXECUTABLE} coverage.info --output-directory coverage-report
      WORKING_DIRECTORY ${CMAKE_BINARY_DIR}
      COMMENT "Generating coverage report"
    )
  endif()

  add_dependencies(coverage ${target_name})
endfunction()
