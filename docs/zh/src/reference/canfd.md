# CAN FD 总线（L30 / O20）

本页说明如何在 Linux 上通过 **python-can + SocketCAN** 连接 L30 和 O20。SDK 仍保留厂商动态库后端；如需使用 `libcanbus.so` / `HCanbus.dll`，请分别参考 [L30](./l30/README.md) 和 [O20](./o20/README.md)。

## 两种 CAN FD 后端

| 后端 | `interface_type` | 适用环境 | 连接参数 |
| ---- | ---------------- | -------- | -------- |
| 厂商动态库 | `"ctypes"`（默认） | Linux / Windows | `device_index`、`channel_index` 或 O20 的 `device`、`channel` |
| SocketCAN | `"socketcan"` | Linux | L30 使用 `channel="can0"`；O20 使用 `socketcan_channel="can0"` |

选择 SocketCAN 后不需要 `libcanbus.so`，但 Linux 必须已经识别 CAN 适配器，并将对应网络接口配置为 CAN FD 模式。

## 安装系统工具

`python-can` 已是 SDK 的运行依赖。建议另外安装 `iproute2` 和 `can-utils`：

```bash
sudo apt update
sudo apt install -y iproute2 can-utils
```

查看系统识别到的 CAN 接口：

```bash
ip -details link show type can
```

以下示例假设接口名为 `can0`。实际名称也可能是 `can1`、`slcan0` 等，请以系统输出为准。

## 配置 CAN FD 链路

L30 使用 1 Mbit/s 仲裁段、5 Mbit/s 数据段；协议指定仲裁段采样点 80%、数据段采样点 75%。已经处于 UP 状态的接口需要先关闭再配置：

```bash
sudo ip link set can0 down
sudo ip link set can0 type can \
  bitrate 1000000 sample-point 0.800 \
  dbitrate 5000000 dsample-point 0.750 \
  fd on
sudo ip link set can0 up
```

确认实际配置和错误计数：

```bash
ip -details -statistics link show can0
```

O20 默认发送 CAN FD 帧但不启用 bit-rate switching；同一条按上述方式配置的 CAN FD 链路可以使用，但 O20 帧本身仍按其默认 `frame_type=0x04` 发送。不要为了 O20 手动改成 L30 的 `0x0C`。

## 连接 L30

第一次连通性检查建议关闭自动周期上报，只读取设备信息，不使能电机也不发送运动命令：

```python
from linkerbot import L30

with L30(
    node_id=1,
    host_id=0,
    interface_type="socketcan",
    channel="can0",
    auto_start_periodic=False,
) as hand:
    info = hand.version.get_device_info(timeout_ms=1000)
    print(info)
```

L30 的 SocketCAN 参数：

| 参数 | 默认值 | 说明 |
| ---- | ------ | ---- |
| `interface_type` | `"ctypes"` | 使用 SocketCAN 时显式传 `"socketcan"` |
| `channel` | `None` | SocketCAN 接口名，例如 `"can0"` |
| `bitrate` | `1_000_000` | 仲裁段速率 |
| `data_bitrate` | `5_000_000` | 数据段速率 |
| `auto_reconfigure` | `False` | 是否允许 SDK 调用 `ip link` 重新配置接口 |
| `node_id` | `1` | L30 设备 NodeID，范围 1～31 |
| `host_id` | `0` | 主机节点 ID，范围 0～31 |

L30 默认使用 CAN FD+BRS，数据段会切换到 `data_bitrate`。

## 连接 O20

O20 的左右手默认使用不同设备 ID：右手为 `0x01`，左手为 `0x02`。也可以通过 `device_id` 显式覆盖。

```python
from linkerbot.hand.o20 import O20

with O20(
    side="right",
    interface_type="socketcan",
    socketcan_channel="can0",
) as hand:
    info = hand.version.get_device_info(timeout_ms=1000)
    print(info)
```

O20 的 SocketCAN 参数：

| 参数 | 默认值 | 说明 |
| ---- | ------ | ---- |
| `interface_type` | `"ctypes"` | 使用 SocketCAN 时显式传 `"socketcan"` |
| `socketcan_channel` | `None` | SocketCAN 接口名，例如 `"can0"` |
| `bitrate` | `1_000_000` | 仲裁速率 |
| `data_bitrate` | `5_000_000` | CAN FD 链路的数据段配置值 |
| `auto_reconfigure` | `False` | 是否允许 SDK 调用 `ip link` 重新配置接口 |
| `frame_type` | `0x04` | CAN FD、不启用 BRS；通常不要覆盖 |
| `side` | `"right"` | 决定默认 `device_id` |
| `device_id` | `None` | 显式覆盖 O20 设备 ID |

L30 和 O20 的 SocketCAN 接口参数名称不同，是为了保留各自原有构造函数中整数 `channel` 参数的兼容性。

## 让 SDK 配置接口

默认 `auto_reconfigure=False`，SDK 只读取并校验现有接口的 FD、仲裁速率和数据速率；配置不匹配时会给出可执行的 `ip link` 命令，不会中断其他进程正在使用的总线。

确认接口可由当前进程安全独占时，可以启用自动配置：

```python
from linkerbot import L30

with L30(
    interface_type="socketcan",
    channel="can0",
    auto_reconfigure=True,
    auto_start_periodic=False,
) as hand:
    print(hand.version.get_node_id(timeout_ms=1000))
```

自动配置要求 `CAP_NET_ADMIN`，通常需要 root 权限。当前 SDK 自动校验速率和 FD 模式，但不校验采样点；L30 需要严格满足 80%/75% 采样点时，应使用本页前面的手动配置命令。

## 监控总线

在另一个终端查看收发帧：

```bash
candump -tz -x can0
```

只查看扩展帧和 CAN FD 标志时，保留 `-x` 很有帮助。停止监控按 `Ctrl+C`。

## 关闭连接

推荐始终使用上下文管理器：

```python
with L30(interface_type="socketcan", channel="can0") as hand:
    pass
```

退出 `with` 后 SDK 会停止收发线程并关闭自己的 SocketCAN socket，但不会执行 `ip link set can0 down`。网络接口属于系统共享资源，可能仍被 `candump` 或其他进程使用。

## 常见问题

### 提示接口不存在或配置不匹配

先执行：

```bash
ip -details link show can0
```

确认接口名、`fd on`、`bitrate 1000000` 和 `dbitrate 5000000`。如果接口已 UP，修改参数前必须先执行 `sudo ip link set can0 down`。

### 能打开接口，但设备不响应

依次检查：

- 灵巧手和 CAN 适配器是否供电；
- CAN_H、CAN_L 和 GND 是否正确连接；
- 总线两端是否各有一个 120 Ω 终端电阻；
- L30 的 `node_id`，或 O20 的 `side/device_id` 是否与设备一致；
- `ip -details -statistics link show can0` 中是否出现 `bus-off`、错误计数持续增长；
- `candump -tz -x can0` 是否能看到请求帧和设备应答帧。

### `Operation not permitted`

配置网络接口需要 root 或 `CAP_NET_ADMIN`。接口配置并启动后，普通用户通常可以运行 SDK；具体权限仍取决于系统的网络和容器配置。
