# 基础知识

## 架构概览

SDK 采用模块化设计，通过主类访问各功能模块：

```
L6
├── hand.angle          # 角度控制
├── hand.speed          # 速度控制
├── hand.torque         # 扭矩控制
├── hand.current        # 电流读取
├── hand.temperature    # 温度读取
├── hand.force_sensor   # 力传感器
├── hand.fault          # 故障管理
└── hand.version        # 版本信息
```

## 调用方式

所有功能通过 `hand.模块.方法()` 调用：

```python
from linkerbot import L6

with L6(side="left", interface_name="can0") as hand:
    hand.angle.set_angles([50, 50, 50, 50, 50, 50])
    hand.speed.set_speeds([100, 100, 100, 100, 100, 100])

    data = hand.temperature.get_blocking()
```

## 类型安全

SDK 提供类型化的数据类，支持 IDE 自动补全：

```python
from linkerbot import L6
from linkerbot.hand.l6 import L6Angle

with L6(side="left", interface_name="can0") as hand:
    # 使用数据类（推荐，有类型提示）
    angle = L6Angle(thumb_flex=50, thumb_abd=30, index=60, middle=60, ring=60, pinky=60)
    hand.angle.set_angles(angle)

    # 或使用列表（简洁）
    hand.angle.set_angles([50, 30, 60, 60, 60, 60])
```

数据类属性：

| 属性         | 说明     |
| ------------ | -------- |
| `thumb_flex` | 拇指弯曲 |
| `thumb_abd`  | 拇指侧摆 |
| `index`      | 食指     |
| `middle`     | 中指     |
| `ring`       | 无名指   |
| `pinky`      | 小指     |

## 数据读取模式

### 阻塞读取

发送请求并等待响应：

```python
data = hand.angle.get_blocking(timeout_ms=100)
```

### 缓存读取

获取最近一次接收的数据（非阻塞）：

```python
data = hand.angle.get_snapshot()
if data is not None:
    print(data.angles)
```

### 流式读取

通过统一事件流持续接收数据：

```python
from linkerbot.hand.l6 import SensorSource, AngleEvent

hand.start_polling({SensorSource.ANGLE: 0.1})

for event in hand.stream():
    match event:
        case AngleEvent(data=data):
            print(data.angles)
    if should_stop():
        break

hand.stop_polling()
hand.stop_stream()
```

### 快照

获取所有传感器的最新缓存数据：

```python
snap = hand.get_snapshot()
print(snap.angle)  # AngleData | None
print(snap.temperature)  # TemperatureData | None
```

## 资源管理

使用 `with` 语句自动管理资源：

```python
with L6(side="left", interface_name="can0") as hand:
    # 使用灵巧手
    pass
# 自动释放资源
```

或手动管理：

```python
hand = L6(side="left", interface_name="can0")
try:
    # 使用灵巧手
    pass
finally:
    hand.close()
```

## 异常处理

```python
from linkerbot import L6
from linkerbot.exceptions import TimeoutError, ValidationError

with L6(side="left", interface_name="can0") as hand:
    try:
        data = hand.angle.get_blocking(timeout_ms=100)
    except TimeoutError:
        print("读取超时")
    except ValidationError as e:
        print(f"参数错误：{e}")
```

| 异常              | 说明                     |
| ----------------- | ------------------------ |
| `TimeoutError`    | 通信超时                 |
| `ValidationError` | 参数验证失败             |
| `StateError`      | 状态错误（如接口已关闭） |

## 关节索引

所有 6 关节模块使用相同的索引顺序：

| 索引 | 名称     | 标识         |
| ---- | -------- | ------------ |
| 0    | 拇指弯曲 | `thumb_flex` |
| 1    | 拇指侧摆 | `thumb_abd`  |
| 2    | 食指     | `index`      |
| 3    | 中指     | `middle`     |
| 4    | 无名指   | `ring`       |
| 5    | 小指     | `pinky`      |
