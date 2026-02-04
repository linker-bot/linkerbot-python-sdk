# 故障管理

O6 灵巧手的故障检测功能。

## 概述

通过 `hand.fault` 访问故障管理功能：

- 读取故障状态（阻塞式、流式、缓存）

## 故障码表

| 故障码 | 值 | 说明 |
|--------|----|----|
| `NONE` | 0 | 无故障 |
| `VOLTAGE_ABNORMAL` | 1 | 过压/欠压 |
| `ENCODER_ABNORMAL` | 2 | 磁编码器异常 |
| `OVERTEMPERATURE` | 4 | 温度过热 |
| `OVERCURRENT` | 8 | 电流过流 |
| `OVERLOAD` | 32 | 负载过载 |

## 读取故障

### 阻塞式读取

```python
data = hand.fault.get_faults_blocking(timeout_ms=500)
```

**参数**：
- `timeout_ms`：超时时间（毫秒），默认 100

**返回值**：`FaultData` 对象，包含：
- `faults`：`O6Fault` 故障数据
- `timestamp`：时间戳

**异常**：
- `TimeoutError`：超时未收到响应

### 流式读取

```python
q = hand.fault.stream(interval_ms=100, maxsize=100)
for data in q:
    # 处理 data
    pass
hand.fault.stop_streaming()
```

**参数**：
- `interval_ms`：轮询间隔（毫秒），默认 100
- `maxsize`：队列大小，默认 100

### 缓存读取

```python
data = hand.fault.get_current_faults()
```

返回最近缓存的故障数据，无数据时返回 `None`。

## 故障数据

### O6Fault 属性

| 属性 | 说明 |
|------|------|
| `thumb_flex` | 拇指弯曲 |
| `thumb_abd` | 拇指外展 |
| `index` | 食指 |
| `middle` | 中指 |
| `ring` | 无名指 |
| `pinky` | 小指 |

### O6Fault 方法

```python
# 检查是否有任何故障
faults.has_any_fault()  # -> bool

# 转为列表
faults.to_list()  # -> list[FaultCode]

# 索引访问
faults[0]  # thumb_flex
```

### FaultCode 方法

```python
# 检查单个关节电机是否有故障
faults.thumb_flex.has_fault()  # -> bool

# 获取故障名称
faults.thumb_flex.get_fault_names()  # -> list[str]
```

## 示例

### 检查故障状态

```python
from linkerbot import O6

hand = O6(side="left", interface_name="can0")

# 读取故障状态
data = hand.fault.get_faults_blocking(timeout_ms=500)

if data.faults.has_any_fault():
    print("检测到故障：")
    if data.faults.thumb_flex.has_fault():
        print(f"  拇指弯曲：{data.faults.thumb_flex.get_fault_names()}")
    if data.faults.index.has_fault():
        print(f"  食指：{data.faults.index.get_fault_names()}")
else:
    print("无故障")
```

### 持续监控

```python
from linkerbot import O6

hand = O6(side="left", interface_name="can0")

q = hand.fault.stream(interval_ms=200, maxsize=100)
try:
    for data in q:
        if data.faults.has_any_fault():
            for code in data.faults.to_list():
                if code.has_fault():
                    print(code.get_fault_names())
except KeyboardInterrupt:
    pass
finally:
    hand.fault.stop_streaming()
```
