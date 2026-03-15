# 速度控制

通过 `hand.speed` 控制和读取 O6 灵巧手各关节电机的运动速度。

- **速度范围**: 0-100
- **最大转速**: 186.66 RPM（对应值 100）

## 设置速度

```python
from linkerbot import O6
from linkerbot.hand.o6 import O6Speed

# 使用列表
hand.speed.set_speeds([50.0, 50.0, 50.0, 50.0, 50.0, 50.0])

# 使用 O6Speed 对象
speed = O6Speed(
    thumb_flex=30.0,  # 拇指弯曲
    thumb_abd=30.0,  # 拇指侧摆
    index=80.0,  # 食指
    middle=80.0,  # 中指
    ring=80.0,  # 无名指
    pinky=80.0,  # 小指
)
hand.speed.set_speeds(speed)
```

## 读取速度

### 阻塞读取

```python
from linkerbot import O6
from linkerbot.exceptions import TimeoutError

try:
    data = hand.speed.get_blocking(timeout_ms=500)
    print(f"拇指弯曲速度：{data.speeds.thumb_flex}")
    print(f"全部速度：{data.speeds.to_list()}")
except TimeoutError:
    print("读取超时")
```

### 缓存读取

```python
data = hand.speed.get_snapshot()
if data:
    print(f"速度：{data.speeds.to_list()}")
    print(f"时间戳：{data.timestamp}")
```

## 流式读取

通过顶层 `hand.stream()` 统一接收所有传感器事件：

```python
from linkerbot.hand.o6 import SensorSource, SpeedEvent

hand.start_polling({SensorSource.SPEED: 0.1})

for event in hand.stream():
    match event:
        case SpeedEvent(data=data):
            print(f"速度：{data.speeds.to_list()}")

hand.stop_polling()
hand.stop_stream()
```

## RPM 单位转换

O6Speed 支持 RPM（转/分钟）单位的转换。

### 转换为 RPM

```python
from linkerbot.hand.o6 import O6Speed

speed = O6Speed(50.0, 50.0, 50.0, 50.0, 50.0, 50.0)
rpm_values = speed.to_rpm()
print(rpm_values)  # [93.33, 93.33, 93.33, 93.33, 93.33, 93.33]
```

### 从 RPM 创建

```python
from linkerbot.hand.o6 import O6Speed

# 设置所有关节电机为 90 RPM
speed = O6Speed.from_rpm([90.0, 90.0, 90.0, 90.0, 90.0, 90.0])
hand.speed.set_speeds(speed)

# 拇指慢速，其他手指快速
speed = O6Speed.from_rpm([60.0, 60.0, 120.0, 120.0, 120.0, 120.0])
hand.speed.set_speeds(speed)
```

## 完整示例

```python
from linkerbot import O6
from linkerbot.hand.o6 import O6Speed

with O6(side="left", interface_name="can0") as hand:
    # 使用 RPM 设置速度
    speed = O6Speed.from_rpm([90.0, 90.0, 120.0, 120.0, 120.0, 120.0])
    hand.speed.set_speeds(speed)

    # 读取当前速度
    data = hand.speed.get_blocking(timeout_ms=500)
    print(f"当前速度：{data.speeds.to_list()}")
    print(f"RPM: {data.speeds.to_rpm()}")
```
