# O30 CAN FD 灵巧手

O30 使用 HandProtocol_v1.0（协议名 HOP）。当前固件实测使用 11 位标准 CAN ID：上位机请求 `0x001`，设备响应 `0x401`；报文为 CAN FD、无 BRS（`frame_type=0x04`）。SDK 支持两种后端：

| 后端                 | 参数                              | 平台            | 说明                                |
| -------------------- | --------------------------------- | --------------- | ----------------------------------- |
| 厂商动态库           | `interface_type="ctypes"`（默认） | Linux / Windows | 使用 `libcanbus.so` / `HCanbus.dll` |
| python-can SocketCAN | `interface_type="socketcan"`      | Linux           | 使用系统 `can0` 等 CAN FD 网络接口  |

## 快速开始

厂商动态库后端：

```python
from linkerbot import O30

with O30(library_path="/usr/local/lib/libcanbus.so") as hand:
    info = hand.version.get_device_info(timeout_ms=1000)
    print(info.product_model, info.protocol_name, info.protocol_version)

    actual = hand.angle.get_blocking(timeout_ms=1000)
    print(actual.angles.to_raw())
```

也可以省略 `library_path`，让 SDK 按系统 loader、`LINKERBOT_CANFD_LIB` 环境变量和包内 fallback 顺序查找动态库。

Linux SocketCAN 后端：

```bash
sudo ip link set can0 down
sudo ip link set can0 type can bitrate 1000000 dbitrate 5000000 fd on
sudo ip link set can0 up
```

```python
from linkerbot import O30

with O30(
    interface_type="socketcan",
    socketcan_channel="can0",
) as hand:
    print(hand.version.get_device_info(timeout_ms=1000))
```

完整的 SocketCAN 配置和排错方式见 [CAN FD 总线](../canfd.md)。

完整实物诊断示例位于 `examples/o30_full_demo.py`。默认只读，不会发送运动命令：

```bash
uv run python examples/o30_full_demo.py --channel can0
```

显式点动一个真实关节时使用 `--move`；程序会要求再次输入 `MOVE`，并在退出前恢复原始位置：

```bash
uv run python examples/o30_full_demo.py \
    --channel can0 --move --joint tip_1 --delta-raw 8
```

## 构造参数

```python
from linkerbot import O30

hand = O30(
    request_id=0x001,
    response_id=None,
    device=0,
    channel=0,
    frame_type=0x04,
)
hand.close()
```

| 参数                | 类型                                   | 说明                                       |
| ------------------- | -------------------------------------- | ------------------------------------------ |
| `request_id`        | `int`                                  | 11 位标准帧请求 ID，默认 `0x001`           |
| `response_id`       | `int \| None`                          | 响应 ID；`None` 时为 `request_id \| 0x400` |
| `device`            | `int`                                  | 厂商 CAN FD 适配器索引，默认 0             |
| `channel`           | `int`                                  | 厂商适配器通道索引，默认 0                 |
| `library_path`      | `str \| Path \| None`                  | `libcanbus.so` / `HCanbus.dll` 路径        |
| `config`            | `CANFDConfigOptions \| None`           | 厂商适配器配置                             |
| `frame_type`        | `int \| None`                          | 默认 `0x04`（CAN FD、无 BRS）              |
| `dispatcher`        | `HandProtocolV1DispatcherLike \| None` | 测试、自定义传输或共享 dispatcher          |
| `interface_type`    | `"ctypes" \| "socketcan"`              | 默认 `"ctypes"`                            |
| `socketcan_channel` | `str \| None`                          | SocketCAN 接口名，例如 `"can0"`            |
| `bitrate`           | `int`                                  | SocketCAN 仲裁速率，默认 1 Mbit/s          |
| `data_bitrate`      | `int`                                  | SocketCAN 数据段配置值，默认 5 Mbit/s      |
| `auto_reconfigure`  | `bool`                                 | 是否允许 SDK 配置 SocketCAN 链路           |

推荐始终使用 `with O30(...) as hand:`，确保收发线程和底层连接被释放。

## 20 个实际关节

固件运行时对象包含 36 个单字节槽位，但 O30 实际只存在 20 个关节。SDK 读取完整 36 字节后只返回真实关节；完整写入会自动跳过不存在的槽位。

当前只确认协议原始范围为 `0～255`，没有可靠的角度标定值。实物验证确认 O30 的原始值方向与 SDK 逻辑百分比相反：`0%` 是张开端、对应 raw `255`；`100%` 是闭合端、对应 raw `0`。`set_raw_angles()`、原始切片和稀疏写始终使用设备原生方向，不做反转。

| 索引范围 | 标识                 | 说明                     |
| -------: | -------------------- | ------------------------ |
|        0 | `roll_0`             | 拇指侧摆                 |
|     1～5 | `yaw_0`～`yaw_4`     | 拇指横摆及食指到小指侧摆 |
|    6～10 | `root1_0`～`root1_4` | 五指指根 1               |
|   11～14 | `root2_1`～`root2_4` | 食指到小指指根 2         |
|   15～19 | `tip_0`～`tip_4`     | 五指指尖                 |

完整 ID、名称、线上 SI、默认值、已实现和未实现功能见[实现状态与测试范围](./implementation-status.md)。

程序中可通过 `O30_JOINT_SPECS` 获取同一张表：

```python
from linkerbot.hand.o30 import O30_JOINT_SPECS

for index, spec in enumerate(O30_JOINT_SPECS):
    print(index, spec.name, spec.minimum, spec.maximum)
```

## 功能模块

| 模块                | 说明                                                    |
| ------------------- | ------------------------------------------------------- |
| `hand.angle`        | 位置百分比/原始值控制，实际值/设定值/完整 16 位对象读取 |
| `hand.speed`        | 速度原始字节读写                                        |
| `hand.acceleration` | 加速度原始字节读写                                      |
| `hand.current`      | 电流状态读取                                            |
| `hand.voltage`      | 电压状态读取                                            |
| `hand.torque`       | 转矩原始字节读写                                        |
| `hand.temperature`  | 温度状态读取                                            |
| `hand.motion_time`  | 运动时间读写，每格 10 ms                                |
| `hand.fault`        | 原始故障字节读取                                        |
| `hand.version`      | 225 字节产品与版本信息读取                              |
| `hand.sensor`       | 触觉能力信息读取；先判断 `total_data_length`            |
| `hand.diagnostics`  | `MI=0x4F` 通信错误历史读取                              |
| `hand.protocol`     | 传输无关 HandProtocol_v1.0 原始对象读写                 |

常用操作见 [运行时控制与状态](./runtime.md)，HOP 帧格式及高级访问见 [HandProtocol_v1.0](./hand-protocol-v1.md)。

## 实测安全边界

O30 当前固件与早期协议文档有若干不一致，SDK 的高层接口有意遵循以下边界：

- `MI=0x00` 关节映射无可靠响应，不提供高层配置接口；
- `MI=0x0C` 使能掩码通信可通但功能不生效，不作为使能状态；
- `MI=0x20` 只提供完整 72 字节读取，不提供局部读写；
- `MI=0x21～0x26` 实测对象长度与旧文档不一致，不做强类型封装；
- `MI=0x35` 配置连续写受限，不封装恢复、保存等危险命令；
- `MI=0x42` 工程服务可能进入 Bootloader、升级或恢复出厂，不提供高层写接口；
- `MI=0x31` 报告 `total_data_length=0` 时，不读取 `0x32～0x34` 数据通道。

确需访问尚未封装的已确认对象时可使用 `hand.protocol`，调用者需要自行承担固件版本与写入语义风险。
