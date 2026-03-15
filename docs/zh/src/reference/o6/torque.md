# 扭矩控制

通过 `hand.torque` 控制和读取 O6 灵巧手的 6 个关节电机扭矩。

- **扭矩范围**: 0-100（无量纲百分比）
- **最大电流**: 1657.5 mA（对应 100）

## 设置扭矩

```python
from linkerbot import O6
from linkerbot.hand.o6 import O6Torque

# 使用列表
hand.torque.set_torques([50.0, 30.0, 60.0, 60.0, 60.0, 60.0])

# 使用 O6Torque 对象
torques = O6Torque(
    thumb_flex=50.0,  # 拇指屈曲
    thumb_abd=30.0,  # 拇指侧摆
    index=60.0,  # 食指
    middle=60.0,  # 中指
    ring=60.0,  # 无名指
    pinky=60.0,  # 小指
)
hand.torque.set_torques(torques)

# 使用 mA 单位
torques = O6Torque.from_milliamps([800.0, 800.0, 1000.0, 1000.0, 1000.0, 1000.0])
hand.torque.set_torques(torques)
```

## 读取扭矩

### 阻塞读取

```python
from linkerbot.exceptions import TimeoutError

try:
    data = hand.torque.get_blocking(timeout_ms=500)
    print(f"拇指屈曲：{data.torques.thumb_flex}")
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
from linkerbot.hand.o6 import SensorSource, TorqueEvent

hand.start_polling({SensorSource.TORQUE: 0.1})

for event in hand.stream():
    match event:
        case TorqueEvent(data=data):
            print(f"扭矩：{data.torques.to_list()}")

hand.stop_polling()
hand.stop_stream()
```

## mA 单位转换

O6 支持扭矩值与 mA 电流单位的相互转换。

### 从 mA 创建

```python
from linkerbot.hand.o6 import O6Torque

# 从 mA 值创建（范围 0-1657.5 mA）
torques = O6Torque.from_milliamps([800.0, 800.0, 1000.0, 1000.0, 1200.0, 1200.0])
print(f"归一化值：{torques.to_list()}")  # 转换为 0-100 范围
```

### 转换为 mA

```python
torques = O6Torque(50.0, 50.0, 50.0, 50.0, 50.0, 50.0)
ma_values = torques.to_milliamps()
print(f"mA 值：{ma_values}")  # [828.75, 828.75, ...]
```

## 完整示例

```python
from linkerbot import O6
from linkerbot.hand.o6 import O6Torque

with O6(side="left", interface_name="can0") as hand:
    # 设置扭矩
    hand.torque.set_torques([50.0, 50.0, 50.0, 50.0, 50.0, 50.0])

    # 读取当前扭矩
    data = hand.torque.get_blocking(timeout_ms=500)
    print(f"当前扭矩：{data.torques.to_list()}")
    print(f"对应 mA: {data.torques.to_milliamps()}")

    # 使用 mA 单位设置
    torques = O6Torque.from_milliamps([1000.0] * 6)
    hand.torque.set_torques(torques)
```
