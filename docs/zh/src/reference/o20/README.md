# O20 CANFD 灵巧手

O20 是基于 CANFD 的 16 自由度灵巧手。SDK 使用 `device_id` 寻址设备，支持单只手、同一 CANFD 总线上的多只手 (左右手共享一条 bus)、以及多个 CANFD 模块/通道上的多只手。

SDK 支持两种 CAN FD 连接方式：默认使用厂商 `libcanbus.so` / `HCanbus.dll`，Linux 也可以通过 python-can 使用 SocketCAN。SocketCAN 的系统配置与连接示例见 [CAN FD 总线（L30 / O20 / O30i）](../canfd.md)。

## 厂商动态库后端准备工作

### 准备好 libcanbus.so 文件

O20 与 L30 共用同一个厂商 CANFD 动态库 (`libcanbus.so` on Linux / `HCanbus.dll` on Windows)。

资料百度网盘地址：
https://pan.baidu.com/s/1X0n7a3hkc0ZUuy-U1jf9Mg?pwd=5678
请先阅读下载说明文本文档，按需求下载。

注意 `libcanbus.so` 的版本问题，挑选对应版本，建议放进 `/usr/local/lib` 目录 (SDK 默认寻找路径),也可显式指定。

下载 `libusb` 依赖：

```bash
sudo apt update
sudo apt install -y libusb-1.0-0 libusb-1.0-0-dev libudev-dev build-essential
```

### USB 设备打开权限问题

写入权限规则到 udev 规则目录：

```bash
sudo tee /etc/udev/rules.d/hcanbus.rules >/dev/null <<'EOF'
SUBSYSTEMS=="usb", ATTRS{idVendor}=="a8fa", ATTRS{idProduct}=="8598", GROUP="plugdev", MODE="0666"
EOF
```

设置权限：

```bash
sudo chmod 644 /etc/udev/rules.d/hcanbus.rules
```

重新加载 udev 规则：

```bash
sudo udevadm control --reload-rules
sudo udevadm trigger
```

拔插一次 USB-CANFD 设备。

## 快速开始

如果 `libcanbus.so` 已安装到系统动态库搜索路径中，可以直接用 `O20()`:

```python
from linkerbot.hand.o20 import O20

with O20(side="right") as hand:
    info = hand.version.get_device_info(timeout_ms=1000)
    print(info.product_model, info.hand_side.value)

    data = hand.angle.get_blocking(timeout_ms=1000)
    print(data.angles.to_list())
```

如果动态库不在系统搜索路径中，可以显式指定：

```python
from linkerbot.hand.o20 import O20

with O20(side="right", library_path="/home/linkerhand/code/HK/libcanbus.so") as hand:
    data = hand.angle.get_blocking(timeout_ms=1000)
    print(data.angles.to_list())
```

也可以使用环境变量：

```bash
export LINKERBOT_CANFD_LIB=/home/linkerhand/code/HK/libcanbus.so
```

Linux SocketCAN 快速连接：

```python
from linkerbot.hand.o20 import O20

with O20(
    side="right",
    interface_type="socketcan",
    socketcan_channel="can0",
) as hand:
    print(hand.version.get_device_info(timeout_ms=1000))
```

运行前需要先把 `can0` 配置为 CAN FD。O20 默认使用 `frame_type=0x04`，不启用 BRS；完整说明见 [CAN FD 总线](../canfd.md)。

## 构造参数

```python
from linkerbot.hand.o20 import O20

hand = O20(
    side="right",  # "right"(默认) 或 "left",决定默认 device_id
    device_id=None,  # 显式覆盖 device_id;传 None 时由 side 决定
    device=0,  # 厂商 CANFD 适配器 index
    channel=0,  # 该适配器上的通道 index
    frame_type=0x04,  # CANFD FrameType,O20 固件期望 0x04
)
hand.close()
```

| 参数                | 类型                         | 说明                                                              |
| ------------------- | ---------------------------- | ----------------------------------------------------------------- |
| `side`              | `"left" \| "right"`          | 物理手型，决定默认 `device_id`(right=0x01,left=0x02)              |
| `device_id`         | `int \| None`                | 显式设备 ID，不传则由 `side` 派生                                 |
| `device`            | `int`                        | 厂商 CANFD 适配器 index，默认 0                                   |
| `channel`           | `int`                        | 该适配器上的通道 index，默认 0                                    |
| `library_path`      | `str \| Path \| None`        | 厂商 CANFD 动态库路径，默认走系统 loader、环境变量、包内 fallback |
| `config`            | `CANFDConfigOptions \| None` | CANFD 波特率等配置                                                |
| `frame_type`        | `int \| None`                | CANFD FrameType 字节;O20 固件期望 `0x04`(纯 CANFD 无 FDBRS)       |
| `dispatcher`        | `O20DispatcherLike \| None`  | 测试或自定义 CANFD 后端注入用;多手共享一条 bus 时也用它           |
| `interface_type`    | `"ctypes" \| "socketcan"`    | CAN FD 后端；默认 `"ctypes"`                                      |
| `socketcan_channel` | `str \| None`                | SocketCAN 接口名，例如 `"can0"`                                   |
| `bitrate`           | `int`                        | SocketCAN 仲裁速率，默认 `1_000_000`                              |
| `data_bitrate`      | `int`                        | SocketCAN 数据段配置值，默认 `5_000_000`                          |
| `auto_reconfigure`  | `bool`                       | 是否允许 SDK 重新配置 SocketCAN 接口，默认 `False`                |

推荐用 `with O20(...) as hand:`,退出代码块时会自动释放连接资源。

