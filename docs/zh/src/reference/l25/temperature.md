# 温度读取

通过 `hand.temperature` 读取 L25 灵巧手 16 个关节电机的温度数据（单位：°C）。

**温度属性**

| 属性           | 说明               |
| -------------- | ------------------ |
| `thumb_abd`    | 拇指侧摆关节电机   |
| `thumb_yaw`    | 拇指旋转关节电机   |
| `thumb_root1`  | 拇指根部关节电机   |
| `thumb_tip`    | 拇指指尖关节电机   |
| `index_abd`    | 食指侧摆关节电机   |
| `index_root1`  | 食指根部关节电机   |
| `index_tip`    | 食指指尖关节电机   |
| `middle_abd`   | 中指侧摆关节电机   |
| `middle_root1` | 中指根部关节电机   |
| `middle_tip`   | 中指指尖关节电机   |
| `ring_abd`     | 无名指侧摆关节电机 |
| `ring_root1`   | 无名指根部关节电机 |
| `ring_tip`     | 无名指指尖关节电机 |
| `pinky_abd`    | 小指侧摆关节电机   |
| `pinky_root1`  | 小指根部关节电机   |
| `pinky_tip`    | 小指指尖关节电机   |

## 读取温度

### 阻塞读取

```python
from linkerbot.exceptions import TimeoutError

try:
    data = hand.temperature.get_blocking(timeout_ms=500)
    print(f"拇指侧摆温度：{data.temperatures.thumb_abd}°C")
except TimeoutError:
    print("读取超时")
```

**参数**

- `timeout_ms`: 超时时间（毫秒），默认 100

**返回值**

- `TemperatureData`: 包含 `temperatures`（L25Temperature）和 `timestamp`

**异常**

- `TimeoutError`: 超时未响应

### 缓存读取

非阻塞读取最近一次缓存的温度数据。

```python
data = hand.temperature.get_snapshot()
if data:
    print(f"温度：{data.temperatures.to_list()}")
```

**返回值**

- `TemperatureData` 或 `None`（无缓存数据时）

## 流式读取

通过顶层 `hand.stream()` 统一接收所有传感器事件：

```python
from linkerbot.hand.l25 import SensorSource, TemperatureEvent

hand.start_polling({SensorSource.TEMPERATURE: 0.1})

try:
    for event in hand.stream():
        match event:
            case TemperatureEvent(data=data):
                print(f"温度：{data.temperatures.to_list()}")
finally:
    hand.stop_polling()
    hand.stop_stream()
```

## 示例

### 读取所有关节电机温度

```python
from linkerbot import L25

with L25(side="left", interface_name="can0") as hand:
    data = hand.temperature.get_blocking(timeout_ms=500)

    # 按属性访问
    print(f"拇指侧摆：{data.temperatures.thumb_abd}°C")
    print(f"食指侧摆：{data.temperatures.index_abd}°C")

    # 转换为列表
    temps = data.temperatures.to_list()
    print(f"全部温度：{temps}")

    # 索引访问
    print(f"第一个关节电机：{data.temperatures[0]}°C")
```

### 温度监控

```python
from linkerbot import L25
from linkerbot.hand.l25 import SensorSource, TemperatureEvent

with L25(side="left", interface_name="can0") as hand:
    hand.start_polling({SensorSource.TEMPERATURE: 0.1})

    try:
        for event in hand.stream():
            match event:
                case TemperatureEvent(data=data):
                    for i, temp in enumerate(data.temperatures.to_list()):
                        if temp > 60.0:
                            print(f"警告：关节电机 {i} 过热 ({temp}°C)")
    except KeyboardInterrupt:
        pass
    finally:
        hand.stop_polling()
        hand.stop_stream()
```
