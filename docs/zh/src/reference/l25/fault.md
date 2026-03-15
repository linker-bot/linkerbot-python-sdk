# 故障管理

L25 灵巧手的故障检测与清除功能。

## 概述

通过 `hand.fault` 访问故障管理功能：

- 读取故障状态（阻塞式、缓存）
- 清除所有关节故障

## 故障码表

L25 使用位标志（Flag）表示故障状态，每个关节电机可同时存在多个故障。

| 故障码                | 值  | 说明         |
| --------------------- | --- | ------------ |
| `NONE`                | 0   | 无故障       |
| `MOTOR_ROTOR_LOCK`    | 1   | 电机转子锁死 |
| `MOTOR_OVER_CURRENT`  | 2   | 电机过流     |
| `MOTOR_STALL_FAULT`   | 4   | 电机堵转故障 |
| `VOLTAGE_ABNORMAL`    | 8   | 电压异常     |
| `SELF_CHECK_ABNORMAL` | 16  | 自检异常     |
| `OVER_TEMPERATURE`    | 32  | 过温         |
| `SOFT_ROTOR_LOCK`     | 64  | 软件转子锁死 |
| `MOTOR_COMM_ABNORMAL` | 128 | 电机通讯异常 |

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

- `faults`：`L25Fault` 故障数据
- `timestamp`：时间戳

**异常**：

- `TimeoutError`：超时未收到响应

### 缓存读取

```python
data = hand.fault.get_snapshot()
if data:
    print(f"是否有故障：{data.faults.has_any_fault()}")
```

返回最近缓存的故障数据，无数据时返回 `None`。

## 清除故障

```python
hand.fault.clear_faults()
```

向所有关节发送故障清除命令（fire-and-forget），不等待响应。

## 流式读取

通过顶层 `hand.stream()` 统一接收所有传感器事件：

```python
from linkerbot.hand.l25 import SensorSource, FaultEvent

hand.start_polling({SensorSource.FAULT: 0.2})

try:
    for event in hand.stream():
        match event:
            case FaultEvent(data=data):
                if data.faults.has_any_fault():
                    for code in data.faults.to_list():
                        if code.has_fault():
                            print(code.get_fault_names())
finally:
    hand.stop_polling()
    hand.stop_stream()
```

## 数据类说明

### L25Fault 属性

| 属性           | 说明       |
| -------------- | ---------- |
| `thumb_abd`    | 拇指侧摆   |
| `thumb_yaw`    | 拇指旋转   |
| `thumb_root1`  | 拇指根部   |
| `thumb_tip`    | 拇指指尖   |
| `index_abd`    | 食指侧摆   |
| `index_root1`  | 食指根部   |
| `index_tip`    | 食指指尖   |
| `middle_abd`   | 中指侧摆   |
| `middle_root1` | 中指根部   |
| `middle_tip`   | 中指指尖   |
| `ring_abd`     | 无名指侧摆 |
| `ring_root1`   | 无名指根部 |
| `ring_tip`     | 无名指指尖 |
| `pinky_abd`    | 小指侧摆   |
| `pinky_root1`  | 小指根部   |
| `pinky_tip`    | 小指指尖   |

### L25Fault 方法

```python
# 检查是否有任何故障
faults.has_any_fault()  # -> bool

# 转为列表
faults.to_list()  # -> list[L25FaultCode]

# 索引访问
faults[0]  # thumb_abd
```

### L25FaultCode 方法

```python
# 检查单个关节电机是否有故障
faults.thumb_abd.has_fault()  # -> bool

# 获取故障名称列表
faults.thumb_abd.get_fault_names()  # -> list[str]
```

## 示例

### 检查故障状态

```python
from linkerbot import L25

with L25(side="left", interface_name="can0") as hand:
    # 读取故障状态
    data = hand.fault.get_blocking(timeout_ms=500)

    if data.faults.has_any_fault():
        print("检测到故障：")
        if data.faults.thumb_abd.has_fault():
            print(f"  拇指侧摆：{data.faults.thumb_abd.get_fault_names()}")
        if data.faults.index_abd.has_fault():
            print(f"  食指侧摆：{data.faults.index_abd.get_fault_names()}")
    else:
        print("无故障")

    # 清除所有故障
    hand.fault.clear_faults()
```

### 持续监控

```python
from linkerbot import L25
from linkerbot.hand.l25 import SensorSource, FaultEvent

with L25(side="left", interface_name="can0") as hand:
    hand.start_polling({SensorSource.FAULT: 0.2})

    try:
        for event in hand.stream():
            match event:
                case FaultEvent(data=data):
                    if data.faults.has_any_fault():
                        for i, code in enumerate(data.faults.to_list()):
                            if code.has_fault():
                                print(f"关节 {i} 故障：{code.get_fault_names()}")
    except KeyboardInterrupt:
        pass
    finally:
        hand.stop_polling()
        hand.stop_stream()
```