## 关节说明

O20 SDK 按电机 ID 顺序使用 16 个关节值 (motor ID 1~16),分布在拇指 (4 DOF)/ 食指 (3 DOF)/ 中指 (3 DOF)/ 无名指 (3 DOF)/ 小指 (3 DOF):

**角度单位**:与 L6 / L30 一致，`set_angles` 与 sensor readback 都使用 **0-100 float 百分比**;需要协议原始整数时用 `set_raw_angles` / `to_raw()`。详见 [angle](./angle.md)。

| 索引 | 关节名       | 手指   | 原始范围 (度) |
| ---: | ------------ | ------ | ------------- |
|    0 | `thumb_mcp`  | 拇指   | 0 ~ 120       |
|    1 | `thumb_ip`   | 拇指   | 0 ~ 150       |
|    2 | `thumb_abd`  | 拇指   | 0 ~ 180       |
|    3 | `thumb_cmc`  | 拇指   | 0 ~ 130       |
|    4 | `index_abd`  | 食指   | -30 ~ 30      |
|    5 | `index_mcp`  | 食指   | 0 ~ 180       |
|    6 | `index_pip`  | 食指   | 0 ~ 180       |
|    7 | `middle_abd` | 中指   | -30 ~ 30      |
|    8 | `middle_mcp` | 中指   | 0 ~ 180       |
|    9 | `middle_pip` | 中指   | 0 ~ 180       |
|   10 | `ring_abd`   | 无名指 | -20 ~ 20      |
|   11 | `ring_mcp`   | 无名指 | 0 ~ 180       |
|   12 | `ring_pip`   | 无名指 | 0 ~ 180       |
|   13 | `pinky_abd`  | 小指   | -20 ~ 20      |
|   14 | `pinky_mcp`  | 小指   | 0 ~ 180       |
|   15 | `pinky_dip`  | 小指   | 0 ~ 180       |

对称关节 (4 个外展关节 `*_abd`) 的原始范围是负 - 正对称的，**50% 百分比 = 0 度 (中立位)**;其它屈曲关节 0% = 完全张开、100% = spec.maximum。

查看每个关节的原始范围：

```python
from linkerbot.hand.o20 import O20_JOINT_SPECS

for index, spec in enumerate(O20_JOINT_SPECS):
    print(index, spec.name, spec.finger, spec.minimum, spec.maximum)
```

## 功能模块

| 模块                                                             | 说明                                             | 文档                                  |
| ---------------------------------------------------------------- | ------------------------------------------------ | ------------------------------------- |
| `hand.angle`                                                     | 角度设置 (百分比 / 原始)、角度读取、角度快照     | [angle](./angle.md)                   |
| `hand.speed`                                                     | 速度设置、速度读取、速度快照                     | [speed](./speed.md)                   |
| `hand.torque`                                                    | 力矩目标设置、力矩目标快照                       | [torque](./torque.md)                 |
| `hand.current`                                                   | 电流读取、电流快照                               | [current](./current.md)               |
| `hand.temperature`                                               | 温度读取、温度快照                               | [temperature](./temperature.md)       |
| `hand.fault`                                                     | 故障字节读取、故障判断、故障清除、故障快照       | [fault](./fault.md)                   |
| `hand.force_sensor`                                              | 五指触觉传感器读取 (单指 / 五指)                 | [force-sensor](./force-sensor.md)     |
| `hand.version`                                                   | DeviceInfo 查询 (产品编号、序列号、版本、左右手) | [version](./version.md)               |
| `hand.stream()` / `hand.start_polling()` / `hand.get_snapshot()` | 统一事件流、主机轮询、聚合快照                   | [stream-polling](./stream-polling.md) |

## 与 L30 差异

| 项                | L30                                | O20                                    |
| ----------------- | ---------------------------------- | -------------------------------------- |
| 关节数            | 17                                 | 16                                     |
| 关节命名          | `J1`~`J17`                         | `thumb_mcp`~`pinky_dip`(motor ID 顺序) |
| 通信模型          | 父命令/子命令                      | 寄存器读写                             |
| 触觉              | 单命令返回两帧                     | 每指两个 register 分别读               |
| 周期上报          | 支持 (`hand.report`)               | 无 SDK 侧配置，固件端固定行为          |
| 默认 `frame_type` | `0x0C`(带 FDBRS,5M 数据段)         | `0x04`(无 FDBRS,1M)                    |
| `device_id`       | 5 bit `NodeID`,主机 `host_id` 单独 | 8 bit 直接 device_id                   |

## 快照

`hand.get_snapshot()` 一次性返回所有 manager 的最新缓存。没有收到过的数据字段是 `None`。详见 [stream-polling](./stream-polling.md)。

## 异常处理

常见异常在 `linkerbot.exceptions` 中：

| 异常              | 说明                           |
| ----------------- | ------------------------------ |
| `ValidationError` | 参数数量、类型或范围错误       |
| `TimeoutError`    | 等待设备响应超时               |
| `StateError`      | 连接已经关闭，或队列已经关闭   |
| `CANError`        | CANFD 总线或动态库通信异常     |
| `ProtocolError`   | 响应帧格式/长度/状态码不合协议 |

```python
from linkerbot.hand.o20 import O20
from linkerbot.exceptions import CANError, TimeoutError, ValidationError

try:
    with O20(side="right") as hand:
        data = hand.angle.get_blocking(timeout_ms=1000)
        print(data.angles.to_list())
except TimeoutError:
    print("设备响应超时")
except ValidationError as error:
    print("参数错误：", error)
except CANError as error:
    print("CANFD 通信错误：", error)
```
