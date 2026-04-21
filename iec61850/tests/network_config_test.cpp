#include <gtest/gtest.h>

#include "network_config.hpp"
#include "logger.hpp"

namespace {
class LoggingEnvironment final : public ::testing::Environment {
public:
	void SetUp() override {
		static std::once_flag once;
		std::call_once(once, []() { init_logging("../src/log4cplus.ini"); });
	}
};

::testing::Environment* const kLoggingEnvironment = ::testing::AddGlobalTestEnvironment(new LoggingEnvironment());
}

class NetworkConfigTest : public ::testing::Test {
protected:
	static std::string test_interface;

	static void SetUpTestSuite() {
		if(!test_interface.empty()) {
			return;
		}
		auto interfaces = network::get_network_interfaces();
		for (const auto& iface : interfaces) {
			if (iface.name.find("br-") != 0 && iface.name.find("docker") != 0) {
				test_interface = iface.name;
				break;
			}
		}
		ASSERT_FALSE(test_interface.empty()) << "No valid test interface found";
	}
};

std::string NetworkConfigTest::test_interface = ""; // 测试网卡名称，根据实际环境调整，为空则自动选择

TEST_F(NetworkConfigTest, GetNetworkInterfacesReturnsNonEmptyListAndValidData) {
	auto interfaces = network::get_network_interfaces();
	EXPECT_FALSE(interfaces.empty());

	for (const auto& iface : interfaces) {
		EXPECT_FALSE(iface.name.empty());
		EXPECT_FALSE(iface.description.empty());
		EXPECT_NE(iface.name, "lo");
		// 地址列表可以为空，但不应包含空字符串
		std::cout << "Interface: " << iface.name << ", Description: " << iface.description << std::endl;
		for (const auto& addr : iface.addresses) {
			EXPECT_FALSE(addr.empty());
			std::cout << "  Address: " << addr << std::endl;
		}
	}
}

TEST_F(NetworkConfigTest, SetIpAddressAndRemovesIpSuccessfully) {
	const std::string test_ip = "172.16.1.99";
	const int prefix_len = 24;
	const std::string test_label = "test_label";

	ASSERT_TRUE(network::add_ip_address(test_interface, test_ip, prefix_len, test_label));

	// 验证IP已添加
	auto interfaces = network::get_network_interfaces();
	bool ip_found = false;
	for (const auto& iface : interfaces) {
		if (iface.name == test_interface || iface.name == test_label) {
			for (const auto& addr : iface.addresses) {
				std::cout << "address: " << addr << std::endl;
				if (addr == test_ip) {
					ip_found = true;
					break;
				}
			}
		}
	}
	ASSERT_TRUE(ip_found) << "IP address not found on interface after addition";
	
	// 再次添加相同IP应成功但无实际更改
	EXPECT_TRUE(network::add_ip_address(test_interface, test_ip, prefix_len, test_label)) << "Failed to add same IP address again";
	
	// 移除IP
	EXPECT_TRUE(network::remove_ip_address(test_interface, test_ip, prefix_len)) << "Failed to remove IP address";
	
	// 再次移除相同IP应成功但无实际更改
	EXPECT_TRUE(network::remove_ip_address(test_interface, test_ip, prefix_len)) << "Failed to remove IP address on non-existent IP";
}

TEST_F(NetworkConfigTest, SetIpAddressAndRemoveByLabelSuccessfully) {
	const std::string test_ip1 = "172.16.1.100";
	const std::string test_ip2 = "172.16.1.101";
	const std::string test_ip3 = "172.16.1.102";
	const std::string test_label = "iec61850";
	const int prefix_len = 24;

	ASSERT_TRUE(network::add_ip_address(test_interface, test_ip1, prefix_len));
	ASSERT_TRUE(network::add_ip_address(test_interface, test_ip2, prefix_len));
	ASSERT_TRUE(network::add_ip_address(test_interface, test_ip3, prefix_len));

	// 验证IP已添加
	auto interfaces = network::get_network_interfaces();
	int found_count = 0;
	for (const auto& iface : interfaces) {
		if (iface.name == test_interface || iface.name == test_label) {
			for (const auto& addr : iface.addresses) {
				std::cout << "address: " << addr << std::endl;
				if (addr == test_ip1 || addr == test_ip2 || addr == test_ip3) {
					found_count++;
				}
			}
		}
	}
	ASSERT_EQ(found_count, 3) << "Not all IP addresses found on interface after addition";

	// 通过标签移除IP
	EXPECT_TRUE(network::remove_by_label(test_interface)) << "Failed to remove IP addresses by label";
}

TEST_F(NetworkConfigTest, ShouldConfigureIpReturnsFalseForInvalidAddresses) {
	EXPECT_FALSE(network::should_configure_ip("0.0.0.0"));
	EXPECT_FALSE(network::should_configure_ip("127.0.0.1"));
	EXPECT_TRUE(network::should_configure_ip("192.168.1.1"));
}
