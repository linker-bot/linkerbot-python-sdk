# 速度控制

通过 `hand.speed` 设置和读取 O20 的 16 个电机速度目标。速度值走**整数**通道,范围 **0 ~ 100**(无单位,值越大越快)。

- **数量**:16 个电机,按 motor ID 1~16 顺序
- **范围**:0 ~ 100(`O20_SPEED_MIN` / `O20_SPEED_MAX`)
- **控制模式**:位置模式下每次连接后设置一次即可保持

## 设置速度

### 所有电机统一速度

```python
from linkerbot.hand.o20 import O20

with O20(side="right") as hand:
    hand.speed.set_all(40)   # 所有 16 个电机速度 = 40
```

### 每个电机独立速度

```python
from linkerbot.hand.o20 import O20

with O20(side="right") as hand:
    # 16 个电机各自不同的速度目标
    speeds = [40, 40, 40, 40,   # 拇指 4
              40, 60, 60,        # 食指 3
              40, 60, 60,        # 中指 3
              40, 60, 60,        # 无名指 3
              40, 60, 60]        # 小指 3
    hand.speed.set_speeds(speeds)
```

## 阻塞读取速度

```python
from linkerbot.hand.o20 import O20
from linkerbot.exceptions import TimeoutError

with O20(side="right") as hand:
    try:
        data = hand.speed.get_blocking(timeout_ms=1000)
        print("速度值:  ", data.speeds)         # tuple[int, ...],16 个值
        print("时间戳:  ", data.timestamp)
    except TimeoutError:
        print("速度读取超时")
```

## 缓存读取

```python
from linkerbot.hand.o20 import O20

with O20(side="right") as hand:
    hand.speed.get_blocking(timeout_ms=1000)
    data = hand.speed.get_snapshot()
    if data is not None:
        print(data.speeds)
```

## 完整示例

```python
from linkerbot.hand.o20 import O20

with O20(side="right") as hand:
    hand.speed.set_all(40)                        # 设定初始速度
    hand.torque.set_all(400)
    hand.angle.set_angles([30.0] * 16)            # 触发一次运动
    data = hand.speed.get_blocking(timeout_ms=1000)
    print("实测速度:", data.speeds)
```

## 参数校验

`set_speeds` 与 `set_all` 都会校验参数:

| 校验项 | 触发条件 | 抛出 |
| ---- | ---- | ---- |
| 长度 | `set_speeds` 传入元素数 ≠ 16 | `ValidationError` |
| 类型 | 任一值不是 int | `ValidationError` |
| 范围 | 值 < 0 或 > 100 | `ValidationError` |
