# IPC 协议（Unix Domain Socket + MessagePack）

## 传输
- Unix Domain Socket
- 长度前缀帧：4 字节大端长度 + MessagePack payload

## 多实例支持

为支持同时运行多个Server或Client实例，所有动作的payload中都可以包含 `instance_id` 字段用于标识目标实例。

- `instance_id`: 可选字符串，用于标识特定实例
- 如果未提供 `instance_id`，后端将使用默认实例或创建新实例
- 后端需要维护实例ID到实际Server/Client对象的映射

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

## 消息结构
消息结构使用JSON-RPC 2.0风格
### Request
```json
{
  "jsonrpc": "2.0",
  "method": "actions",
  "id": "uuid",
  "params": { ... }
}
```

### Response
```json
{
  "jsonrpc": "2.0",
  "id": "uuid",
  "result": { ... },
  "error": { code, message, data? }
}
```


## 动作列表(method)
### Server
- `server.start`
```json
{
  "jsonrpc": "2.0",
  "method": "server.start",
  "id": "uuid",
  "params": {
    "instance_id": "optional_string",
    "config": {
      "ip_address": "string", // 服务器监听的 IP 地址（可从 SCD Communication 节点获取）
      "port": number,       // 服务器监听端口（默认 102）
      "max_connections": number   // 最大连接数
    }
  }
},
{
  "jsonrpc": "2.0",
  "id": "uuid",
  "result": {
    "success": true,
    "instance_id": "string"
  }
}
```

- `server.stop`
```json
{
  "jsonrpc": "2.0",
  "method": "server.stop",
  "id": "uuid",
  "params": {
    "instance_id": "optional_string"
  }
},
{
  "jsonrpc": "2.0",
  "id": "uuid",
  "result": {
    "success": true
  }
}
```

- `server.load_model`
```json
{
  "jsonrpc": "2.0",
  "method": "server.load_model",
  "id": "uuid",
  "params": {
    "instance_id": "optional_string",
    "model": { ... } // 模型数据结构（IED、LD、LN、DO、DA 等信息）
  }
},
{
  "jsonrpc": "2.0",
  "id": "uuid",
  "result": {
    "success": true
  }
}
```
  - model 结构与 SCD Communication 节点相似，包含 IED、LD、LN、DO、DA 等信息
    - `name`: IED 名称
    - `lds`: LD 列表
    - `communication`: 通信参数字典（按访问点名称索引）
      - `ip_address`: IP 地址
      - `ip_subnet`: 子网掩码
      - `osi_ap_title`: OSI 应用进程标题
      - `osi_ae_qualifier`: OSI 应用实体限定符
      - `gse_addresses`: GSE 地址映射
      - `smv_addresses`: SMV 地址映射
- `server.set_data_value`
  - payload: `{ instance_id?: string, reference: "LdName/..", value: <any> }`
- `server.read`
```json
{
  "jsonrpc": "2.0",
  "method": "server.read",
  "id": "uuid",
  "params": {
    "instance_id": "optional_string",
    "items": [{
        "reference": "LDName/LNName[.Name[. ...]]",
        "fc": "optional_FC" // 可选功能约束过滤
      }, ...]
  }
},
{
  "jsonrpc": "2.0",
  "id": "uuid",
  "result": [
    {
      "reference": "LDName/LNName[.Name[. ...]]",
      "fc": "FC",
      "value": <any>,
      "error": null | { code, message }
    },
    ...
  ]
}
```
返回示例:
```json
{
  "id": "test-id",
  "result": [
    {
      "fc": "MX",
      "reference": "simpleIOGenericIO/GGIO1.AnIn1",
      "value": {
        "mag": {
          "f": 0.0
        },
        "q": "0000000000000",
        "t": "19700101000000.000Z"
      }
    },
    {
      "fc": "ST",
      "reference": "simpleIOGenericIO/GGIO1.SPCSO1",
      "value": {
        "q": "0000000000000",
        "stVal": false,
        "t": "19700101000000.000Z"
      }
    },
    {
      "fc": "ST",
      "reference": "simpleIOGenericIO/GGIO1.SPCSO1.q",
      "value": "0000000000000"
    }
  ]
}
```
- `server.write`
```json
{
  "jsonrpc": "2.0",
  "method": "server.write",
  "id": "uuid",
  "params": {
    "instance_id": "optional_string",
    "items": [{
        "reference": "LDName/LNName[.Name[. ...]]",
        "value": <any>
      }, ...]
  }
},
{
  "jsonrpc": "2.0",
  "id": "uuid",
  "result": [
    {
      "reference": "LDName/LNName[.Name[. ...]]",
      "success": true,
      "error": null | { code, message }
    },
    ...
  ]
}
```
示例:
```json
{
  "jsonrpc": "2.0",
  "method": "server.write",
  "id": "uuid",
  "params": {
    "instance_id": "optional_string",
    "items": [{
      "fc": "MX",
      "reference": "simpleIOGenericIO/GGIO1.AnIn1",
      "value": {
        "mag": {
          "f": 42.0
        },
        "q": "0100000000100",
        "t": "19700101000000.000Z"
      }
    },
    {
      "fc": "ST",
      "reference": "simpleIOGenericIO/GGIO1.SPCSO1",
      "value": {
        "q": "0000000000000",
        "stVal": false,
        "t": "19700101000000.000Z"
      }
    },
    {
      "fc": "ST",
      "reference": "simpleIOGenericIO/GGIO1.SPCSO1.q",
      "value": "0000000000000"
    }]
  }
}
```
















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


