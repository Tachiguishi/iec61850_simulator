# IPC 协议（Unix Domain Socket + MessagePack）

## 传输
- Unix Domain Socket
- 长度前缀帧：4 字节大端长度 + MessagePack payload

## 消息结构
### Request
```json
{
  "id": "uuid",
  "type": "request",
  "action": "server.start",
  "payload": { ... }
}
```

### Response
```json
{
  "id": "uuid",
  "type": "response",
  "payload": { ... },
  "error": { "message": "..." }
}
```

> `error` 为空或不存在表示成功。

## 多实例支持

为支持同时运行多个Server或Client实例，所有动作的payload中都可以包含 `instance_id` 字段用于标识目标实例。

- `instance_id`: 可选字符串，用于标识特定实例
- 如果未提供 `instance_id`，后端将使用默认实例或创建新实例
- 后端需要维护实例ID到实际Server/Client对象的映射

## 动作列表
### Server
- `server.start`
  - payload: `{ instance_id?: string, config: {...}, model: {...} }`
    - config 包含:
      - `ip_address`: 服务器监听的 IP 地址（可从 SCD Communication 节点获取）
      - `port`: 服务器监听端口（默认 102）
      - `max_connections`: 最大连接数
    - model 包含:
      - `name`: IED 名称
      - `communication`: 通信参数字典（按访问点名称索引）
        - `ip_address`: IP 地址
        - `ip_subnet`: 子网掩码
        - `osi_ap_title`: OSI 应用进程标题
        - `osi_ae_qualifier`: OSI 应用实体限定符
        - `gse_addresses`: GSE 地址映射
        - `smv_addresses`: SMV 地址映射
  - response.payload: `{ success: true, instance_id: string }`
- `server.stop`
  - payload: `{ instance_id?: string }`
- `server.load_model`
  - payload: `{ instance_id?: string, model: {...} }`
- `server.set_data_value`
  - payload: `{ instance_id?: string, reference: "IED1/LD0/..", value: <any> }`
- `server.get_values`
  - payload: `{ instance_id?: string, references: ["..."] }`
  - response.payload: `{ values: { ref: { value, quality, timestamp } } }`
- `server.get_clients`
  - payload: `{ instance_id?: string }`
  - response.payload: `{ clients: [ { id, connected_at } ] }`
- `server.list_instances` (新增)
  - payload: `{}`
  - response.payload: `{ instances: [ { instance_id, state, port, ied_name } ] }`

### Client
- `client.connect`
  - payload: `{ instance_id?: string, host, port, name, config }`
  - response.payload: `{ success: true, instance_id: string }`
- `client.disconnect`
  - payload: `{ instance_id?: string }`
- `client.browse`
  - payload: `{ instance_id?: string }`
  - response.payload: `{ model: {...} }`
- `client.read`
  - payload: `{ instance_id?: string, reference }`
  - response.payload: `{ value: { value, quality, timestamp, error } }`
- `client.read_batch`
  - payload: `{ instance_id?: string, references: [...] }`
  - response.payload: `{ values: { ref: { value, quality, timestamp, error } } }`
- `client.write`
  - payload: `{ instance_id?: string, reference, value }`
  - response.payload: `{ success: true }`
- `client.list_instances` (新增)
  - payload: `{}`
  - response.payload: `{ instances: [ { instance_id, state, target_host, target_port } ] }`


## 连接方式 - 长连接

```
Python 客户端                  C++ 服务器
    │                               │
    ├─ 建立连接 ────────────────→ 接受连接
    │                               │
    ├─ 发送请求1 ───────────────→ 读取请求1
    │                               │
    │ ◄─────────────── 发送响应1 ──┤
    │                               │
    ├─ 发送请求2 ───────────────→ 读取请求2 (连接复用 ✅)
    │                               │
    │ ◄─────────────── 发送响应2 ──┤
    │                               │
    ├─ 发送请求N ───────────────→ 读取请求N
    │                               │
    │ ◄─────────────── 发送响应N ──┤
    │                               │
    └─ 断开连接 ────────────────→ 关闭连接
```

### Python 客户端 (UDSMessageClient)

```
request()
  │
  ├─ connect()
  ├─ send()
  ├─ recv()
  │
  └─ return (保持连接)
    │
    下一次 request()
          │
    ├─ send() (复用连接)
    ├─ recv()
    └─ return
        │
    ... (可无限复用)
        │
    最后 close()
```

### C++ 服务器 (IpcServer)

```
accept_loop_threaded()
  │
  ├─ accept(client)
  │
  ├─ while running:
  │   ├─ read_request()
  │   ├─ queue_task()
  │   ├─ continue (不关闭) ✅
  │
  └─ close(client) (读取失败时)
```