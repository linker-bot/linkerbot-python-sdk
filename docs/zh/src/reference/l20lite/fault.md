# 故障管理

L20Lite 灵巧手的故障检测功能。

## 概述

通过 `hand.fault` 访问故障管理功能：

- 读取故障状态（阻塞式、缓存）

## 故障码表

| 故障码             | 值 | 说明         |
| ------------------ | -- | ------------ |
| `NONE`             | 0  | 无故障       |
| `VOLTAGE_ABNORMAL` | 1  | 过压/欠压    |
| `ENCODER_ABNORMAL` | 2  | 磁编码器异常 |
| `OVERTEMPERATURE`  | 4  | 温度过热     |
| `OVERCURRENT`      | 8  | 电流过流     |
| `OVERLOAD`         | 32 | 负载过载     |

## 读取故障

### 阻塞式读取

```python
from linkerbot.exceptions import TimeoutError

try:
    data = hand.fault.get_blocking(timeout_ms=500)
except TimeoutError:
    print("读取超时")
```

**参数**：

- `timeout_ms`：超时时间（毫秒），默认 100

**返回值**：`FaultData` 对象，包含：

- `faults`：`L20liteFault` 故障数据
- `timestamp`：时间戳

**异常**：

- `TimeoutError`：超时未收到响应

### 缓存读取

```python
data = hand.fault.get_snapshot()
if data:
    print(f"有故障：{data.faults.has_any_fault()}")
```

返回最近缓存的故障数据，无数据时返回 `None`。

## 故障数据

### L20liteFault 属性

| 属性          | 说明       |
| ------------- | ---------- |
| `thumb_flex`  | 拇指弯曲   |
| `thumb_abd`   | 拇指侧摆   |
| `index_flex`  | 食指弯曲   |
| `middle_flex` | 中指弯曲   |
| `ring_flex`   | 无名指弯曲 |
| `pinky_flex`  | 小指弯曲   |
| `index_abd`   | 食指侧摆   |
| `ring_abd`    | 无名指侧摆 |
| `pinky_abd`   | 小指侧摆   |
| `thumb_yaw`   | 拇指旋转   |

### L20liteFault 方法

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
from linkerbot import L20lite

with L20lite(side="left", interface_name="can0") as hand:
    # 读取故障状态
    data = hand.fault.get_blocking(timeout_ms=500)

    if data.faults.has_any_fault():
        print("检测到故障：")
        if data.faults.thumb_flex.has_fault():
            print(f"  拇指弯曲：{data.faults.thumb_flex.get_fault_names()}")
        if data.faults.index_flex.has_fault():
            print(f"  食指弯曲：{data.faults.index_flex.get_fault_names()}")
    else:
        print("无故障")
```

### 遍历所有关节故障

```python
from linkerbot import L20lite

with L20lite(side="left", interface_name="can0") as hand:
    data = hand.fault.get_blocking(timeout_ms=500)

    if data.faults.has_any_fault():
        for i, code in enumerate(data.faults.to_list()):
            if code.has_fault():
                print(f"关节 {i} 故障：{code.get_fault_names()}")
```
