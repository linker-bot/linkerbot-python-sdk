# 温度读取

通过 `hand.temperature` 读取 O6 灵巧手 6 个关节电机的温度数据（单位：°C）。

**温度属性**

| 属性         | 说明             |
| ------------ | ---------------- |
| `thumb_flex` | 拇指屈曲关节电机 |
| `thumb_abd`  | 拇指侧摆关节电机 |
| `index`      | 食指关节电机     |
| `middle`     | 中指关节电机     |
| `ring`       | 无名指关节电机   |
| `pinky`      | 小指关节电机     |

## 读取温度

### 阻塞读取

```python
data = hand.temperature.get_blocking(timeout_ms=500)
print(f"拇指温度：{data.temperatures.thumb_flex}°C")
```

**参数**

- `timeout_ms`: 超时时间（毫秒），默认 100

**返回值**

- `TemperatureData`: 包含 `temperatures` 和 `timestamp`

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
from linkerbot.hand.o6 import SensorSource, TemperatureEvent

hand.start_polling({SensorSource.TEMPERATURE: 0.1})

for event in hand.stream():
    match event:
        case TemperatureEvent(data=data):
            print(f"温度：{data.temperatures.to_list()}")

hand.stop_polling()
hand.stop_stream()
```

## 示例

### 读取所有关节电机温度

```python
from linkerbot import O6

with O6(side="left", interface_name="can0") as hand:
    data = hand.temperature.get_blocking(timeout_ms=500)

    # 按属性访问
    print(f"拇指屈曲：{data.temperatures.thumb_flex}°C")
    print(f"食指：{data.temperatures.index}°C")

    # 转换为列表
    temps = data.temperatures.to_list()
    print(f"全部温度：{temps}")

    # 索引访问
    print(f"第一个关节电机：{data.temperatures[0]}°C")
```

### 温度监控

```python
from linkerbot import O6
from linkerbot.hand.o6 import SensorSource, TemperatureEvent

with O6(side="left", interface_name="can0") as hand:
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
