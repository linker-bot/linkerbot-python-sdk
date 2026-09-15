# 触觉传感器

通过 `hand.force_sensor` 读取 L30 五指触觉传感器。每个手指返回一个 `12 x 6` 的 `numpy.uint8` 矩阵。

触觉矩阵是只读的。如果要修改，请先调用 `.copy()`。

## 读取单个手指

```python
from linkerbot import L30
from linkerbot.hand.l30 import Finger

with L30() as hand:
    data = hand.force_sensor.get_finger(Finger.INDEX, timeout_ms=1000)
    print("手指：", data.finger)
    print("矩阵形状：", data.values.shape)
    print("第一行：", data.values[0])
```

## 读取全部五个手指

```python
from linkerbot import L30

with L30() as hand:
    data = hand.force_sensor.get_blocking(timeout_ms=1000)
    print("拇指：", data.thumb.shape)
    print("食指：", data.index.shape)
    print("中指：", data.middle.shape)
    print("无名指：", data.ring.shape)
    print("小指：", data.pinky.shape)
```

## 缓存读取

```python
from linkerbot import L30

with L30() as hand:
    hand.force_sensor.get_blocking(timeout_ms=1000)
    data = hand.force_sensor.get_snapshot()
    if data is not None:
        print(data.thumb)
```

## 完整示例

```python
from linkerbot import L30
from linkerbot.hand.l30 import Finger

with L30() as hand:
    index = hand.force_sensor.get_finger(Finger.INDEX, timeout_ms=1000)
    print("食指触觉矩阵：", index.values)
```
