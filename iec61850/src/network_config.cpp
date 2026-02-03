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
    if (ret < 0 && ret != -17) {  // -17 is EEXIST (File exists)
        LOG4CPLUS_ERROR(logger(), "Failed to add IP address: " << nl_geterror(ret));
        rtnl_addr_put(addr);
        nl_socket_free(sock);
        return false;
    }
    
    if (ret == -17) {
        LOG4CPLUS_WARN(logger(), "IP address already exists: " << ip_address);
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
    if (ret < 0 && ret != -99) {  // -99 is EADDRNOTAVAIL (Cannot assign requested address)
        LOG4CPLUS_ERROR(logger(), "Failed to remove IP address: " << nl_geterror(ret));
        rtnl_addr_put(addr);
        nl_socket_free(sock);
        return false;
    }
    
    if (ret == -99) {
        LOG4CPLUS_WARN(logger(), "IP address does not exist: " << ip_address);
    } else {
        LOG4CPLUS_INFO(logger(), "Successfully removed IP " << ip_address << " from " << interface_name);
    }
    
    rtnl_addr_put(addr);
    nl_socket_free(sock);
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
