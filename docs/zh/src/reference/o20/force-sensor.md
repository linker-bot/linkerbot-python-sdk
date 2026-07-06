# 触觉传感器

通过 `hand.force_sensor` 读取 O20 五指触觉矩阵。每指返回一个 **12×6 uint8 矩阵**(72 个压力值),外加一个 **online 标志**。

- **手指枚举**:`Finger.THUMB / INDEX / MIDDLE / RING / PINKY`
- **每指数据源**:两个 register(前 64B + 后 9B)
- **矩阵形状**:`(12, 6)`,`np.uint8`
- **矩阵值域**:0~255,值越大压力越强

## 单指读取

`hand.force_sensor.get_finger(Finger.X)` 返回一个 `FingerForceSensor`,再调 `get_blocking()`:

```python
from linkerbot.hand.o20 import O20, Finger

with O20(side="right") as hand:
    thumb = hand.force_sensor.get_finger(Finger.THUMB).get_blocking(timeout_ms=1000)
    print("finger    :", thumb.finger.value)
    print("online    :", thumb.online)
    print("matrix    :", thumb.values.shape)     # (12, 6)
    print("timestamp :", thumb.timestamp)
```

## 五指连读

`hand.force_sensor.get_blocking()` 依次读五指,返回 `O20AllFingersData` 包含所有五指数据:

```python
from linkerbot.hand.o20 import O20

with O20(side="right") as hand:
    all_fingers = hand.force_sensor.get_blocking(timeout_ms=2000)

    for finger_name in ("thumb", "index", "middle", "ring", "pinky"):
        data = getattr(all_fingers, finger_name)
        print(f"{finger_name:<6} online={data.online}  sum={int(data.values.sum())}")
```

## 事务原子性(fix#143)

O20 每指触觉分散在**两个独立 register**上,SDK 在 `_read_finger` 内部用 `client.tactile_transaction()` 上下文管理器把两次读**原子化**,防止两个线程并发读时把不同采样轮次的 `(data1, data2)` 混在一起产生跨采样矩阵。

用户代码不用关心这个上下文——`get_finger().get_blocking()` 与 `hand.force_sensor.get_blocking()` 都内建了保护。只有你在**自己**用 `client.read()` 读原始 register 时才需要显式包装:

```python
from linkerbot.hand.o20 import O20

with O20(side="right") as hand:
    # 通常不需要这样用,直接 hand.force_sensor.get_finger(...) 即可
    with hand._client.tactile_transaction():
        data1 = hand._client.read(register=0x09, timeout_ms=1000)  # THUMB DATA1
        data2 = hand._client.read(register=0x0A, timeout_ms=1000)  # THUMB DATA2
```

## Online 语义

`FingerForceData.online` 是**厂商协议 md 声明**的传感器在线状态标志(第 0 字节)。实测部分固件版本可能不实现这一位,SDK 目前按协议 md 的语义解析并校验为 `{0, 1}`;如遇到 `ProtocolError: unexpected tactile online flag` 通常是固件版本与协议 md 不一致,需要联系维护方对齐。

## 缓存读取

只有五指连读的 `get_blocking()` 会更新 `get_snapshot()`;单指 `get_finger().get_blocking()` **不**写快照:

```python
from linkerbot.hand.o20 import O20

with O20(side="right") as hand:
    hand.force_sensor.get_blocking(timeout_ms=2000)   # 触发一次五指读
    snapshot = hand.force_sensor.get_snapshot()
    if snapshot is not None:
        print("thumb sum:", int(snapshot.thumb.values.sum()))
```

## numpy 只读约定

返回的 `values` 矩阵设为 `write=False` 只读,防止用户误改缓存。想改要 `.copy()`:

```python
matrix = thumb.values         # 只读视图
mutable = matrix.copy()       # 可写副本
mutable[0, 0] = 128           # OK
# thumb.values[0, 0] = 128    # ValueError: assignment destination is read-only
```

## 完整示例

```python
import numpy as np
from linkerbot.hand.o20 import O20, Finger

with O20(side="right") as hand:
    # 单指
    index = hand.force_sensor.get_finger(Finger.INDEX).get_blocking(timeout_ms=1000)
    print("index matrix max:", int(index.values.max()))

    # 五指连读 + 快照
    all_fingers = hand.force_sensor.get_blocking(timeout_ms=2000)
    total = sum(int(getattr(all_fingers, n).values.sum())
                for n in ("thumb", "index", "middle", "ring", "pinky"))
    print("五指压力累加:", total)
```
