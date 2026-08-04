# L30 CANFD 灵巧手

L30 是基于 CANFD 的 17 关节灵巧手。SDK 使用 `node_id` 寻址设备，支持单只手、同一 CANFD 总线上的多只手，以及多个 CANFD 模块/通道上的多只手。

SDK 支持两种 CAN FD 连接方式：默认使用厂商 `libcanbus.so` / `HCanbus.dll`，Linux 也可以通过 python-can 使用 SocketCAN。SocketCAN 的系统配置与连接示例见 [CAN FD 总线（L30 / O20 / O30i）](../canfd.md)。

## 厂商动态库后端准备工作

### 准备好 libcanbus.so 文件

资料百度网盘地址：
https://pan.baidu.com/s/1X0n7a3hkc0ZUuy-U1jf9Mg?pwd=5678
请先阅读下载说明文本文档，按需求下载。

注意 `libcanbus.so` 的版本问题，挑选对应版本，建议放进`/usr/local/lib`目录 (sdk 默认寻找路径),也可显式指定，文档中有详细说明

下载`libusb`依赖

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

如果 `libcanbus.so` 已安装到系统动态库搜索路径中（例如 `/usr/local/lib`、`LD_LIBRARY_PATH` 或 `ldconfig` 缓存），可以直接使用 `L30()`：

```python
from linkerbot import L30

with L30() as hand:
    data = hand.angle.get_blocking(timeout_ms=1000)
    print(data.angles.to_list())
```

如果动态库不在系统搜索路径中，可以显式指定：

```python
from linkerbot import L30

with L30(library_path="/home/linkerhand/code/HK/libcanbus.so") as hand:
    data = hand.angle.get_blocking(timeout_ms=1000)
    print(data.angles.to_list())
```

也可以使用环境变量：

```bash
export LINKERBOT_CANFD_LIB=/home/linkerhand/code/HK/libcanbus.so
```

Linux SocketCAN 快速连接：

```python
from linkerbot import L30

with L30(
    interface_type="socketcan",
    channel="can0",
    node_id=1,
    frame_type=0x04,  # 默认值：CAN FD，不启用发送端 BRS
    auto_start_periodic=False,
) as hand:
    print(hand.version.get_device_info(timeout_ms=1000))
```

运行前需要先把 `can0` 配置为 CAN FD，完整命令和排错方法见 [CAN FD 总线](../canfd.md)。

## 构造参数

```python
from linkerbot import L30

hand = L30(
    node_id=1,
    host_id=0,
    device_index=0,
    channel_index=0,
    frame_type=0x04,
    auto_start_periodic=True,
)
hand.close()
```

| 参数                  | 类型                         | 说明                                                              |
| --------------------- | ---------------------------- | ----------------------------------------------------------------- |
| `node_id`             | `int`                        | L30 设备节点 ID，默认 `1`                                         |
| `host_id`             | `int`                        | 主机节点 ID，默认 `0`                                             |
| `device_index`        | `int`                        | 厂商动态库扫描到的第几个 CANFD 模块/适配器，默认 `0`              |
| `channel_index`       | `int`                        | 该 CANFD 模块上的第几个通道，默认 `0`                             |
| `library_path`        | `str \| Path \| None`        | 厂商 CANFD 动态库路径；默认走系统 loader、环境变量和包内 fallback |
| `config`              | `CANFDConfigOptions \| None` | CANFD 波特率等配置；不传时使用默认配置                            |
| `frame_type`          | `int \| None`                | 默认 `0x04`（FD 无 BRS）；传 `0x0C` 显式启用 FD+BRS              |
| `auto_start_periodic` | `bool`                       | 是否在初始化后自动开启默认角度周期上报，默认 `True`               |
| `dispatcher`          | `L30DispatcherLike \| None`  | 测试或自定义 CANFD 后端注入用；普通用户不需要传                   |
| `interface_type`      | `"ctypes" \| "socketcan"`    | CAN FD 后端；默认 `"ctypes"`                                      |
| `channel`             | `str \| None`                | SocketCAN 接口名，例如 `"can0"`                                   |
| `bitrate`             | `int`                        | SocketCAN 仲裁段速率，默认 `1_000_000`                            |
| `data_bitrate`        | `int`                        | SocketCAN 数据段速率，默认 `5_000_000`                            |
| `auto_reconfigure`    | `bool`                       | 是否允许 SDK 重新配置 SocketCAN 接口，默认 `False`                |

推荐使用 `with L30(...) as hand:`，退出代码块时会自动释放连接资源。
L30 的主机发送帧默认不启用 BRS；SocketCAN 链路仍应配置 5 Mbit/s 数据段，
用于接收设备可能发送的 BRS 响应。只有适配器已验证支持稳定发送 BRS 时，
才建议传 `frame_type=0x0C`。

## 关节说明

L30 SDK 按协议顺序使用 17 个关节值：`J1` 到 `J17`。所有角度、速度、力矩、电流、温度、故障数据都按这个顺序排列。

**角度单位**:与 L6 一致，`set_angles` 与 sensor readback 都使用 **0-100 float 百分比**;需要协议原始整数时用 `set_raw_angles` / `to_raw()`。详见 [angle](./angle.md)。

下表范围是协议 v6 定义的**左手默认原始位置范围**：

