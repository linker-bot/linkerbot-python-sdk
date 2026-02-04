# 力传感器

O6 灵巧手配备 5 个手指的力传感器（thumb, index, middle, ring, pinky），支持阻塞读取和流式读取两种模式。

## 概述

通过 `hand.force_sensor` 访问力传感器功能：

```python
from linkerbot import O6

hand = O6(side="left", interface_name="can0")
data = hand.force_sensor.get_data_blocking()
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
data = hand.force_sensor.get_data_blocking(timeout_ms=1000)
print(data.thumb.values)   # 拇指数据
print(data.index.values)   # 食指数据
```

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `timeout_ms` | `float` | 1000 | 超时时间（毫秒） |

**异常**: `TimeoutError`（超时）、`ValidationError`（参数无效）

### 缓存读取

获取最近一次接收的数据（非阻塞）：

```python
latest = hand.force_sensor.get_latest_data()
for finger, data in latest.items():
    if data:
        print(f"{finger}: {data.values[0]}")
```

## 流式读取

持续接收传感器数据。

```python
queue = hand.force_sensor.stream(interval_ms=100, maxsize=100)
try:
    for data in queue:
        print(data.thumb.values)
        if done:
            break
finally:
    hand.force_sensor.stop_streaming()
```

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `interval_ms` | `float` | 100 | 采样间隔（毫秒） |
| `maxsize` | `int` | 100 | 队列最大容量 |

**异常**: `StateError`（重复启动）、`ValidationError`（参数无效）

## 示例

### 读取并判断数据新鲜度

```python
import time
from linkerbot import O6

hand = O6(side="left", interface_name="can0")
latest = hand.force_sensor.get_latest_data()

if latest["thumb"]:
    age = time.time() - latest["thumb"].timestamp
    print(f"数据年龄：{age:.3f}s")
```

### 流式采集指定时长

```python
import time
from linkerbot import O6

hand = O6(side="left", interface_name="can0")
queue = hand.force_sensor.stream(interval_ms=50)
start = time.time()

try:
    for data in queue:
        print(f"拇指：{data.thumb.values[0]}")
        if time.time() - start > 5:  # 采集 5 秒
            break
finally:
    hand.force_sensor.stop_streaming()
```
