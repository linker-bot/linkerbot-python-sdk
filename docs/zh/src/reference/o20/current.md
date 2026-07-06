# 电流读取

通过 `hand.current` 读取 O20 的 16 个电机实测电流值,单位 **mA**。只读。

- **数量**:16 个电机
- **单位**:毫安(mA)
- **数据类型**:`int16`,可能为负(表示反向电流)

## 阻塞读取

```python
from linkerbot.hand.o20 import O20
from linkerbot.exceptions import TimeoutError

with O20(side="right") as hand:
    try:
        data = hand.current.get_blocking(timeout_ms=1000)
        print("电流(mA):", data.currents)      # tuple[int, ...],16 个值
        print("时间戳:  ", data.timestamp)
    except TimeoutError:
        print("电流读取超时")
```

## 缓存读取

```python
from linkerbot.hand.o20 import O20

with O20(side="right") as hand:
    hand.current.get_blocking(timeout_ms=1000)
    data = hand.current.get_snapshot()
    if data is not None:
        print(data.currents)
```

## 与力矩上限的关系

`hand.torque.set_all` / `set_torques` 下发的是**目标力矩上限**(0-1000,单位 6.5 mA/lsb)。实际电机运行时的电流用本模块的 `hand.current.get_blocking` 读回。两者可以对比看电机负载:

```python
with O20(side="right") as hand:
    hand.torque.set_all(400)                          # 上限 = 400 * 6.5 ≈ 2600 mA
    hand.angle.set_angles([30.0] * 16)                # 触发运动
    print("实测电流:", hand.current.get_blocking(timeout_ms=1000).currents)
```
