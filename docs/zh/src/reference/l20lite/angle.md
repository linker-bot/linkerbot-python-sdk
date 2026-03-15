# 角度控制

通过 `hand.angle` 控制和读取 L20Lite 灵巧手的 10 个关节电机角度。

- **角度范围**: 0-100
- **单位**: 无量纲（映射到关节电机实际角度）

## 设置角度

```python
from linkerbot import L20lite
from linkerbot.hand.l20lite import L20liteAngle

# 使用列表
hand.angle.set_angles([50.0, 30.0, 60.0, 60.0, 60.0, 60.0, 20.0, 20.0, 20.0, 20.0])

# 使用 L20liteAngle 对象
angles = L20liteAngle(
    thumb_flex=50.0,  # 拇指弯曲
    thumb_abd=30.0,  # 拇指侧摆
    index_flex=60.0,  # 食指弯曲
    middle_flex=60.0,  # 中指弯曲
    ring_flex=60.0,  # 无名指弯曲
    pinky_flex=60.0,  # 小指弯曲
    index_abd=20.0,  # 食指侧摆
    ring_abd=20.0,  # 无名指侧摆
    pinky_abd=20.0,  # 小指侧摆
    thumb_yaw=20.0,  # 拇指旋转
)
hand.angle.set_angles(angles)
```

## 读取角度

### 阻塞读取

```python
from linkerbot import L20lite
from linkerbot.exceptions import TimeoutError

try:
    data = hand.angle.get_blocking(timeout_ms=500)
    print(f"拇指弯曲：{data.angles.thumb_flex}")
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
from linkerbot.hand.l20lite import SensorSource, AngleEvent

hand.start_polling({SensorSource.ANGLE: 0.1})

try:
    for event in hand.stream():
        match event:
            case AngleEvent(data=data):
                print(f"角度：{data.angles.to_list()}")
finally:
    hand.stop_polling()
    hand.stop_stream()
```

## 完整示例

```python
from linkerbot import L20lite

with L20lite(side="left", interface_name="can0") as hand:
    # 设置角度
    hand.angle.set_angles([0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0])

    # 读取当前角度
    data = hand.angle.get_blocking(timeout_ms=500)
    print(f"当前角度：{data.angles.to_list()}")

    # 渐进移动
    for i in range(0, 101, 10):
        hand.angle.set_angles([float(i)] * 10)
```
