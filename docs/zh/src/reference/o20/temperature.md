# 温度读取

通过 `hand.temperature` 读取 O20 的 16 个电机温度，单位 **°C**。只读。

- **数量**:16 个电机
- **单位**:摄氏度 (°C)
- **数据类型**:`uint8`,一个电机 1 字节

## 阻塞读取

```python
from linkerbot.hand.o20 import O20
from linkerbot.exceptions import TimeoutError

with O20(side="right") as hand:
    try:
        data = hand.temperature.get_blocking(timeout_ms=1000)
        print("温度 (°C):", data.temperatures)  # tuple[int, ...],16 个值
        print("时间戳： ", data.timestamp)
    except TimeoutError:
        print("温度读取超时")
```

## 缓存读取

```python
from linkerbot.hand.o20 import O20

with O20(side="right") as hand:
    hand.temperature.get_blocking(timeout_ms=1000)
    data = hand.temperature.get_snapshot()
    if data is not None:
        print(data.temperatures)
```

## 温度监控示例

对每个电机温度做上限报警：

```python
from linkerbot.hand.o20 import O20

THRESHOLD = 60  # 单位 °C

with O20(side="right") as hand:
    data = hand.temperature.get_blocking(timeout_ms=1000)
    hot = [
        (motor, temp)
        for motor, temp in enumerate(data.temperatures)
        if temp >= THRESHOLD
    ]
    if hot:
        print("超温电机：")
        for motor_index, temp in hot:
            print(f"  motor {motor_index + 1}: {temp} °C")
```
