
为了方便仿真程序监听102端口以及收发GOOSE报文，在不使用sudo权限的情况下，程序需要为Python解释器添加相应的网络权限（capabilities）

```sh
sudo setcap 'cap_net_bind_service,cap_net_raw,cap_net_admin=+ep' $(which python3)
```

但是在设置capabilities后，它就不再是“普通桌面应用”了,Qt会被 DBus / xdg-desktop-portal / GTK 主题系统部分拒绝访问.
导致Portal 访问失败， GNOME 主题加载失败， 窗口装饰（标题栏、关闭按钮）缺失等问题

解决方法： 将GUI程序和通信程序分离，GUI程序不需要任何特殊权限，通信程序单独运行并添加capabilities权限。

```less
[ PyQt GUI ]      ← 普通用户，无 capability
     |
     | IPC(Unix Domain Socket)
     v
[ 通信进程 ]
  - MMS :102
  - GOOSE
  - cap_net_raw
  - cap_net_bind_service
```

把GUI和通信进程分离后，GUI程序就不需要任何特殊权限，可以正常使用Portal访问文件和打印对话框，也可以正常加载GTK主题和窗口装饰。
GUI程序使用PyQt编写，通信程序使用C++编写，两者通过Unix Domain Socket进行IPC通信，通信消息使用MessagePack进行序列化和反序列化。

## 组件划分

```
GUI (Python/PyQt)
  ├─ 数据模型展示/编辑
  ├─ 操作触发
  └─ IPC 客户端 (UDS + MessagePack)

通信进程 (C++)
  ├─ IEC61850 Server / Client
  ├─ 数据读写与订阅
  └─ IPC Server (UDS + MessagePack)
```

## IPC 协议

详细协议请见 [doc/ipc_protocol.md](doc/ipc_protocol.md)。
