# 运行时控制与状态

O30 的常用运行时对象在协议线上都是 36 槽向量，但实际只有 20 个关节。高层 API 的完整读写均使用[实际关节顺序](./implementation-status.md#实际关节定义)，SDK 自动跳过不存在的线上槽位。

## 位置控制

百分比 API：

```python
from linkerbot import O30

with O30() as hand:
    hand.angle.set_angles([50.0] * 20, timeout_ms=1000)
```

实物验证确认 O30 的百分比与原始字节反向换算：`0%`（张开端）对应 raw `255`，`100%`（闭合端）对应 raw `0`。百分比仍是逻辑归一化值，不是以度为单位的标定角度。

原始字节 API：

```python
with O30() as hand:
    hand.angle.set_raw_angles([0x80] * 20, timeout_ms=1000)

    # 只改五指指尖：SDK 关节索引 15～19
    hand.angle.set_raw_slice(15, [0x80] * 5, timeout_ms=1000)
```

原始 API 保持设备协议语义，不执行上述反转。对屈曲关节而言，raw 增大朝张开方向运动，raw 减小朝闭合方向运动；侧摆和横摆关节仍应按实际机械方向进行小幅验证。

切片末端不能超过 SDK 关节索引 19。以下调用会抛出 `ValidationError`，不会发帧：

```python
hand.angle.set_raw_slice(19, [1, 2])
```

稀疏位置对象 `MI=0x30` 使用与完整向量不同的固件关节编号。`set_sparse()` 的 key 使用 SDK 的 0～19 关节索引，SDK 自动转换。例如索引 15/16 是拇指/食指指尖，线上会变成稀疏关节号 4/9：

```python
hand.angle.set_sparse({15: 0x80, 16: 0x80})
# HOP data: 30 00 04 04 80 09 80
```

每个关节占两个 payload 字节；需要一次设置全部 20 个实际关节时使用 `set_raw_angles()`。

## 位置读取

```python
with O30() as hand:
    actual = hand.angle.get_blocking(timeout_ms=1000)
    print("百分比", actual.angles.to_list())
    print("原始值", actual.angles.to_raw())

    target = hand.angle.get_target_blocking(timeout_ms=1000)
    print("设定值", target.to_raw())

    # 实测仅确认完整 72 字节读取；SDK 返回 20 个实际关节
    raw_i16 = hand.angle.get_i16_blocking(timeout_ms=1000)
```

`get_blocking()` 读取 RTS=0 实际值，并更新 `get_snapshot()` 缓存；`get_target_blocking()` 使用 RTS=1 读取设定值。

## 速度、加速度、转矩和运动时间

这些 manager 接受 20 个协议原始字节：

```python
with O30() as hand:
    hand.speed.set_all(40)
    hand.acceleration.set_all(20)
    hand.torque.set_all(30)

    hand.speed.set_speeds([40] * 20)
    hand.acceleration.set_accelerations([20] * 20)
    hand.torque.set_torques([30] * 20)

    print(hand.speed.get_blocking(timeout_ms=1000).speeds)
    print(hand.acceleration.get_blocking(timeout_ms=1000).accelerations)
    print(hand.torque.get_blocking(timeout_ms=1000).torques)
```

运动时间每格为 10 ms，可使用 ticks 或严格的毫秒整数：

```python
with O30() as hand:
    hand.motion_time.set_all_ticks(10)  # 100 ms
    hand.motion_time.set_milliseconds([100] * 20)

    data = hand.motion_time.get_blocking(timeout_ms=1000)
    print(data.ticks)
    print(data.milliseconds)
```

毫秒值必须是 10 的倍数，范围为 0～2550。

## 只读运行状态

```python
with O30() as hand:
    currents = hand.current.get_blocking(timeout_ms=1000).currents
    voltages = hand.voltage.get_blocking(timeout_ms=1000).voltages
    temperatures = hand.temperature.get_blocking(timeout_ms=1000).temperatures
    faults = hand.fault.get_blocking(timeout_ms=1000)

    if faults.has_fault(0):
        print("槽 0 原始故障字节", faults.faults[0])
```

固件报告没有给出故障字节的稳定 bit 定义，SDK 只保留原始值并以“是否非零”判断该槽是否存在故障。

## 产品信息、传感器能力与诊断

```python
with O30() as hand:
    info = hand.version.get_device_info(timeout_ms=1000)
    print(info.product_model, info.protocol_name, info.protocol_version)

    sensor = hand.sensor.get_info(timeout_ms=1000)
    if not sensor.has_sensor_data:
        print("当前设备无可读触觉通道：", sensor.sensor_type)

    errors = hand.diagnostics.get_communication_errors(timeout_ms=1000)
    print(errors.latest_index, errors.history)
```

`get_device_info()` 自动重组 225 字节多帧响应。`sensor.get_info()` 先读取 `MI=0x31` 的 50 字节描述；当前 O30 实测为 `NO_SENSOR` 且总长度为 0，因此 SDK 不会假定 `0x32～0x34` 数据通道可用。

## 快照、轮询和事件流

```python
from linkerbot import O30
from linkerbot.hand.o30 import AngleEvent, SensorSource

with O30() as hand:
    stream = hand.stream(maxsize=100)
    hand.start_polling(
        {
            SensorSource.ANGLE: 1 / 30,
            SensorSource.CURRENT: 1 / 10,
            SensorSource.TEMPERATURE: 1.0,
        }
    )

    for event in stream:
        if isinstance(event, AngleEvent):
            print(event.data.angles.to_raw())
            break

    snapshot = hand.get_snapshot()
    hand.stop_polling()
    hand.stop_stream()
```

O30 没有 SDK 管理的设备端周期上报配置，`start_polling()` 是主机主动读。支持的源包括 `ANGLE`、`SPEED`、`ACCELERATION`、`CURRENT`、`VOLTAGE`、`TORQUE`、`TEMPERATURE`、`MOTION_TIME` 和 `FAULT`。
