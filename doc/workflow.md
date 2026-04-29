
# 服务端

## 基础流程

### 载入模型 server.load_model
```mermaid
sequenceDiagram;
    autonumber
    participant UI
    participant Server
    participant Action
    UI->>Server: 发送Model数据
    Note right of UI: server.load_model
    opt 已有Model
        Server->>+Action: 删除已有Model数据
        Action->>-Server: 删除完成
    end
    Server->>+Action: 创建IedModel示例
    Action->>-Server: 创建完成
    opt 已有IedServer实例
        Server->>+Action: 销毁已有IedServer实例
        Action->>-Server: 销毁完成
    end
    Server->>+Action: 创建IedServer实例
    Action->>-Server: 创建完成
    Server->>UI: 载入完成
```

测试用例:
ActionServer.
  StartMissingPayloadReturnsError
  LoadModelMissingPayloadReturnsError
  SetDataValueInvalidRequestReturnsError
  GetValuesInvalidRequestReturnsError
  GetClientsReturnsPayload
  LoadModelAndStartServerReturnsSuccess

- 载入一个Model数据，验证载入完成
  * `ActionServerModelTest.LoadDefaultModelReturnsSuccess`
  * `ActionServerModelTest.LoadReportModelReturnsSuccess`
  * `ActionServerModelTest.LoadControlModelReturnsSuccess`
  * `ActionServerModelTest.LoadSettingGroupModelReturnsSuccess`
- 载入一个Model数据后再载入另一个Model数据，验证旧数据被删除且新数据载入完成
  * `ActionServerModelTest.ReloadModelReplacesExistingModel`

### 启动服务 server.start
前置条件: 模型已加载
```mermaid
sequenceDiagram;
    autonumber
    participant UI
    participant Server
    participant Action
    UI->>Server: 启动服务
    Server->>UI: 服务启动完成
```

测试用例:
- 启动服务后验证服务启动完成
  * `ActionServer.StartServerReturnsSuccess`

### 读取数据
```mermaid
sequenceDiagram;
    autonumber
    participant UI
    participant Server
    participant Action
    UI->>Server: 请求数据
    Note right of UI: server.get_data
    Server->>+Action: 读取数据
    Action->>-Server: 返回数据
    Server->>UI: 返回数据
```
测试用例:
- 未加载模型时请求数据，验证返回错误
  * `ActionServerOperationTest.GetValuesInvalidRequestReturnsError`
- 请求的Reference不存在，验证返回错误
  * `ActionServerOperationTest.GetValuesNonExistentReferenceReturnsError`
- 请求数据，验证返回正确数据
  * `ActionServerOperationTest.GetValuesValidReferenceReturnsValue`

## 数据变更联动

# 客户端

## 基础流程

```mermaid
sequenceDiagram;
    participant UI
    participant Client
    UI->>Client: 服务器地址
    Client->>UI: 连接服务器并载入模型
    loop 连接状态变更
        Client->>UI: 连接状态
    end
    alt 请求单点数据
        UI->>Client: 请求单点数据
        Client->>UI: 返回单点数据
    else 请求数据集数据
        UI->>Client: 请求数据集数据
        Client->>UI: 返回数据集数据
    else 请求定值数据
        UI->>Client: 请求定值数据
        Client->>UI: 返回定值数据
    else 订阅Report控制块
        UI->>Client: 订阅Report控制块
        Client->>UI: Report控制块数据变更通知
    else 设定单点数据
        UI->>Client: 设定单点数据
        Client->>UI: 返回设定结果
    else 设定定值数据
        UI->>Client: 设定定值数据
        Client->>UI: 返回设定结果
    else 取消订阅Report控制块
        UI->>Client: 取消订阅Report控制块
        Client->>UI: 取消订阅结果
    else 控制命令
        UI->>Client: 发送控制命令
        Client->>UI: 返回控制结果
    else 断开连接
        UI->>Client: 断开连接
        Client->>UI: 断开结果
    end
```
