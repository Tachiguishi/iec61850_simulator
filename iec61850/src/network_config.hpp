#pragma once

#include <string>
#include <vector>

namespace network {

/**
 * 网络接口信息
 */
struct InterfaceInfo {
    std::string name;           // 网卡名称 (e.g., eth0, ens33)
    std::string description;    // 描述
    std::vector<std::string> addresses;  // 已有的IP地址列表
    bool is_up;                 // 是否启用
};

/**
 * 获取系统所有网络接口列表
 */
std::vector<InterfaceInfo> get_network_interfaces();

/**
 * 添加IP地址到指定网卡（带label）
 * @param interface_name 网卡名称
 * @param ip_address IP地址
 * @param prefix_len 前缀长度（默认24）
 * @param label 标签（用于标识此IP由iec61850_simulator添加）
 * @return 成功返回true
 */
bool add_ip_address(const std::string& interface_name, 
                   const std::string& ip_address, 
                   int prefix_len = 24,
                   const std::string& label = "");

/**
 * 删除IP地址从指定网卡
 * @param interface_name 网卡名称
 * @param ip_address IP地址
 * @param prefix_len 前缀长度（默认24）
 * @return 成功返回true
 */
bool remove_ip_address(const std::string& interface_name,
                      const std::string& ip_address,
                      int prefix_len = 24);

/**
 * 通过label删除指定网卡上的所有IP地址
 * @param interface_name 网卡名称
 * @param label 标签
 * @return 成功返回true
 */
bool remove_by_label(const std::string& interface_name,
                     const std::string& label);

/**
 * 检查IP地址是否需要配置（不是0.0.0.0或127.*）
 */
bool should_configure_ip(const std::string& ip_address);

} // namespace network
