# 加速度控制

通过 `hand.acceleration` 控制和读取 O6 灵巧手的 6 个关节电机加速度。

- **加速度范围**: 0-100
- **最大加速度**: 2209.8 deg/s²（对应值 100）

## 设置加速度

```python
from linkerbot import O6
from linkerbot.hand.o6 import O6Acceleration

# 使用列表
hand.acceleration.set_accelerations([80.0, 80.0, 80.0, 80.0, 80.0, 80.0])

# 使用 O6Acceleration 对象
accel = O6Acceleration(
    thumb_flex=80.0,  # 拇指屈曲
    thumb_abd=80.0,  # 拇指侧摆
    index=80.0,  # 食指
    middle=80.0,  # 中指
    ring=80.0,  # 无名指
    pinky=80.0,  # 小指
)
hand.acceleration.set_accelerations(accel)
```

## 读取加速度

### 阻塞读取

```python
from linkerbot import O6
from linkerbot.exceptions import TimeoutError

try:
    data = hand.acceleration.get_blocking(timeout_ms=500)
    print(f"拇指屈曲：{data.accelerations.thumb_flex}")
    print(f"全部加速度：{data.accelerations.to_list()}")
except TimeoutError:
    print("读取超时")
```

### 缓存读取

```python
data = hand.acceleration.get_snapshot()
if data:
    print(f"加速度：{data.accelerations.to_list()}")
    print(f"时间戳：{data.timestamp}")
```

## 流式读取

通过顶层 `hand.stream()` 统一接收所有传感器事件：

```python
from linkerbot.hand.o6 import SensorSource, AccelerationEvent

hand.start_polling({SensorSource.ACCELERATION: 0.1})

for event in hand.stream():
    match event:
        case AccelerationEvent(data=data):
            print(f"加速度：{data.accelerations.to_list()}")

hand.stop_polling()
hand.stop_stream()
```

## deg/s² 单位转换

`O6Acceleration` 支持与物理单位 deg/s²（度每秒平方）之间的转换。

### 转换为 deg/s²

```python
from linkerbot.hand.o6 import O6Acceleration

accel = O6Acceleration(50.0, 50.0, 50.0, 50.0, 50.0, 50.0)
deg_s2_values = accel.to_deg_per_sec2()
print(deg_s2_values)  # [1104.9, 1104.9, 1104.9, 1104.9, 1104.9, 1104.9]
```

### 从 deg/s² 创建

```python
from linkerbot.hand.o6 import O6Acceleration

# 设置所有关节电机加速度为 1000 deg/s²
accel = O6Acceleration.from_deg_per_sec2([1000.0] * 6)

# 设置不同的加速度
accel = O6Acceleration.from_deg_per_sec2(
    [
        1500.0,  # 拇指屈曲
        1200.0,  # 拇指侧摆
        1800.0,  # 食指
        1800.0,  # 中指
        1800.0,  # 无名指
        1800.0,  # 小指
    ]
)
```

## 完整示例

```python
from linkerbot import O6
from linkerbot.hand.o6 import O6Acceleration

with O6(side="left", interface_name="can0") as hand:
    # 设置较低加速度（平滑运动）
    hand.acceleration.set_accelerations([30.0] * 6)

    # 使用 deg/s² 单位设置
    accel = O6Acceleration.from_deg_per_sec2([1000.0] * 6)
    hand.acceleration.set_accelerations(accel)

    # 读取当前加速度
    data = hand.acceleration.get_blocking(timeout_ms=500)
    print(f"当前加速度：{data.accelerations.to_list()}")
    print(f"对应 deg/s²: {data.accelerations.to_deg_per_sec2()}")
```
