# 电流读取

```python
from linkerbot import L6
```

读取 L6 灵巧手六个关节电机的实时电流数据（单位：mA）。

## 概述

通过 `hand.current` 访问电流读取功能，支持三种模式：

| 模式 | 方法 | 用途 |
|------|------|------|
| 阻塞读取 | `get_currents_blocking()` | 单次查询 |
| 流式读取 | `stream()` | 持续监测 |
| 缓存读取 | `get_current_currents()` | 读取最近缓存 |

## 读取电流

### 阻塞读取

发送请求并等待响应：

```python
data = hand.current.get_currents_blocking(timeout_ms=500)

# 访问各手指电流 (单位：mA)
print(data.currents.thumb_flex)  # 拇指弯曲
print(data.currents.thumb_abd)   # 拇指外展
print(data.currents.index)       # 食指
print(data.currents.middle)      # 中指
print(data.currents.ring)        # 无名指
print(data.currents.pinky)       # 小指

# 索引访问
print(data.currents[0])  # thumb_flex
```

**参数**:
- `timeout_ms`: 超时时间 (毫秒)，默认 100

**异常**:
- `TimeoutError`: 超时未收到响应

### 缓存读取

获取最近一次缓存的数据，不发送请求：

```python
data = hand.current.get_current_currents()
if data:
    print(f"电流：{data.currents.to_list()}")
```

## 流式读取

持续监测电流数据：

```python
q = hand.current.stream(interval_ms=50, maxsize=100)

try:
    for data in q:
        print(f"电流：{data.currents.to_list()}")
finally:
    hand.current.stop_streaming()
```

**参数**:
- `interval_ms`: 轮询间隔（毫秒），默认 100
- `maxsize`: 队列大小，默认 100

## 示例

### 检测过载电流

```python
q = hand.current.stream(interval_ms=50)

try:
    for data in q:
        for i, current in enumerate(data.currents.to_list()):
            if current > 1000:
                print(f"警告：关节 {i} 电流过高 ({current} mA)")
finally:
    hand.current.stop_streaming()
```

### 记录电流数据

```python
import time

records = []
start = time.time()
q = hand.current.stream(interval_ms=100)

try:
    for data in q:
        records.append({
            "time": data.timestamp - start,
            "currents": data.currents.to_list()
        })
        if time.time() - start > 5:  # 记录 5 秒
            break
finally:
    hand.current.stop_streaming()

print(f"采集 {len(records)} 条数据")
```
