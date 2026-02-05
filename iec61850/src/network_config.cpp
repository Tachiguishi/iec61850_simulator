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
#include <memory>

#include <log4cplus/loggingmacros.h>

// libnl3 headers
#include <netlink/netlink.h>
#include <netlink/route/link.h>
#include <netlink/route/addr.h>
#include <netlink/route/route.h>
#include <netlink/cache.h>

namespace network {

namespace {
    // Netlink 错误码常量
    constexpr int NL_ERROR_EXISTS = -17;        // EEXIST - 对象已存在
    constexpr int NL_ERROR_OBJECT_EXISTS = -NLE_EXIST; // 对象已存在（与NL_ERROR_EXISTS相同，但更具体）
    constexpr int NL_ERROR_NO_ADDR = -99;       // EADDRNOTAVAIL - 地址不存在
    constexpr int NL_ERROR_INVALID = -NLE_NOADDR;   // ENODEV - 设备或地址无效

    auto& logger() {
        static auto logger = log4cplus::Logger::getInstance("network");
        return logger;
    }
    
    // RAII 包装器：自动管理 nl_sock
    struct NlSocketDeleter {
        void operator()(nl_sock* sock) const {
            if (sock) nl_socket_free(sock);
        }
    };
    using NlSocketPtr = std::unique_ptr<nl_sock, NlSocketDeleter>;
    
    // RAII 包装器：自动管理 rtnl_addr
    struct RtnlAddrDeleter {
        void operator()(rtnl_addr* addr) const {
            if (addr) rtnl_addr_put(addr);
        }
    };
    using RtnlAddrPtr = std::unique_ptr<rtnl_addr, RtnlAddrDeleter>;
    
    // RAII 包装器：自动管理 nl_addr
    struct NlAddrDeleter {
        void operator()(nl_addr* addr) const {
            if (addr) nl_addr_put(addr);
        }
    };
    using NlAddrPtr = std::unique_ptr<nl_addr, NlAddrDeleter>;
    
    // RAII 包装器：自动管理 nl_cache
    struct NlCacheDeleter {
        void operator()(nl_cache* cache) const {
            if (cache) nl_cache_free(cache);
        }
    };
    using NlCachePtr = std::unique_ptr<nl_cache, NlCacheDeleter>;
    
    // 初始化 netlink socket（统一的辅助函数）
    NlSocketPtr init_netlink_socket() {
        nl_sock* raw_sock = nl_socket_alloc();
        if (!raw_sock) {
            LOG4CPLUS_ERROR(logger(), "Failed to allocate netlink socket");
            return nullptr;
        }
        
        NlSocketPtr sock(raw_sock);
        if (nl_connect(sock.get(), NETLINK_ROUTE) < 0) {
            LOG4CPLUS_ERROR(logger(), "Failed to connect netlink socket");
            return nullptr;
        }
        
        return sock;
    }
    
    // 获取接口索引（统一的辅助函数）
    int get_interface_index(const std::string& interface_name) {
        int if_index = if_nametoindex(interface_name.c_str());
        if (if_index == 0) {
            LOG4CPLUS_ERROR(logger(), "Failed to get interface index for " << interface_name);
        }
        return if_index;
    }
    
