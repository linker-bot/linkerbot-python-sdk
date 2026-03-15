# L6 灵巧手

## 快速开始

```python
from linkerbot import L6

with L6(side="left", interface_name="can0") as hand:
    # 设置角度
    hand.angle.set_angles((10, 20, 30, 40, 50, 60))

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

| 索引 | 名称     | 标识         |
| ---- | -------- | ------------ |
| 0    | 拇指弯曲 | `thumb_flex` |
| 1    | 拇指侧摆 | `thumb_abd`  |
| 2    | 食指     | `index`      |
| 3    | 中指     | `middle`     |
| 4    | 无名指   | `ring`       |
| 5    | 小指     | `pinky`      |

## 功能模块

| 模块                | 说明               | 文档                              |
| ------------------- | ------------------ | --------------------------------- |
| `hand.angle`        | 关节角度控制与读取 | [angle](./angle.md)               |
| `hand.speed`        | 运动速度控制       | [speed](./speed.md)               |
| `hand.torque`       | 扭矩控制           | [torque](./torque.md)             |
| `hand.force_sensor` | 力传感器数据       | [force-sensor](./force-sensor.md) |
| `hand.temperature`  | 温度监测           | [temperature](./temperature.md)   |
| `hand.current`      | 电流监测           | [current](./current.md)           |
| `hand.fault`        | 故障检测与清除     | [fault](./fault.md)               |
| `hand.version`      | 设备版本信息       | [version](./version.md)           |

## 统一流式读取

L6 提供统一的事件流接口，通过 `hand.stream()` 和 `hand.start_polling()` 获取所有传感器数据。初始化时会自动以默认间隔启动轮询（角度 60 Hz、力传感器 30 Hz），无需手动调用 `start_polling()`。

```python
from linkerbot import L6
from linkerbot.hand.l6 import SensorSource, AngleEvent, TemperatureEvent

with L6(side="left", interface_name="can0") as hand:
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

**SensorSource 可选值及默认频率**

| 值                          | 说明     | 默认频率   |
| --------------------------- | -------- | ---------- |
| `SensorSource.ANGLE`        | 角度     | 60 Hz      |
| `SensorSource.TORQUE`       | 扭矩     | 不默认轮询 |
| `SensorSource.TEMPERATURE`  | 温度     | 不默认轮询 |
| `SensorSource.CURRENT`      | 电流     | 不默认轮询 |
| `SensorSource.FAULT`        | 故障     | 不默认轮询 |
| `SensorSource.FORCE_SENSOR` | 力传感器 | 30 Hz      |

## 快照

获取所有传感器最新缓存数据：

```python
snap = hand.get_snapshot()
print(snap.angle)  # AngleData | None
print(snap.temperature)  # TemperatureData | None
```
