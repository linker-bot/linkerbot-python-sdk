# 电流读取

```python
from linkerbot import L6
```

读取 L6 灵巧手六个关节电机的实时电流数据（单位：mA）。

## 概述

通过 `hand.current` 访问电流读取功能，支持三种模式：

| 模式     | 方法             | 用途         |
| -------- | ---------------- | ------------ |
| 阻塞读取 | `get_blocking()` | 单次查询     |
| 流式读取 | `hand.stream()`  | 持续监测     |
| 缓存读取 | `get_snapshot()` | 读取最近缓存 |

## 读取电流

### 阻塞读取

发送请求并等待响应：

```python
data = hand.current.get_blocking(timeout_ms=500)

# 访问各手指电流 (单位：mA)
print(data.currents.thumb_flex)  # 拇指弯曲
print(data.currents.thumb_abd)  # 拇指侧摆
print(data.currents.index)  # 食指
print(data.currents.middle)  # 中指
print(data.currents.ring)  # 无名指
print(data.currents.pinky)  # 小指

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
data = hand.current.get_snapshot()
if data:
    print(f"电流：{data.currents.to_list()}")
```

## 流式读取

通过顶层 `hand.stream()` 统一接收所有传感器事件：

```python
from linkerbot.hand.l6 import SensorSource, CurrentEvent

hand.start_polling({SensorSource.CURRENT: 0.05})

for event in hand.stream():
    match event:
        case CurrentEvent(data=data):
            print(f"电流：{data.currents.to_list()}")

hand.stop_polling()
hand.stop_stream()
```

## 示例

### 检测过载电流

```python
from linkerbot import L6
from linkerbot.hand.l6 import SensorSource, CurrentEvent

with L6(side="left", interface_name="can0") as hand:
    hand.start_polling({SensorSource.CURRENT: 0.05})

    try:
        for event in hand.stream():
            match event:
                case CurrentEvent(data=data):
                    for i, current in enumerate(data.currents.to_list()):
                        if current > 1000:
                            print(f"警告：关节 {i} 电流过高 ({current} mA)")
    finally:
        hand.stop_polling()
        hand.stop_stream()
```

### 记录电流数据

```python
import time
from linkerbot import L6
from linkerbot.hand.l6 import SensorSource, CurrentEvent

with L6(side="left", interface_name="can0") as hand:
    records = []
    start = time.time()
    hand.start_polling({SensorSource.CURRENT: 0.1})

    try:
        for event in hand.stream():
            match event:
                case CurrentEvent(data=data):
                    records.append(
                        {
                            "time": data.timestamp - start,
                            "currents": data.currents.to_list(),
                        }
                    )
            if time.time() - start > 5:  # 记录 5 秒
                break
    finally:
        hand.stop_polling()
        hand.stop_stream()

    print(f"采集 {len(records)} 条数据")
```
