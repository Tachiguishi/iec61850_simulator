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

## 动作列表
### Server
- `server.start`
  - payload: `{ config: {...}, model: {...} }`
  - response.payload: `{ success: true }`
- `server.stop`
  - payload: `{}`
- `server.load_model`
  - payload: `{ model: {...} }`
- `server.set_data_value`
  - payload: `{ reference: "IED1/LD0/..", value: <any> }`
- `server.get_values`
  - payload: `{ references: ["..."] }`
  - response.payload: `{ values: { ref: { value, quality, timestamp } } }`
- `server.get_clients`
  - response.payload: `{ clients: [ { id, connected_at } ] }`

### Client
- `client.connect`
  - payload: `{ host, port, name, config }`
- `client.disconnect`
  - payload: `{}`
- `client.browse`
  - response.payload: `{ model: {...} }`
- `client.read`
  - payload: `{ reference }`
  - response.payload: `{ value: { value, quality, timestamp, error } }`
- `client.read_batch`
  - payload: `{ references: [...] }`
  - response.payload: `{ values: { ref: { value, quality, timestamp, error } } }`
- `client.write`
  - payload: `{ reference, value }`
  - response.payload: `{ success: true }`
