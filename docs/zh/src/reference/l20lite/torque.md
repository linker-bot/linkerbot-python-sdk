# 扭矩控制

通过 `hand.torque` 控制和读取 L20Lite 灵巧手的 10 个关节电机扭矩。

- **扭矩范围**: 0-100
- **单位**: 无量纲百分比

## 设置扭矩

```python
from linkerbot import L20lite
from linkerbot.hand.l20lite import L20liteTorque

# 使用列表
hand.torque.set_torques([50.0, 50.0, 60.0, 60.0, 60.0, 60.0, 30.0, 30.0, 30.0, 30.0])

# 使用 L20liteTorque 对象
torques = L20liteTorque(
    thumb_flex=50.0,  # 拇指弯曲
    thumb_abd=50.0,  # 拇指侧摆
    index_flex=60.0,  # 食指弯曲
    middle_flex=60.0,  # 中指弯曲
    ring_flex=60.0,  # 无名指弯曲
    pinky_flex=60.0,  # 小指弯曲
    index_abd=30.0,  # 食指侧摆
    ring_abd=30.0,  # 无名指侧摆
    pinky_abd=30.0,  # 小指侧摆
    thumb_yaw=30.0,  # 拇指旋转
)
hand.torque.set_torques(torques)
```

## 读取扭矩

### 阻塞读取

```python
from linkerbot.exceptions import TimeoutError

try:
    data = hand.torque.get_blocking(timeout_ms=500)
    print(f"拇指弯曲：{data.torques.thumb_flex}")
    print(f"全部扭矩：{data.torques.to_list()}")
except TimeoutError:
    print("读取超时")
```

### 缓存读取

```python
data = hand.torque.get_snapshot()
if data:
    print(f"扭矩：{data.torques.to_list()}")
    print(f"时间戳：{data.timestamp}")
```

## 流式读取

通过顶层 `hand.stream()` 统一接收所有传感器事件：

```python
from linkerbot.hand.l20lite import SensorSource, TorqueEvent

hand.start_polling({SensorSource.TORQUE: 0.1})

try:
    for event in hand.stream():
        match event:
            case TorqueEvent(data=data):
                print(f"扭矩：{data.torques.to_list()}")
finally:
    hand.stop_polling()
    hand.stop_stream()
```

## 完整示例

```python
from linkerbot import L20lite
from linkerbot.hand.l20lite import L20liteTorque

with L20lite(side="left", interface_name="can0") as hand:
    # 设置扭矩
    hand.torque.set_torques([50.0] * 10)

    # 读取当前扭矩
    data = hand.torque.get_blocking(timeout_ms=500)
    print(f"当前扭矩：{data.torques.to_list()}")

    # 使用数据类精细控制
    torques = L20liteTorque(
        thumb_flex=70.0,
        thumb_abd=70.0,
        index_flex=50.0,
        middle_flex=50.0,
        ring_flex=50.0,
        pinky_flex=50.0,
        index_abd=40.0,
        ring_abd=40.0,
        pinky_abd=40.0,
        thumb_yaw=40.0,
    )
    hand.torque.set_torques(torques)
```
