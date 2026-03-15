# 角度控制

通过 `hand.angle` 控制和读取 L6 灵巧手的 6 个关节电机角度。

- **角度范围**: 0-100
- **单位**: 无量纲（映射到关节电机实际角度）

## 设置角度

```python
from linkerbot import L6
from linkerbot.hand.l6 import L6Angle

# 使用列表
hand.angle.set_angles([50.0, 30.0, 60.0, 60.0, 60.0, 60.0])

# 使用 L6Angle 对象
angles = L6Angle(
    thumb_flex=50.0,  # 拇指屈曲
    thumb_abd=30.0,  # 拇指侧摆
    index=60.0,  # 食指
    middle=60.0,  # 中指
    ring=60.0,  # 无名指
    pinky=60.0,  # 小指
)
hand.angle.set_angles(angles)
```

## 读取角度

### 阻塞读取

```python
from linkerbot import L6
from linkerbot.exceptions import TimeoutError

try:
    data = hand.angle.get_blocking(timeout_ms=500)
    print(f"拇指屈曲：{data.angles.thumb_flex}")
    print(f"全部角度：{data.angles.to_list()}")
except TimeoutError:
    print("读取超时")
```

### 缓存读取

```python
data = hand.angle.get_snapshot()
if data:
    print(f"角度：{data.angles.to_list()}")
    print(f"时间戳：{data.timestamp}")
```

## 流式读取

通过顶层 `hand.stream()` 统一接收所有传感器事件：

```python
from linkerbot.hand.l6 import SensorSource, AngleEvent

hand.start_polling({SensorSource.ANGLE: 0.1})

for event in hand.stream():
    match event:
        case AngleEvent(data=data):
            print(f"角度：{data.angles.to_list()}")

hand.stop_polling()
hand.stop_stream()
```

## 完整示例

```python
from linkerbot import L6

with L6(side="left", interface_name="can0") as hand:
    # 设置角度
    hand.angle.set_angles([0.0, 0.0, 0.0, 0.0, 0.0, 0.0])

    # 读取当前角度
    data = hand.angle.get_blocking(timeout_ms=500)
    print(f"当前角度：{data.angles.to_list()}")

    # 渐进移动
    for i in range(0, 101, 10):
        hand.angle.set_angles([float(i)] * 6)
```
