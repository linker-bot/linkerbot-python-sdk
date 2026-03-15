# 力传感器

O6 灵巧手配备 5 个手指的力传感器（thumb, index, middle, ring, pinky），支持阻塞读取和缓存读取两种模式。

## 概述

通过 `hand.force_sensor` 访问力传感器功能：

```python
from linkerbot import O6

with O6(side="left", interface_name="can0") as hand:
    data = hand.force_sensor.get_blocking()
```

### 数据结构

**ForceSensorData** - 单个手指的传感器数据：

- `values`: 形状 (10, 4) 的 NumPy 数组（uint8）
- `timestamp`: Unix 时间戳

**AllFingersData** - 全部 5 个手指的数据：

- `thumb`, `index`, `middle`, `ring`, `pinky`: 各手指的 `ForceSensorData`

## 读取数据

### 阻塞读取

```python
data = hand.force_sensor.get_blocking(timeout_ms=1000)
print(data.thumb.values)  # 拇指数据
print(data.index.values)  # 食指数据
```

| 参数         | 类型    | 默认值 | 说明             |
| ------------ | ------- | ------ | ---------------- |
| `timeout_ms` | `float` | 1000   | 超时时间（毫秒） |

**异常**: `TimeoutError`（超时）、`ValidationError`（参数无效）

### 缓存读取

获取最近一次接收的数据（非阻塞）：

```python
data = hand.force_sensor.get_snapshot()
if data:
    print(f"拇指：{data.thumb.values[0]}")
    print(f"食指：{data.index.values[0]}")
```

**返回值**: `AllFingersData` 或 `None`（任一手指无数据时）

## 流式读取

通过顶层 `hand.stream()` 统一接收所有传感器事件：

```python
from linkerbot.hand.o6 import SensorSource, ForceSensorEvent

hand.start_polling({SensorSource.FORCE_SENSOR: 0.1})

for event in hand.stream():
    match event:
        case ForceSensorEvent(data=data):
            print(data.thumb.values)

hand.stop_polling()
hand.stop_stream()
```

## 示例

### 阻塞读取所有手指

```python
from linkerbot import O6

with O6(side="left", interface_name="can0") as hand:
    data = hand.force_sensor.get_blocking(timeout_ms=1000)
    print(f"拇指：{data.thumb.values.shape}")
    print(f"食指：{data.index.values.shape}")
```

### 流式采集指定时长

```python
import time
from linkerbot import O6
from linkerbot.hand.o6 import SensorSource, ForceSensorEvent

with O6(side="left", interface_name="can0") as hand:
    hand.start_polling({SensorSource.FORCE_SENSOR: 0.05})
    start = time.time()

    try:
        for event in hand.stream():
            match event:
                case ForceSensorEvent(data=data):
                    print(f"拇指：{data.thumb.values[0]}")
            if time.time() - start > 5:  # 采集 5 秒
                break
    finally:
        hand.stop_polling()
        hand.stop_stream()
```
