# 角度控制

通过 `hand.angle` 控制和读取 L30 的 17 个关节角度。

- **数量**：17 个关节，顺序为 `J1` 到 `J17`
- **单位**：协议 raw 值
- **范围**：每个关节范围不同，可通过 `L30_JOINT_SPECS` 查看

## 设置角度

```python
from linkerbot import L30

safe_angles = [0] * 17

with L30() as hand:
    hand.control.enable(timeout_ms=1000)
    hand.angle.set_angles(safe_angles)
```

## 使用 L30Angle 对象

```python
from linkerbot import L30
from linkerbot.hand.l30 import L30Angle

angles = L30Angle.from_list([0] * 17)

with L30() as hand:
    hand.control.enable(timeout_ms=1000)
    hand.angle.set_angles(angles)
```

## 查看关节范围

```python
from linkerbot.hand.l30 import L30_JOINT_SPECS

for index, spec in enumerate(L30_JOINT_SPECS):
    print(index, spec.name, spec.minimum, spec.maximum)
```

## 百分比转换

百分比 `0` 表示该关节最小值，`100` 表示最大值。

```python
from linkerbot.hand.l30 import percentages_to_raw, raw_to_percentages

angle = percentages_to_raw([0] * 17)
print(angle.to_list())

percentages = raw_to_percentages(angle)
print(percentages)
```

结合设备控制：

```python
from linkerbot import L30
from linkerbot.hand.l30 import percentages_to_raw

with L30() as hand:
    hand.control.enable(timeout_ms=1000)
    hand.angle.set_angles(percentages_to_raw([10] * 17))
```

## 阻塞读取角度

```python
from linkerbot import L30
from linkerbot.exceptions import TimeoutError

with L30() as hand:
    try:
        data = hand.angle.get_blocking(timeout_ms=1000)
        print(data.angles.to_list())
        print(data.timestamp)
    except TimeoutError:
        print("角度读取超时")
```

## 缓存读取

```python
from linkerbot import L30

with L30() as hand:
    hand.angle.get_blocking(timeout_ms=1000)
    data = hand.angle.get_snapshot()
    if data is not None:
        print(data.angles.to_list())
```

## 完整示例

```python
from linkerbot import L30

with L30() as hand:
    hand.control.enable(timeout_ms=1000)
    hand.angle.set_angles([0] * 17)
    data = hand.angle.get_blocking(timeout_ms=1000)
    print("当前角度：", data.angles.to_list())
```
