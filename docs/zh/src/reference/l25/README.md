# L25 灵巧手

## 快速开始

```python
from linkerbot import L25

with L25(side="left", interface_name="can0") as hand:
    # 设置角度
    hand.angle.set_angles([50.0] * 16)

    # 读取角度
    data = hand.angle.get_blocking(timeout_ms=500)
    print(data.angles)
```

**构造参数**

| 参数             | 类型                  | 说明                                                                          |
| ---------------- | --------------------- | ----------------------------------------------------------------------------- |
| `side`           | `"left"` \| `"right"` | 左手或右手                                                                    |
| `interface_name` | `str`                 | CAN 接口名，如 `"can0"`                                                       |
| `interface_type` | `str`                 | CAN 接口类型，默认 `"socketcan"`。Windows 用法参考 [CAN 总线](../can.md) 文档 |

## 关节说明

L25 灵巧手拥有 16 个自由度，分布在 5 根手指上。

| 索引 | 名称       | 标识           |
| ---- | ---------- | -------------- |
| 0    | 拇指侧摆   | `thumb_abd`    |
| 1    | 拇指旋转   | `thumb_yaw`    |
| 2    | 拇指根部   | `thumb_root1`  |
| 3    | 拇指指尖   | `thumb_tip`    |
| 4    | 食指侧摆   | `index_abd`    |
| 5    | 食指根部   | `index_root1`  |
| 6    | 食指指尖   | `index_tip`    |
| 7    | 中指侧摆   | `middle_abd`   |
| 8    | 中指根部   | `middle_root1` |
| 9    | 中指指尖   | `middle_tip`   |
| 10   | 无名指侧摆 | `ring_abd`     |
| 11   | 无名指根部 | `ring_root1`   |
| 12   | 无名指指尖 | `ring_tip`     |
| 13   | 小指侧摆   | `pinky_abd`    |
| 14   | 小指根部   | `pinky_root1`  |
| 15   | 小指指尖   | `pinky_tip`    |

## 功能模块

| 模块                | 说明               |
| ------------------- | ------------------ |
| `hand.angle`        | 关节角度控制与读取 |
| `hand.speed`        | 速度控制与读取     |
| `hand.torque`       | 扭矩控制与读取     |
| `hand.temperature`  | 温度读取           |
| `hand.force_sensor` | 力传感器数据       |
| `hand.fault`        | 故障读取与清除     |
| `hand.version`      | 设备版本信息       |

## 统一流式读取

L25 提供统一的事件流接口，通过 `hand.stream()` 和 `hand.start_polling()` 获取所有传感器数据。初始化时会自动以默认间隔启动轮询（角度 60 Hz、力传感器 30 Hz），无需手动调用 `start_polling()`。

```python
from linkerbot import L25
from linkerbot.hand.l25 import SensorSource, AngleEvent, TemperatureEvent

with L25(side="left", interface_name="can0") as hand:
    # 可同时指定多个传感器及各自的轮询间隔（秒）
    # 再次调用 start_polling() 会覆盖之前的设置
    hand.start_polling({SensorSource.ANGLE: 0.05, SensorSource.TEMPERATURE: 1.0})

    for event in hand.stream():
        match event:
            case AngleEvent(data=ad):
                print(f"角度：{ad.angles.to_list()}")
            case TemperatureEvent(data=td):
                print(f"温度：{td.temperatures.to_list()}")

    hand.stop_polling()
    hand.stop_stream()
```

**start_polling 参数**

| 参数        | 类型                        | 默认值     | 说明                       |
| ----------- | --------------------------- | ---------- | -------------------------- |
| `intervals` | `dict[SensorSource, float]` | 全部默认值 | 每个传感器的轮询间隔（秒） |

**SensorSource 可选值及默认频率**

| 值                          | 说明     | 默认频率   |
| --------------------------- | -------- | ---------- |
| `SensorSource.ANGLE`        | 角度     | 60 Hz      |
| `SensorSource.SPEED`        | 速度     | 不默认轮询 |
| `SensorSource.TORQUE`       | 扭矩     | 不默认轮询 |
| `SensorSource.TEMPERATURE`  | 温度     | 不默认轮询 |
| `SensorSource.FAULT`        | 故障     | 不默认轮询 |
| `SensorSource.FORCE_SENSOR` | 力传感器 | 30 Hz      |

## 快照

获取所有传感器最新缓存数据：

```python
snap = hand.get_snapshot()
print(snap.angle)  # AngleData | None
print(snap.speed)  # SpeedData | None
print(snap.torque)  # TorqueData | None
print(snap.temperature)  # TemperatureData | None
print(snap.fault)  # FaultData | None
print(snap.force_sensor)  # AllFingersData | None
```
