# 速度控制

通过 `hand.speed` 控制和读取 L25 灵巧手各关节电机的运动速度。

- **速度范围**: 0-100
- **单位**: 无量纲

## 设置速度

```python
from linkerbot import L25
from linkerbot.hand.l25 import L25Speed

# 使用列表（16 个关节）
hand.speed.set_speeds([50.0] * 16)

# 使用 L25Speed 对象
speed = L25Speed(
    thumb_abd=30.0,  # 拇指侧摆
    thumb_yaw=30.0,  # 拇指旋转
    thumb_root1=30.0,  # 拇指根部
    thumb_tip=30.0,  # 拇指指尖
    index_abd=80.0,  # 食指侧摆
    index_root1=80.0,  # 食指根部
    index_tip=80.0,  # 食指指尖
    middle_abd=80.0,  # 中指侧摆
    middle_root1=80.0,  # 中指根部
    middle_tip=80.0,  # 中指指尖
    ring_abd=80.0,  # 无名指侧摆
    ring_root1=80.0,  # 无名指根部
    ring_tip=80.0,  # 无名指指尖
    pinky_abd=80.0,  # 小指侧摆
    pinky_root1=80.0,  # 小指根部
    pinky_tip=80.0,  # 小指指尖
)
hand.speed.set_speeds(speed)
```

## 读取速度

### 阻塞读取

```python
from linkerbot import L25
from linkerbot.exceptions import TimeoutError

try:
    data = hand.speed.get_blocking(timeout_ms=500)
    print(f"拇指侧摆速度：{data.speeds.thumb_abd}")
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
from linkerbot.hand.l25 import SensorSource, SpeedEvent

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
from linkerbot import L25
from linkerbot.hand.l25 import L25Speed

with L25(side="left", interface_name="can0") as hand:
    # 设置速度
    speed = L25Speed(
        thumb_abd=30.0,
        thumb_yaw=30.0,
        thumb_root1=30.0,
        thumb_tip=30.0,
        index_abd=80.0,
        index_root1=80.0,
        index_tip=80.0,
        middle_abd=80.0,
        middle_root1=80.0,
        middle_tip=80.0,
        ring_abd=80.0,
        ring_root1=80.0,
        ring_tip=80.0,
        pinky_abd=80.0,
        pinky_root1=80.0,
        pinky_tip=80.0,
    )
    hand.speed.set_speeds(speed)

    # 读取当前速度
    data = hand.speed.get_blocking(timeout_ms=500)
    print(f"当前速度：{data.speeds.to_list()}")
```
