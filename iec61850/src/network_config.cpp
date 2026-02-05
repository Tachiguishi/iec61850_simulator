#include "network_config.hpp"
#include "logger.hpp"

#include <ifaddrs.h>
#include <net/if.h>
#include <arpa/inet.h>
#include <sys/ioctl.h>
#include <sys/socket.h>
#include <unistd.h>
#include <cstring>
#include <algorithm>
#include <map>

#include <log4cplus/loggingmacros.h>

// libnl3 headers
#include <netlink/netlink.h>
#include <netlink/route/link.h>
#include <netlink/route/addr.h>
#include <netlink/route/route.h>
#include <netlink/cache.h>

namespace network {

namespace {
    auto& logger() {
        static auto logger = log4cplus::Logger::getInstance("network");
        return logger;
    }
}

std::vector<InterfaceInfo> get_network_interfaces() {
    std::vector<InterfaceInfo> interfaces;
    
    struct ifaddrs* ifaddr;
    if (getifaddrs(&ifaddr) == -1) {
        LOG4CPLUS_ERROR(logger(), "Failed to get network interfaces");
        return interfaces;
    }
    
    // 使用map来聚合同一网卡的多个地址
    std::map<std::string, InterfaceInfo> iface_map;
    
    for (struct ifaddrs* ifa = ifaddr; ifa != nullptr; ifa = ifa->ifa_next) {
        if (ifa->ifa_addr == nullptr) continue;
        
        std::string name = ifa->ifa_name;
        
        // 创建或获取接口信息
        if (iface_map.find(name) == iface_map.end()) {
            InterfaceInfo info;
            info.name = name;
            info.is_up = (ifa->ifa_flags & IFF_UP) != 0;
            info.description = name;
            iface_map[name] = info;
        }
        
        // 添加IP地址
        if (ifa->ifa_addr->sa_family == AF_INET) {
            char addr_str[INET_ADDRSTRLEN];
            struct sockaddr_in* addr = (struct sockaddr_in*)ifa->ifa_addr;
            inet_ntop(AF_INET, &addr->sin_addr, addr_str, INET_ADDRSTRLEN);
            iface_map[name].addresses.push_back(addr_str);
        }
    }
    
    freeifaddrs(ifaddr);
    
    // 转换为vector
    for (auto& [name, info] : iface_map) {
        // 排除loopback
        if (name != "lo") {
            interfaces.push_back(info);
        }
    }
    
    return interfaces;
}

bool add_ip_address(const std::string& interface_name, 
                   const std::string& ip_address, 
                   int prefix_len,
                   const std::string& label) {
    
    if (!should_configure_ip(ip_address)) {
        LOG4CPLUS_DEBUG(logger(), "IP " << ip_address << " does not need configuration");
        return true;
    }
    
    // 初始化netlink socket
    struct nl_sock* sock = nl_socket_alloc();
    if (!sock) {
        LOG4CPLUS_ERROR(logger(), "Failed to allocate netlink socket");
        return false;
    }
    
    if (nl_connect(sock, NETLINK_ROUTE) < 0) {
        LOG4CPLUS_ERROR(logger(), "Failed to connect netlink socket");
        nl_socket_free(sock);
        return false;
    }
    
    // 获取网卡的interface index
    int if_index = if_nametoindex(interface_name.c_str());
    if (if_index == 0) {
        LOG4CPLUS_ERROR(logger(), "Failed to get interface index for " << interface_name);
        nl_socket_free(sock);
        return false;
    }
    
    // 创建并配置地址对象
    struct rtnl_addr* addr = rtnl_addr_alloc();
    if (!addr) {
        LOG4CPLUS_ERROR(logger(), "Failed to allocate address object");
        nl_socket_free(sock);
        return false;
    }
    
    // 设置接口索引
    rtnl_addr_set_ifindex(addr, if_index);
    
    // 解析IP地址
	struct nl_addr* nl_ip = nullptr;
    int ret = nl_addr_parse(ip_address.c_str(), AF_INET, &nl_ip);
    if (ret < 0 || !nl_ip) {
        LOG4CPLUS_ERROR(logger(), "Failed to parse IP address: " << ip_address);
        rtnl_addr_put(addr);
        nl_socket_free(sock);
        return false;
    }
    
    // 设置前缀长度
    nl_addr_set_prefixlen(nl_ip, prefix_len);
    rtnl_addr_set_local(addr, nl_ip);
    nl_addr_put(nl_ip);
    
    // 设置label标签
    if (!label.empty()) {
        rtnl_addr_set_label(addr, label.c_str());
    }
    
    // 添加地址
    LOG4CPLUS_INFO(logger(), "Adding IP address: " << ip_address << "/" << prefix_len 
                            << " to " << interface_name 
                            << (label.empty() ? "" : " label " + label));
    
    ret = rtnl_addr_add(sock, addr, 0);
    // -17 is EEXIST, -6 can also indicate object already exists with different label
    if (ret < 0 && ret != -17 && ret != -6) {
        LOG4CPLUS_ERROR(logger(), "Failed to add IP address: " << nl_geterror(ret) << "(" << ret << ")");
        rtnl_addr_put(addr);
        nl_socket_free(sock);
        return false;
    }

    if (ret == -17 || ret == -6) {
        LOG4CPLUS_WARN(logger(), "IP address already exists or label conflict: " << ip_address 
                                << " (error code: " << ret << ")");
    } else {
        LOG4CPLUS_INFO(logger(), "Successfully added IP " << ip_address << " to " << interface_name);
    }
    
    rtnl_addr_put(addr);
    nl_socket_free(sock);
    return true;
}

bool remove_ip_address(const std::string& interface_name,
                      const std::string& ip_address,
                      int prefix_len) {
    
    if (!should_configure_ip(ip_address)) {
        LOG4CPLUS_DEBUG(logger(), "IP " << ip_address << " does not need cleanup");
        return true;
    }
    
    // 初始化netlink socket
    struct nl_sock* sock = nl_socket_alloc();
    if (!sock) {
        LOG4CPLUS_ERROR(logger(), "Failed to allocate netlink socket");
        return false;
    }
    
    if (nl_connect(sock, NETLINK_ROUTE) < 0) {
        LOG4CPLUS_ERROR(logger(), "Failed to connect netlink socket");
        nl_socket_free(sock);
        return false;
    }
    
    // 获取网卡的interface index
    int if_index = if_nametoindex(interface_name.c_str());
    if (if_index == 0) {
        LOG4CPLUS_ERROR(logger(), "Failed to get interface index for " << interface_name);
        nl_socket_free(sock);
        return false;
    }
    
    // 创建并配置地址对象
    struct rtnl_addr* addr = rtnl_addr_alloc();
    if (!addr) {
        LOG4CPLUS_ERROR(logger(), "Failed to allocate address object");
        nl_socket_free(sock);
        return false;
    }
    
    // 设置接口索引
    rtnl_addr_set_ifindex(addr, if_index);
    
    // 解析IP地址
    struct nl_addr* nl_ip = nullptr;
    int ret = nl_addr_parse(ip_address.c_str(), AF_INET, &nl_ip);
    if (ret < 0 || !nl_ip) {
        LOG4CPLUS_ERROR(logger(), "Failed to parse IP address: " << ip_address);
        rtnl_addr_put(addr);
        nl_socket_free(sock);
        return false;
    }
    
    // 设置前缀长度
    nl_addr_set_prefixlen(nl_ip, prefix_len);
    rtnl_addr_set_local(addr, nl_ip);
    nl_addr_put(nl_ip);
    
    // 删除地址
    LOG4CPLUS_INFO(logger(), "Removing IP address: " << ip_address << "/" << prefix_len 
                            << " from " << interface_name);
    
    ret = rtnl_addr_delete(sock, addr, 0);
    // -99 is EADDRNOTAVAIL, -19 is ENODEV or invalid address
    if (ret < 0 && ret != -99 && ret != -19) {
        LOG4CPLUS_ERROR(logger(), "Failed to remove IP address: " << nl_geterror(ret) << "(" << ret << ")");
        rtnl_addr_put(addr);
        nl_socket_free(sock);
        return false;
    }
    
    if (ret == -99 || ret == -19) {
        LOG4CPLUS_WARN(logger(), "IP address does not exist: " << ip_address 
                                << " (error code: " << ret << ")");
    } else {
        LOG4CPLUS_INFO(logger(), "Successfully removed IP " << ip_address << " from " << interface_name);
    }
    
    rtnl_addr_put(addr);
    nl_socket_free(sock);
    return true;
}

bool remove_by_label(const std::string& interface_name,
                     const std::string& label) {
    
    if (label.empty()) {
        LOG4CPLUS_ERROR(logger(), "Label cannot be empty for remove_by_label");
        return false;
    }
    
    // 初始化netlink socket
    struct nl_sock* sock = nl_socket_alloc();
    if (!sock) {
        LOG4CPLUS_ERROR(logger(), "Failed to allocate netlink socket");
        return false;
    }
    
    if (nl_connect(sock, NETLINK_ROUTE) < 0) {
        LOG4CPLUS_ERROR(logger(), "Failed to connect netlink socket");
        nl_socket_free(sock);
        return false;
    }
    
    // 获取网卡的interface index
    int if_index = if_nametoindex(interface_name.c_str());
    if (if_index == 0) {
        LOG4CPLUS_ERROR(logger(), "Failed to get interface index for " << interface_name);
        nl_socket_free(sock);
        return false;
    }
    
    // 分配地址缓存
    struct nl_cache* addr_cache = nullptr;
    int ret = rtnl_addr_alloc_cache(sock, &addr_cache);
    if (ret < 0 || !addr_cache) {
        LOG4CPLUS_ERROR(logger(), "Failed to allocate address cache: " << nl_geterror(ret));
        nl_socket_free(sock);
        return false;
    }
    
    LOG4CPLUS_INFO(logger(), "Removing addresses with label '" << label 
                            << "' from " << interface_name);
    
    bool removed_any = false;
    int removed_count = 0;
    
    // 遍历地址缓存
    struct rtnl_addr* addr = (struct rtnl_addr*)nl_cache_get_first(addr_cache);
    while (addr) {
        // 检查是否是目标接口
        if (rtnl_addr_get_ifindex(addr) == if_index) {
            // 获取地址的label
            const char* addr_label = rtnl_addr_get_label(addr);
            
            // 如果label匹配，删除这个地址
            if (addr_label && std::string(addr_label) == label) {
                // 获取IP地址用于日志
                struct nl_addr* local = rtnl_addr_get_local(addr);
                char ip_str[INET_ADDRSTRLEN] = {0};
                if (local) {
                    void* addr_data = nl_addr_get_binary_addr(local);
                    if (addr_data) {
                        inet_ntop(AF_INET, addr_data, ip_str, INET_ADDRSTRLEN);
                    }
                }
                
                LOG4CPLUS_INFO(logger(), "Removing address " << ip_str 
                                        << " with label '" << label << "'");
                
                // 删除地址
                ret = rtnl_addr_delete(sock, addr, 0);
                if (ret < 0 && ret != -99) {  // -99 is EADDRNOTAVAIL
                    LOG4CPLUS_ERROR(logger(), "Failed to remove address: " << nl_geterror(ret));
                } else {
                    removed_any = true;
                    removed_count++;
                    LOG4CPLUS_DEBUG(logger(), "Successfully removed address " << ip_str);
                }
            }
        }
        
        // 获取下一个地址
        addr = (struct rtnl_addr*)nl_cache_get_next((struct nl_object*)addr);
    }
    
    nl_cache_free(addr_cache);
    nl_socket_free(sock);
    
    if (removed_any) {
        LOG4CPLUS_INFO(logger(), "Removed " << removed_count 
                                << " address(es) with label '" << label << "'");
    } else {
        LOG4CPLUS_WARN(logger(), "No addresses found with label '" << label 
                                << "' on " << interface_name);
    }
    
    return true;
}

bool should_configure_ip(const std::string& ip_address) {
    // 不配置0.0.0.0或127开头的地址
    if (ip_address == "0.0.0.0" || ip_address.substr(0, 4) == "127.") {
        return false;
    }
    return true;
}

} // namespace network
