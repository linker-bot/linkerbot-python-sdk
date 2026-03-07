# L20Lite 灵巧手

## 快速开始

```python
from linkerbot import L20lite

with L20lite(side="left", interface_name="can0") as hand:
    # 设置角度
    hand.angle.set_angles([50, 30, 60, 60, 60, 60, 20, 20, 20, 20])

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

| 索引 | 名称       | 标识          |
| ---- | ---------- | ------------- |
| 0    | 拇指弯曲   | `thumb_flex`  |
| 1    | 拇指侧摆   | `thumb_abd`   |
| 2    | 食指弯曲   | `index_flex`  |
| 3    | 中指弯曲   | `middle_flex` |
| 4    | 无名指弯曲 | `ring_flex`   |
| 5    | 小指弯曲   | `pinky_flex`  |
| 6    | 食指侧摆   | `index_abd`   |
| 7    | 无名指侧摆 | `ring_abd`    |
| 8    | 小指侧摆   | `pinky_abd`   |
| 9    | 拇指旋转   | `thumb_yaw`   |

## 功能模块

| 模块                | 说明               |
| ------------------- | ------------------ |
| `hand.angle`        | 关节角度控制与读取 |
| `hand.speed`        | 速度控制与读取     |
| `hand.torque`       | 扭矩控制与读取     |
| `hand.temperature`  | 温度读取           |
| `hand.force_sensor` | 力传感器数据       |
| `hand.fault`        | 故障读取           |
| `hand.version`      | 设备版本信息       |

## 统一流式读取

L20Lite 提供统一的事件流接口，通过 `hand.stream()` 和 `hand.start_polling()` 获取所有传感器数据。

```python
from linkerbot import L20lite
from linkerbot.hand.l20lite import SensorSource, AngleEvent, TemperatureEvent

with L20lite(side="left", interface_name="can0") as hand:
    hand.start_polling(
        sources=[SensorSource.ANGLE, SensorSource.TEMPERATURE],
        interval_ms=100,
    )

    for event in hand.stream():
        match event:
            case AngleEvent(data=ad):
                print(f"角度：{ad.angles.to_list()}")
            case TemperatureEvent(data=td):
                print(f"温度：{td.temperatures.to_list()}")

    hand.stop_polling()
    hand.stop_stream()
```

## 快照

获取所有传感器最新缓存数据：

```python
snap = hand.get_snapshot()
print(snap.angle)  # AngleData | None
print(snap.speed)  # SpeedData | None
print(snap.torque)  # TorqueData | None
print(snap.temperature)  # TemperatureData | None
print(snap.force_sensor)  # AllFingersData | None
```
