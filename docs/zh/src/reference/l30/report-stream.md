# 周期上报、轮询与事件流

L30 支持三种数据获取方式：

- 阻塞读取：例如 `hand.angle.get_blocking(timeout_ms=1000)`。
- 设备端周期上报：设备主动发送数据，SDK 更新快照和事件流。
- 主机主动轮询：SDK 后台线程定期发送读取请求。

## 默认周期上报

`L30(auto_start_periodic=True)` 默认会开启角度周期上报。

```python
from linkerbot import L30

with L30() as hand:
    data = hand.angle.get_blocking(timeout_ms=1000)
    print(data.angles.to_list())
```

## 手动开启默认周期上报

```python
from linkerbot import L30

with L30(auto_start_periodic=False) as hand:
    hand.start_periodic_reports(timeout_ms=1000)
    print("已开启默认周期上报")
```

## 手动关闭周期上报

```python
from linkerbot import L30

with L30() as hand:
    hand.stop_periodic_reports(timeout_ms=1000)
    print("已关闭本实例开启过的周期上报")
```

## 配置指定上报源

```python
from linkerbot import L30
from linkerbot.hand.l30 import ReportSource

with L30(auto_start_periodic=False) as hand:
    hand.report.configure(
        ReportSource.ANGLE,
        enabled=True,
        period_ms=20,
        timeout_ms=1000,
    )
```

目前高层快照只支持完整 17 关节周期上报，因此 `joint_mask` 请保持默认值，不要传 partial mask。

## 主机主动轮询

如果不想使用设备端周期上报，可以关闭自动周期上报，然后用 `start_polling()` 让 SDK 后台线程主动读取传感器。

```python
import time

from linkerbot import L30
from linkerbot.hand.l30 import SensorSource

with L30(auto_start_periodic=False) as hand:
    hand.start_polling({SensorSource.ANGLE: 0.05})
    time.sleep(1)

    data = hand.angle.get_snapshot()
    if data is not None:
        print(data.angles.to_list())

    hand.stop_polling()
```

同时轮询多个传感器：

```python
import time

from linkerbot import L30
from linkerbot.hand.l30 import SensorSource

with L30(auto_start_periodic=False) as hand:
    hand.start_polling(
        {
            SensorSource.ANGLE: 0.05,
            SensorSource.SPEED: 0.1,
            SensorSource.CURRENT: 0.2,
            SensorSource.TEMPERATURE: 1.0,
            SensorSource.FAULT: 1.0,
        }
    )
    time.sleep(2)
    hand.stop_polling()

    snapshot = hand.get_snapshot()
    print(snapshot.angle)
    print(snapshot.speed)
    print(snapshot.current)
```

## 统一事件流

`hand.stream()` 会返回一个可迭代队列。角度、速度、电流、温度、故障、触觉等数据更新时都会进入同一个事件流。

```python
from linkerbot import L30
from linkerbot.hand.l30 import AngleEvent

with L30() as hand:
    stream = hand.stream()
    for event in stream:
        if isinstance(event, AngleEvent):
            print(event.data.angles.to_list())
            break
    hand.stop_stream()
```

主机轮询结合事件流：

```python
from linkerbot import L30
from linkerbot.hand.l30 import CurrentEvent, SensorSource, TemperatureEvent

with L30(auto_start_periodic=False) as hand:
    hand.start_polling(
        {
            SensorSource.CURRENT: 0.2,
            SensorSource.TEMPERATURE: 1.0,
        }
    )
    stream = hand.stream()

    try:
        for event in stream:
            if isinstance(event, CurrentEvent):
                print("电流事件：", event.data.currents)
            elif isinstance(event, TemperatureEvent):
                print("温度事件：", event.data.temperatures)
            break
    finally:
        hand.stop_polling()
        hand.stop_stream()
```

## 事件类型

```python
from linkerbot.hand.l30 import (
    AngleEvent,
    CurrentEvent,
    FaultEvent,
    ForceSensorEvent,
    SpeedEvent,
    TemperatureEvent,
    TorqueEvent,
)
```

| 事件类型           | 数据字段                                   |
| ------------------ | ------------------------------------------ |
| `AngleEvent`       | `event.data.angles`                        |
| `SpeedEvent`       | `event.data.speeds`                        |
| `TorqueEvent`      | `event.data.torques`                       |
| `CurrentEvent`     | `event.data.currents`                      |
| `TemperatureEvent` | `event.data.temperatures`                  |
| `FaultEvent`       | `event.data.faults`                        |
| `ForceSensorEvent` | `event.data.thumb/index/middle/ring/pinky` |
