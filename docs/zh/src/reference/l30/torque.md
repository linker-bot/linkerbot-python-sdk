# 力矩目标控制

通过 `hand.torque` 设置 L30 的 17 个关节力矩目标。

- **数量**：17 个关节，顺序为 `J1` 到 `J17`
- **范围**：60-800
- **注意**：`hand.torque.get_snapshot()` 返回最近一次 SDK 发送的目标力矩，不是硬件实测力矩。

## 设置每个关节力矩

```python
from linkerbot import L30

with L30() as hand:
    hand.torque.set_torques([100] * 17)
```

## 设置所有关节相同力矩

```python
from linkerbot import L30

with L30() as hand:
    hand.torque.set_all(100)
```

## 读取最近一次目标力矩缓存

```python
from linkerbot import L30

with L30() as hand:
    hand.torque.set_all(100)
    data = hand.torque.get_snapshot()
    if data is not None:
        print(data.torques)
```

## 完整示例

```python
from linkerbot import L30

with L30() as hand:
    hand.torque.set_all(100)
    target = hand.torque.get_snapshot()
    print("最近一次目标力矩：", target.torques if target else None)
```
