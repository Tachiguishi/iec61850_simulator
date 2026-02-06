function(set_capabilities_for target_name)
	add_custom_command(TARGET ${target_name} POST_BUILD
		COMMAND ${CMAKE_COMMAND} -E echo "Setting capabilities for $<TARGET_FILE:${target_name}>"
		COMMAND sudo setcap cap_net_bind_service,cap_net_raw,cap_net_admin=+ep $<TARGET_FILE:${target_name}>
		VERBATIM
	)
endfunction()
