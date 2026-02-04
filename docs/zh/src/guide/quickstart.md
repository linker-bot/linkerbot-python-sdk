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
    hand.angle.set_angles([0, 0, 0, 0, 0, 0])

    # 握拳
    hand.angle.set_angles([100, 50, 100, 100, 100, 100])
```

关节顺序：`[拇指弯曲, 拇指外展, 食指, 中指, 无名指, 小指]`

## 读取角度

```python
with L6(side="left", interface_name="can0") as hand:
    # 阻塞读取
    data = hand.angle.get_angles_blocking(timeout_ms=100)
    print(f"当前角度：{data.angles.to_list()}")

    # 访问单个关节
    print(f"食指：{data.angles.index}")
```

## 读取力传感器

获取 5 个手指的力传感器数据：

```python
with L6(side="left", interface_name="can0") as hand:
    data = hand.force_sensor.get_data_blocking(timeout_ms=1000)

    # 访问各手指数据
    print(f"拇指：{data.thumb.values.shape}")  # (12, 6)
    print(f"食指：{data.index.values.shape}")
```

## 流式读取

持续接收数据：

```python
with L6(side="left", interface_name="can0") as hand:
    queue = hand.angle.stream(interval_ms=100, maxsize=10)

    for data in queue:
        print(f"角度：{data.angles.to_list()}")

        if should_stop():
            break

    hand.angle.stop_streaming()
```

## 完整示例

```python
from linkerbot import L6
import time

with L6(side="left", interface_name="can0") as hand:
    # 设置速度
    hand.speed.set_speeds([50, 50, 50, 50, 50, 50])

    # 张开
    hand.angle.set_angles([0, 0, 0, 0, 0, 0])
    time.sleep(1)

    # 握拳
    hand.angle.set_angles([100, 50, 100, 100, 100, 100])
    time.sleep(1)

    # 读取状态
    angles = hand.angle.get_angles_blocking()
    temps = hand.temperature.get_temperatures_blocking()

    print(f"角度：{angles.angles.to_list()}")
    print(f"温度：{temps.temperatures.to_list()} °C")
```

## 下一步

- [基础知识](basics.md) - 了解 SDK 架构
- [角度控制](../reference/l6/angle.md) - 详细 API
- [力传感器](../reference/l6/force-sensor.md) - 力传感器详解
