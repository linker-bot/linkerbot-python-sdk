# 设备信息

通过 `hand.version` 读取 O20 DeviceInfo:产品型号、序列号、软/硬件版本、左右手标志、唯一识别码。**只读**——修改 DeviceInfo(register 0x6E)不通过公开 SDK 暴露,避免用户误覆盖生产标签。

## 阻塞读取

```python
from linkerbot.hand.o20 import O20

with O20(side="right") as hand:
    info = hand.version.get_device_info(timeout_ms=1000)
    print("product_model    :", info.product_model)
    print("serial_number    :", info.serial_number)
    print("software_version :", info.software_version)
    print("hardware_version :", info.hardware_version)
    print("hand_side        :", info.hand_side.value)     # "left" / "right"
    print("unique_id        :", info.unique_id.hex())
    print("timestamp        :", info.timestamp)
```

## `O20DeviceInfo` 字段

| 字段 | 类型 | 说明 |
| ---- | ---- | ---- |
| `product_model` | `str` | 产品型号 ASCII 字符串(10 字节固定宽,去尾 `\x00`) |
| `serial_number` | `str` | 产品序列号 ASCII 字符串(20 字节固定宽) |
| `software_version` | `str` | 软件版本字符串(10 字节固定宽) |
| `hardware_version` | `str` | 硬件版本字符串(10 字节固定宽) |
| `hand_side` | `O20HandSide` | `LEFT` 或 `RIGHT` 枚举 |
| `unique_id` | `bytes` | 11 字节唯一识别码 |
| `timestamp` | `float` | 主机接收到响应的 Unix 时间戳 |

## `O20HandSide` 编码

固件按 CAN `device_id` 编码 `hand_side` 字节:

| 字节值 | `O20HandSide` | `device_id` |
| ---: | ---- | ---: |
| `1` | `O20HandSide.RIGHT` | `0x01` |
| `2` | `O20HandSide.LEFT` | `0x02` |

若读到其它值会抛 `ProtocolError`,通常是固件版本与协议对齐问题。

## 用 hand_side 反查物理手型

在开手前不知道当前 `device_id` 对应哪只手时,可以先读 DeviceInfo 确认:

```python
from linkerbot.hand.o20 import O20, O20HandSide

with O20(device_id=0x01) as hand:
    info = hand.version.get_device_info(timeout_ms=1000)
    assert info.hand_side is O20HandSide.RIGHT, (
        f"device_id=0x01 报告的是 {info.hand_side.value},硬件贴标可能反了"
    )
```

## 双手场景:分辨左右

同一 CANFD bus 上挂两只手时,DeviceInfo 是可靠的物理手型来源:

```python
from linkerbot.comm.canfd import CANFDMessageDispatcher, CANFDConfigOptions
from linkerbot.hand.o20 import O20

dispatcher = CANFDMessageDispatcher(config=CANFDConfigOptions(frame_type=0x04))
try:
    with (
        O20(side="right", dispatcher=dispatcher, frame_type=0x04) as right,
        O20(side="left",  dispatcher=dispatcher, frame_type=0x04) as left,
    ):
        for tag, hand in (("right", right), ("left", left)):
            info = hand.version.get_device_info(timeout_ms=1000)
            print(f"{tag:<5}  device_id=0x{hand.device_id:02X}  "
                  f"hand_side={info.hand_side.value}  serial={info.serial_number}")
finally:
    dispatcher.stop()
```

## 异常

| 异常 | 触发 |
| ---- | ---- |
| `TimeoutError` | 超时未收到 DeviceInfo 响应 |
| `ProtocolError` | 响应过短、hand_side 字节非 {1, 2} |
| `CANError` | CANFD bus 断线或 vendor 库通信异常 |