    // 解析IP地址为 nl_addr（统一的辅助函数）
    NlAddrPtr parse_ip_address(const std::string& ip_address, int prefix_len) {
        nl_addr* raw_addr = nullptr;
        int ret = nl_addr_parse(ip_address.c_str(), AF_INET, &raw_addr);
        if (ret < 0 || !raw_addr) {
            LOG4CPLUS_ERROR(logger(), "Failed to parse IP address: " << ip_address);
            return nullptr;
        }
        
        NlAddrPtr nl_ip(raw_addr);
        nl_addr_set_prefixlen(nl_ip.get(), prefix_len);
        return nl_ip;
    }
}

std::vector<InterfaceInfo> get_network_interfaces() {
    std::vector<InterfaceInfo> interfaces;
    
    struct ifaddrs* ifaddr = nullptr;
    if (getifaddrs(&ifaddr) == -1) {
        LOG4CPLUS_ERROR(logger(), "Failed to get network interfaces");
        return interfaces;
    }
    
    // RAII 管理 ifaddrs 资源
    struct IfaddrsDeleter {
        void operator()(ifaddrs* ifa) const { 
            if (ifa) freeifaddrs(ifa); 
        }
    };
    std::unique_ptr<ifaddrs, IfaddrsDeleter> ifaddr_guard(ifaddr);
    
    // 使用map来聚合同一网卡的多个地址
    std::map<std::string, InterfaceInfo> iface_map;
    
    for (struct ifaddrs* ifa = ifaddr; ifa != nullptr; ifa = ifa->ifa_next) {
        if (!ifa->ifa_addr) continue;
        
        const std::string name = ifa->ifa_name;
        
        // 创建或获取接口信息
        auto& info = iface_map[name];
        if (info.name.empty()) {
            info.name = name;
            info.is_up = (ifa->ifa_flags & IFF_UP) != 0;
            info.description = name;
        }
        
        // 添加IP地址
        if (ifa->ifa_addr->sa_family == AF_INET) {
            char addr_str[INET_ADDRSTRLEN];
            auto* addr = reinterpret_cast<sockaddr_in*>(ifa->ifa_addr);
            if (inet_ntop(AF_INET, &addr->sin_addr, addr_str, INET_ADDRSTRLEN)) {
                info.addresses.push_back(addr_str);
            }
        }
    }
    
    // 转换为vector，排除loopback
    interfaces.reserve(iface_map.size());
    for (const auto& [name, info] : iface_map) {
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
    auto sock = init_netlink_socket();
    if (!sock) {
        return false;
    }
    
    // 获取网卡的interface index
    int if_index = get_interface_index(interface_name);
    if (if_index == 0) {
        return false;
    }
    
    // 创建并配置地址对象（使用RAII）
    RtnlAddrPtr addr(rtnl_addr_alloc());
    if (!addr) {
        LOG4CPLUS_ERROR(logger(), "Failed to allocate address object");
        return false;
    }
    
    // 设置接口索引
    rtnl_addr_set_ifindex(addr.get(), if_index);
    
    // 解析IP地址（使用RAII）
    auto nl_ip = parse_ip_address(ip_address, prefix_len);
    if (!nl_ip) {
        return false;
    }
    
    // 设置本地地址（nl_ip会被复制，所以可以安全释放）
    rtnl_addr_set_local(addr.get(), nl_ip.get());
    
    // 设置label标签
    if (!label.empty()) {
        rtnl_addr_set_label(addr.get(), label.c_str());
    }
    
    // 添加地址
    LOG4CPLUS_INFO(logger(), "Adding IP address: " << ip_address << "/" << prefix_len 
                            << " to " << interface_name 
                            << (label.empty() ? "" : " label " + label));
    
    int ret = rtnl_addr_add(sock.get(), addr.get(), 0);
    
    // 处理返回值
    if (ret < 0 && ret != NL_ERROR_EXISTS && ret != NL_ERROR_OBJECT_EXISTS) {
        LOG4CPLUS_ERROR(logger(), "Failed to add IP address: " << nl_geterror(ret) << " (" << ret << ")");
        return false;
    }

    if (ret == NL_ERROR_EXISTS || ret == NL_ERROR_OBJECT_EXISTS) {
        LOG4CPLUS_WARN(logger(), "IP address already exists or label conflict: " << ip_address 
                                << " (error code: " << ret << ")");
    } else {
        LOG4CPLUS_INFO(logger(), "Successfully added IP " << ip_address << " to " << interface_name);
    }

    return true;
}

bool remove_ip_address(const std::string& interface_name,
                      const std::string& ip_address,
                      int prefix_len) {
    
    if (!should_configure_ip(ip_address)) {
        LOG4CPLUS_DEBUG(logger(), "IP " << ip_address << " does not need cleanup");
        return true;
    }

    auto sock = init_netlink_socket();
    if (!sock) {
        return false;
    }
    
    // 获取网卡的interface index
    int if_index = get_interface_index(interface_name);
    if (if_index == 0) {
        return false;
    }
    
    // 创建并配置地址对象（使用RAII）
    RtnlAddrPtr addr(rtnl_addr_alloc());
    if (!addr) {
        LOG4CPLUS_ERROR(logger(), "Failed to allocate address object");
        return false;
    }
    
    // 设置接口索引
    rtnl_addr_set_ifindex(addr.get(), if_index);
    
    // 解析IP地址（使用RAII）
    auto nl_ip = parse_ip_address(ip_address, prefix_len);
    if (!nl_ip) {
        return false;
    }
    
    // 设置本地地址
    rtnl_addr_set_local(addr.get(), nl_ip.get());
    
    // 删除地址
    LOG4CPLUS_INFO(logger(), "Removing IP address: " << ip_address << "/" << prefix_len 
                            << " from " << interface_name);
    
    int ret = rtnl_addr_delete(sock.get(), addr.get(), 0);
    
    // 处理返回值
    if (ret < 0 && ret != NL_ERROR_NO_ADDR && ret != NL_ERROR_INVALID) {
        LOG4CPLUS_ERROR(logger(), "Failed to remove IP address: " << nl_geterror(ret) << " (" << ret << ")");
        return false;
    }
    
    if (ret == NL_ERROR_NO_ADDR || ret == NL_ERROR_INVALID) {
        LOG4CPLUS_WARN(logger(), "IP address does not exist: " << ip_address 
                                << " (error code: " << ret << ")");
    } else {
        LOG4CPLUS_INFO(logger(), "Successfully removed IP " << ip_address << " from " << interface_name);
    }

    return true;
}

bool remove_by_label(const std::string& interface_name,
                     const std::string& label) {

    if (label.empty()) {
        LOG4CPLUS_DEBUG(logger(), "Label cannot be empty for remove_by_label");
        return false;
    }
    auto sock = init_netlink_socket();

    if (!sock) {
        return false;
    }
    
    // 获取网卡的interface index
    int if_index = get_interface_index(interface_name);
    if (if_index == 0) {
        return false;
    }
    
    // 分配地址缓存（使用RAII）
    nl_cache* raw_cache = nullptr;
    int ret = rtnl_addr_alloc_cache(sock.get(), &raw_cache);
    if (ret < 0 || !raw_cache) {
        LOG4CPLUS_ERROR(logger(), "Failed to allocate address cache: " << nl_geterror(ret));
        return false;
    }
    NlCachePtr addr_cache(raw_cache);
    
    LOG4CPLUS_INFO(logger(), "Removing addresses with label '" << label 
                            << "' from " << interface_name);

    int removed_count = 0;
    
    // 遍历地址缓存
    auto* addr = reinterpret_cast<rtnl_addr*>(nl_cache_get_first(addr_cache.get()));
    while (addr) {
        // 检查是否是目标接口
        if (rtnl_addr_get_ifindex(addr) == if_index) {
            // 获取地址的label
            const char* addr_label = rtnl_addr_get_label(addr);
            
            // 如果label匹配，删除这个地址
            if (addr_label && std::string(addr_label) == label) {
                // 获取IP地址用于日志
                std::string ip_str = "unknown";
                struct nl_addr* local = rtnl_addr_get_local(addr);
                if (local) {
                    char ip_buffer[INET_ADDRSTRLEN] = {0};
                    void* addr_data = nl_addr_get_binary_addr(local);
                    if (addr_data && inet_ntop(AF_INET, addr_data, ip_buffer, INET_ADDRSTRLEN)) {
                        ip_str = ip_buffer;
                    }
                }
                
                LOG4CPLUS_INFO(logger(), "Removing address " << ip_str 
                                        << " with label '" << label << "'");
                
                // 删除地址
                ret = rtnl_addr_delete(sock.get(), addr, 0);
                if (ret < 0 && ret != NL_ERROR_NO_ADDR) {
                    LOG4CPLUS_ERROR(logger(), "Failed to remove address: " << nl_geterror(ret));
                } else {
                    removed_count++;
                    LOG4CPLUS_DEBUG(logger(), "Successfully removed address " << ip_str);
                }
            }
        }
        
        // 获取下一个地址
        addr = reinterpret_cast<rtnl_addr*>(nl_cache_get_next(reinterpret_cast<nl_object*>(addr)));
    }
    
    if (removed_count == 0) {
        LOG4CPLUS_WARN(logger(), "No addresses found with label '" << label << "' on " << interface_name);
    } else {
        LOG4CPLUS_INFO(logger(), "Removed " << removed_count << " address(es) with label '" 
                                << label << "' from " << interface_name);
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
