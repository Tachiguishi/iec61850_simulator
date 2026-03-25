
# 服务端

## 载入Model

```mermaid
graph TD;
    A[开始] --> B{是否成功?};
    B -- 是 --> C[结束];
    B -- 否 --> D[重试];
    D --> B;
```
