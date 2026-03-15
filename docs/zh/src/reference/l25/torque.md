# 扭矩控制

通过 `hand.torque` 控制和读取 L25 灵巧手的 16 个关节电机扭矩。

- **扭矩范围**: 0-100
- **单位**: 无量纲百分比

## 设置扭矩

```python
from linkerbot import L25
from linkerbot.hand.l25 import L25Torque

# 使用列表（16 个关节）
hand.torque.set_torques([50.0] * 16)

# 使用 L25Torque 对象
torques = L25Torque(
    thumb_abd=50.0,  # 拇指侧摆
    thumb_yaw=30.0,  # 拇指旋转
    thumb_root1=60.0,  # 拇指根部
    thumb_tip=40.0,  # 拇指指尖
    index_abd=50.0,  # 食指侧摆
    index_root1=60.0,  # 食指根部
    index_tip=40.0,  # 食指指尖
    middle_abd=50.0,  # 中指侧摆
    middle_root1=60.0,  # 中指根部
    middle_tip=40.0,  # 中指指尖
    ring_abd=50.0,  # 无名指侧摆
    ring_root1=60.0,  # 无名指根部
    ring_tip=40.0,  # 无名指指尖
    pinky_abd=50.0,  # 小指侧摆
    pinky_root1=60.0,  # 小指根部
    pinky_tip=40.0,  # 小指指尖
)
hand.torque.set_torques(torques)
```

## 读取扭矩

### 阻塞读取

```python
from linkerbot.exceptions import TimeoutError

try:
    data = hand.torque.get_blocking(timeout_ms=500)
    print(f"拇指侧摆：{data.torques.thumb_abd}")
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
from linkerbot.hand.l25 import SensorSource, TorqueEvent

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
from linkerbot import L25

with L25(side="left", interface_name="can0") as hand:
    # 设置扭矩
    hand.torque.set_torques([50.0] * 16)

    # 读取当前扭矩
    data = hand.torque.get_blocking(timeout_ms=500)
    print(f"当前扭矩：{data.torques.to_list()}")

    # 设置不同手指的扭矩
    hand.torque.set_torques(
        [
            80.0,
            80.0,
            80.0,
            80.0,  # 拇指
            60.0,
            60.0,
            60.0,  # 食指
            60.0,
            60.0,
            60.0,  # 中指
            60.0,
            60.0,
            60.0,  # 无名指
            60.0,
            60.0,
            60.0,  # 小指
        ]
    )
```