| 索引 | 标识  | 原始范围（左手） | 说明                                                         |
| ---- | ----- | ---------------- | ------------------------------------------------------------ |
| 0    | `J1`  | 0～900           | 拇指指根弯曲；原始值增大时手指弯曲，减小时伸直               |
| 1    | `J2`  | 0～1200          | 拇指指尖弯曲；原始值增大时手指弯曲，减小时伸直               |
| 2    | `J3`  | 0～900           | 拇指侧摆；原始值增大时向虎口侧运动                           |
| 3    | `J4`  | 0～800           | 拇指旋转；原始值增大时向手心运动                             |
| 4    | `J5`  | -200～200        | 无名指侧摆；原始值增大时向食指方向摆动，减小时向小指方向摆动 |
| 5    | `J6`  | 0～1500          | 无名指指尖弯曲；原始值增大时手指弯曲，减小时伸直             |
| 6    | `J7`  | 0～1600          | 无名指指根弯曲；原始值增大时手指弯曲，减小时伸直             |
| 7    | `J8`  | 0～1600          | 中指指根弯曲；原始值增大时手指弯曲，减小时伸直               |
| 8    | `J9`  | 0～1500          | 中指指尖弯曲；原始值增大时手指弯曲，减小时伸直               |
| 9    | `J10` | 0～1600          | 小指指根弯曲；原始值增大时手指弯曲，减小时伸直               |
| 10   | `J11` | 0～1500          | 小指指尖弯曲；原始值增大时手指弯曲，减小时伸直               |
| 11   | `J12` | -200～200        | 小指侧摆；原始值增大时向食指方向摆动，减小时向小指方向摆动   |
| 12   | `J13` | -200～200        | 中指侧摆；原始值增大时向食指方向摆动，减小时向小指方向摆动   |
| 13   | `J14` | -200～200        | 食指侧摆；原始值增大时向食指方向摆动，减小时向小指方向摆动   |
| 14   | `J15` | 0～1600          | 食指指根弯曲；原始值增大时手指弯曲，减小时伸直               |
| 15   | `J16` | 0～1500          | 食指指尖弯曲；原始值增大时手指弯曲，减小时伸直               |
| 16   | `J17` | -1000～1000      | 手腕摆动；原始值增大时向后摆动，减小时向前摆动               |

查看每个关节的角度范围：

```python
from linkerbot.hand.l30 import L30_JOINT_SPECS

for index, spec in enumerate(L30_JOINT_SPECS):
    print(index, spec.name, spec.minimum, spec.maximum)
```

## 功能模块

| 模块                                                     | 说明                                   | 文档                                |
| -------------------------------------------------------- | -------------------------------------- | ----------------------------------- |
| `hand.control`                                           | 电机使能、失能                         | [communication](./communication.md) |
| `hand.angle`                                             | 角度设置、角度读取、角度快照           | [angle](./angle.md)                 |
| `hand.speed`                                             | 速度设置、速度读取、速度快照           | [speed](./speed.md)                 |
| `hand.torque`                                            | 力矩目标设置、力矩目标快照             | [torque](./torque.md)               |
| `hand.current`                                           | 电流读取、电流快照                     | [current](./current.md)             |
| `hand.temperature`                                       | 温度读取、温度快照                     | [temperature](./temperature.md)     |
| `hand.fault`                                             | 故障字节读取、故障判断、故障快照       | [fault](./fault.md)                 |
| `hand.force_sensor`                                      | 五指触觉传感器读取                     | [force-sensor](./force-sensor.md)   |
| `hand.version`                                           | 设备编码、产品编码、NodeID、左右手查询 | [version](./version.md)             |
| `L30Bus`                                                 | 单设备、多设备/多 CANFD 模块通讯       | [communication](./communication.md) |
| `hand.report` / `hand.stream()` / `hand.start_polling()` | 周期上报、主机轮询、统一事件流         | [report-stream](./report-stream.md) |

## 快照

`hand.get_snapshot()` 会一次性返回所有 manager 的最新缓存。没有收到过的数据会是 `None`。

```python
from linkerbot import L30

with L30() as hand:
    hand.angle.get_blocking(timeout_ms=1000)
    hand.current.get_blocking(timeout_ms=1000)

    snapshot = hand.get_snapshot()
    if snapshot.angle is not None:
        print(snapshot.angle.angles.to_list())
    if snapshot.current is not None:
        print(snapshot.current.currents)
```

## 异常处理

常见异常在 `linkerbot.exceptions` 中：

| 异常              | 说明                         |
| ----------------- | ---------------------------- |
| `ValidationError` | 参数数量、类型或范围错误     |
| `TimeoutError`    | 等待设备响应超时             |
| `StateError`      | 连接已经关闭，或队列已经关闭 |
| `CANError`        | CANFD 总线或动态库通信异常   |

```python
from linkerbot import L30
from linkerbot.exceptions import CANError, TimeoutError, ValidationError

try:
    with L30() as hand:
        data = hand.angle.get_blocking(timeout_ms=1000)
        print(data.angles.to_list())
except TimeoutError:
    print("设备响应超时")
except ValidationError as error:
    print("参数错误：", error)
except CANError as error:
    print("CANFD 通信错误：", error)
```
