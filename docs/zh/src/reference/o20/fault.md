# 故障读取与清除

通过 `hand.fault` 读取和清除 O20 的 16 个电机故障状态。

- **数量**:16 个电机
- **单位**:每电机 1 字节,值为下表定义的故障码
- **协议**:寄存器 `SYS_ERROR_STATUS`(0x02),读回 uint8[16];写回可清故障

## 故障码

| 值 | 名称 | 说明 |
| ---: | ---- | ---- |
| `0` | `O20_FAULT_NONE` | 无故障 |
| `1` | `O20_FAULT_OVER_TEMPERATURE` | 过温 |
| `2` | `O20_FAULT_OVER_CURRENT` | 过流(可能触发正向自锁) |
| `3` | `O20_FAULT_COMMUNICATION` | 通讯异常 |
| `4` | `O20_FAULT_NOT_CALIBRATED` | 电机未校准 |

## 阻塞读取

```python
from linkerbot.hand.o20 import O20
from linkerbot.exceptions import TimeoutError

with O20(side="right") as hand:
    try:
        data = hand.fault.get_blocking(timeout_ms=1000)
        print("故障字节:", [f"0x{b:02X}" for b in data.faults])
        print("时间戳:  ", data.timestamp)
    except TimeoutError:
        print("故障读取超时")
```

## 判断某电机是否有故障 / 拿人类可读描述

`O20FaultData` 提供辅助方法:

```python
from linkerbot.hand.o20 import O20

with O20(side="right") as hand:
    data = hand.fault.get_blocking(timeout_ms=1000)
    for motor_index in range(16):
        if data.has_fault(motor_index):
            print(f"motor {motor_index + 1}: {data.fault_message(motor_index)}")
```

## 清除故障

`fault.clear()` 会给设备发一个清故障请求,把所有 16 个电机的故障状态清零:

```python
from linkerbot.hand.o20 import O20

with O20(side="right") as hand:
    data = hand.fault.get_blocking(timeout_ms=1000)
    if any(data.has_fault(i) for i in range(16)):
        print("检测到故障,清除中...")
        hand.fault.clear()
        # 重新读一次确认
        after = hand.fault.get_blocking(timeout_ms=1000)
        print("清除后:", [f"0x{b:02X}" for b in after.faults])
```

### 关于过流自锁

O20 内部结构在正向堵转过流后会自锁——继续正向下发不会再有动作,需要:

1. 手动调 `fault.clear()` 清除自锁状态,再下发正向指令;**或**
2. 直接下发反向指令,固件会自动清除自锁状态

## 缓存读取

```python
from linkerbot.hand.o20 import O20

with O20(side="right") as hand:
    hand.fault.get_blocking(timeout_ms=1000)
    data = hand.fault.get_snapshot()
    if data is not None:
        print(data.faults)
```
