
### 服务端模式
- [x] IPC单元测试
- [x] IPC异步通信
- [x] 启动IEC61850服务端监听102端口
- [x] 解析SCD中Communication部分，根据其中的配置监听指定的IP地址和端口(可能需要修改网卡的IP地址)
- [ ] 处理客户端连接请求，进行MMS通信
- [ ] 支持数据点的读写操作
- [ ] 支持数据点的订阅和报告
- [ ] 模拟仿真数据: 正弦波、方波、三角波，开关量等
- [ ] 数据点变化通过Chart模块实时绘制波形图
- [ ] 定值及定值组管理
- [ ] 控制命令处理
- [ ] 多个数据点变化联动
- [x] 多个服务器实例支持 (已实现ServerInstanceManager和MultiServerPanel)
- [ ] GOOSE报文发送与接收

### 客户端模式
- [ ] 连接到IEC61850服务端
- [ ] 浏览数据模型树
- [ ] 读取和写入数据点
- [ ] 控制操作 (直接控制/SBO)
- [ ] 数据订阅和轮询
- [ ] 实时数据监控与显示(Chart模块)
- [x] 多个客户端连接支持 (已实现ClientInstanceManager和MultiClientPanel)

### 多实例仿真架构 (新增)
- [x] ServerInstanceManager - 服务器实例管理器
- [x] ClientInstanceManager - 客户端实例管理器
- [x] InstanceListWidget - 实例列表可视化组件
- [x] MultiServerPanel - 多实例服务器面板
- [x] MultiClientPanel - 多实例客户端面板
- [x] IPC协议扩展支持instance_id
- [x] C++后端多实例支持 (已更新action_server.cpp和action_client.cpp)
- [x] MainWindow集成多实例面板 (通过config.gui.multi_instance配置开关)
- [x] 实例持久化配置保存/加载 (save_to_file/load_from_file)
- [x] 批量创建实例 - 从SCD文件导入多个IED (import_from_scd)
