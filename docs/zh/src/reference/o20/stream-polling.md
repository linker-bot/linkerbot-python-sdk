# 快照 / 主机轮询 / 事件流

O20 SDK 提供三种非阻塞获取传感器数据的方式,可以按场景组合使用:

| 方式 | 说明 | 什么时候用 |
| ---- | ---- | ---- |
| `hand.get_snapshot()` | 一次性拿所有 manager 最近缓存 | 单帧诊断、日志埋点 |
| `hand.start_polling(intervals)` | 后台线程按周期主动读 | 想要持续更新缓存或事件流,但不想手动循环调 `get_blocking` |
| `hand.stream(maxsize=100)` | 统一事件流,`for event in stream:` 消费 | 事件驱动 UI、算法侧订阅传感器更新 |

> 与 L30 不同,**O20 不支持设备端周期上报**(没有 `hand.report` manager)。想周期采样只有 `start_polling` 这条路——即主机侧轮询,由 SDK 后台线程按你设定的间隔发 `get_blocking`。

## 快照

```python
from linkerbot.hand.o20 import O20

with O20(side="right") as hand:
    hand.angle.get_blocking(timeout_ms=1000)
    hand.current.get_blocking(timeout_ms=1000)

    snapshot = hand.get_snapshot()
    if snapshot.angle is not None:
        print("angle:  ", snapshot.angle.angles.to_list())
    if snapshot.current is not None:
        print("current:", snapshot.current.currents)
    if snapshot.temperature is not None:
        print("temp:   ", snapshot.temperature.temperatures)
    print("snapshot ts:", snapshot.timestamp)
```

`O20Snapshot` 包含 `angle / speed / torque / current / temperature / fault / force_sensor` 七个 manager 的最近数据,任一没有采样过就是 `None`。

## 主机轮询

```python
from linkerbot.hand.o20 import O20, SensorSource

with O20(side="right") as hand:
    hand.start_polling({
        SensorSource.ANGLE:       1 / 30,   # 30 Hz
        SensorSource.CURRENT:     1 / 10,   # 10 Hz
        SensorSource.TEMPERATURE: 1.0,      # 1 Hz
    })

    # 后台线程持续采样,主线程做别的事……
    import time
    time.sleep(5)

    snap = hand.get_snapshot()
    print("最近 angle:", snap.angle.angles.to_list())

    hand.stop_polling()
```

支持的 `SensorSource`:`ANGLE / SPEED / CURRENT / TEMPERATURE / FAULT / FORCE_SENSOR`。

## 事件流

`hand.stream(maxsize=100)` 返回一个可迭代队列。每次任何 manager 更新缓存(阻塞读、主机轮询)时,就往队列里推一个对应的 `AngleEvent / CurrentEvent / TemperatureEvent / ...`:

```python
from linkerbot.hand.o20 import O20, SensorSource
from linkerbot.hand.o20.events import AngleEvent, CurrentEvent

with O20(side="right") as hand:
    hand.start_polling({
        SensorSource.ANGLE: 1 / 30,
        SensorSource.CURRENT: 1 / 10,
    })

    stream = hand.stream(maxsize=200)
    counts: dict[str, int] = {}
    import time
    stop_at = time.monotonic() + 2.0
    for event in stream:
        key = type(event).__name__     # AngleEvent / CurrentEvent / ...
        counts[key] = counts.get(key, 0) + 1
        if isinstance(event, AngleEvent):
            latest_angle = event.data.angles.to_list()[:4]
        if isinstance(event, CurrentEvent):
            latest_current = event.data.currents[:4]
        if time.monotonic() >= stop_at:
            break
    print("2s 内事件计数:", counts)

    hand.stop_polling()
    hand.stop_stream()
```

### 事件类型

| 事件类 | `.data` 类型 | 由谁产生 |
| ---- | ---- | ---- |
| `AngleEvent` | `O20AngleData` | `hand.angle.get_blocking` / 轮询 |
| `SpeedEvent` | `O20SpeedData` | `hand.speed.get_blocking` / 轮询 |
| `TorqueEvent` | `O20TorqueData` | `hand.torque.set_all` / `set_torques`(下发即事件) |
| `CurrentEvent` | `O20CurrentData` | `hand.current.get_blocking` / 轮询 |
| `TemperatureEvent` | `O20TemperatureData` | `hand.temperature.get_blocking` / 轮询 |
| `FaultEvent` | `O20FaultData` | `hand.fault.get_blocking` / 轮询 |
| `ForceSensorEvent` | `O20AllFingersData` | `hand.force_sensor.get_blocking` / 轮询 |

### 队列语义

`stream()` 返回的 `IterableQueue`:
- **`maxsize`**:队列上限,超出时会丢**最旧**的一个再入队(不丢新数据)
- **`for event in stream:`**:阻塞迭代直到队列关闭
- **`stream.close()`** / **`hand.stop_stream()`**:关闭队列,迭代跳出

### 事件没有 `.source` 字段

O20 事件类只有 `.data`,**没有** `.source`。想按源分桶用 `type(event).__name__` 或 `isinstance(event, XxxEvent)`。

## 组合示例:控制循环 + 后台采样 + 事件驱动

```python
from linkerbot.hand.o20 import O20, SensorSource
from linkerbot.hand.o20.events import AngleEvent
import threading, time

with O20(side="right") as hand:
    hand.speed.set_all(40)
    hand.torque.set_all(400)

    # 后台 30 Hz 拉角度,事件流消费
    hand.start_polling({SensorSource.ANGLE: 1 / 30})
    stream = hand.stream(maxsize=200)

    latest_percentages: list[float] = []
    def consume() -> None:
        for event in stream:
            if isinstance(event, AngleEvent):
                nonlocal_holder[0] = event.data.angles.to_list()
    nonlocal_holder = [None]
    consumer = threading.Thread(target=consume, daemon=True)
    consumer.start()

    # 主线程慢慢改目标
    for percent in (0, 15, 30, 15, 0):
        hand.angle.set_angles([float(percent)] * 16)
        time.sleep(1.0)
        if nonlocal_holder[0] is not None:
            print("最近实测角度[:4]:",
                  [round(v, 1) for v in nonlocal_holder[0][:4]])

    hand.stop_polling()
    hand.stop_stream()
    consumer.join(timeout=1.0)
```
