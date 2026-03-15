# 速度控制

通过 `hand.speed` 控制和读取 L20Lite 灵巧手各关节电机的运动速度。

- **速度范围**: 0-100
- **单位**: 无量纲（映射到关节电机实际转速）

## 设置速度

```python
from linkerbot import L20lite
from linkerbot.hand.l20lite import L20liteSpeed

# 使用列表
hand.speed.set_speeds([50.0, 50.0, 50.0, 50.0, 50.0, 50.0, 50.0, 50.0, 50.0, 50.0])

# 使用 L20liteSpeed 对象
speeds = L20liteSpeed(
    thumb_flex=30.0,  # 拇指弯曲
    thumb_abd=30.0,  # 拇指侧摆
    index_flex=80.0,  # 食指弯曲
    middle_flex=80.0,  # 中指弯曲
    ring_flex=80.0,  # 无名指弯曲
    pinky_flex=80.0,  # 小指弯曲
    index_abd=50.0,  # 食指侧摆
    ring_abd=50.0,  # 无名指侧摆
    pinky_abd=50.0,  # 小指侧摆
    thumb_yaw=50.0,  # 拇指旋转
)
hand.speed.set_speeds(speeds)
```

## 读取速度

### 阻塞读取

```python
from linkerbot.exceptions import TimeoutError

try:
    data = hand.speed.get_blocking(timeout_ms=500)
    print(f"拇指弯曲速度：{data.speeds.thumb_flex}")
    print(f"全部速度：{data.speeds.to_list()}")
except TimeoutError:
    print("读取超时")
```

### 缓存读取

```python
data = hand.speed.get_snapshot()
if data:
    print(f"速度：{data.speeds.to_list()}")
    print(f"时间戳：{data.timestamp}")
```

## 流式读取

通过顶层 `hand.stream()` 统一接收所有传感器事件：

```python
from linkerbot.hand.l20lite import SensorSource, SpeedEvent

hand.start_polling({SensorSource.SPEED: 0.1})

try:
    for event in hand.stream():
        match event:
            case SpeedEvent(data=data):
                print(f"速度：{data.speeds.to_list()}")
finally:
    hand.stop_polling()
    hand.stop_stream()
```

## 完整示例

```python
from linkerbot import L20lite
from linkerbot.hand.l20lite import L20liteSpeed

with L20lite(side="left", interface_name="can0") as hand:
    # 拇指慢速，其他手指快速
    speeds = L20liteSpeed(
        thumb_flex=20.0,
        thumb_abd=20.0,
        index_flex=80.0,
        middle_flex=80.0,
        ring_flex=80.0,
        pinky_flex=80.0,
        index_abd=60.0,
        ring_abd=60.0,
        pinky_abd=60.0,
        thumb_yaw=60.0,
    )
    hand.speed.set_speeds(speeds)

    # 读取当前速度
    data = hand.speed.get_blocking(timeout_ms=500)
    print(f"当前速度：{data.speeds.to_list()}")

    # 设置角度后观察速度效果
    hand.angle.set_angles([100.0] * 10)
```
