# 快速开始

## 连接灵巧手

```python
from linkerbot import L6

with L6(side="left", interface_name="can0") as hand:
    # 控制和读取灵巧手
    pass
```

使用 `with` 语句确保资源正确释放。

## 控制关节角度

设置 6 个关节的目标角度（范围 0-100）：

```python
from linkerbot import L6

with L6(side="left", interface_name="can0") as hand:
    # 张开手掌
    hand.angle.set_angles([100, 50, 100, 100, 100, 100])

    # 握拳
    hand.angle.set_angles([0, 0, 0, 0, 0, 0])
```

关节顺序：`[拇指弯曲, 拇指侧摆, 食指, 中指, 无名指, 小指]`

## 读取角度

```python
with L6(side="left", interface_name="can0") as hand:
    # 阻塞读取
    data = hand.angle.get_blocking(timeout_ms=100)
    print(f"当前角度：{data.angles.to_list()}")

    # 访问单个关节
    print(f"食指：{data.angles.index}")
```

## 读取力传感器

获取 5 个手指的力传感器数据：

```python
with L6(side="left", interface_name="can0") as hand:
    data = hand.force_sensor.get_blocking(timeout_ms=1000)

    # 访问各手指数据
    print(f"拇指：{data.thumb.values.shape}")  # (12, 6)
    print(f"食指：{data.index.values.shape}")
```

## 流式读取

通过统一事件流持续接收数据。初始化时会自动以默认间隔启动轮询（角度 60 Hz、力传感器 30 Hz），也可手动调用 `start_polling()` 覆盖：

```python
from linkerbot.hand.l6 import SensorSource, AngleEvent

with L6(side="left", interface_name="can0") as hand:
    # 初始化已自动启动默认轮询（角度 + 力传感器）
    # 如需自定义，可再次调用 start_polling() 覆盖
    hand.start_polling({SensorSource.ANGLE: 0.1})

    for event in hand.stream():
        match event:
            case AngleEvent(data=data):
                print(f"角度：{data.angles.to_list()}")

        if should_stop():
            break

    hand.stop_polling()
    hand.stop_stream()
```

## 完整示例

```python
from linkerbot import L6
import time

with L6(side="left", interface_name="can0") as hand:
    # 设置速度
    hand.speed.set_speeds([50, 50, 50, 50, 50, 50])

    # 张开
    hand.angle.set_angles([100, 50, 100, 100, 100, 100])
    time.sleep(1)

    # 握拳
    hand.angle.set_angles([0, 0, 0, 0, 0, 0])
    time.sleep(1)

    # 读取状态
    angles = hand.angle.get_blocking()
    temps = hand.temperature.get_blocking()

    print(f"角度：{angles.angles.to_list()}")
    print(f"温度：{temps.temperatures.to_list()} °C")
```

## 下一步

- [基础知识](basics.md) - 了解 SDK 架构
- [角度控制](../reference/l6/angle.md) - 详细 API
- [力传感器](../reference/l6/force-sensor.md) - 力传感器详解
