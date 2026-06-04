# 故障读取

通过 `hand.fault` 读取 L30 的 17 个关节故障字节，并判断具体故障类型。

## 阻塞读取故障字节

```python
from linkerbot import L30

with L30() as hand:
    data = hand.fault.get_blocking(timeout_ms=1000)
    print(data.faults)
```

## 判断某个关节是否有故障

```python
from linkerbot import L30

with L30() as hand:
    data = hand.fault.get_blocking(timeout_ms=1000)
    joint_index = 0
    print("有电压故障：", data.has_voltage_fault(joint_index))
    print("有负载故障：", data.has_load_fault(joint_index))
```

## 缓存读取

```python
from linkerbot import L30

with L30() as hand:
    hand.fault.get_blocking(timeout_ms=1000)
    data = hand.fault.get_snapshot()
    if data is not None:
        print(data.faults)
```

## 完整示例

```python
from linkerbot import L30

with L30() as hand:
    fault = hand.fault.get_blocking(timeout_ms=1000)
    for index, value in enumerate(fault.faults):
        if value:
            print("关节", index, "故障字节", value)
```
