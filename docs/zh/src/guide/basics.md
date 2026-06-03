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

## 角度表示与映射

手部 `hand.angle` 支持两种控制输入：

- `set_angles()`：使用 0-100 的标准百分比角度，保持兼容旧接口。
- `set_raw_angles()`：使用 0-255 的标准 raw 角度，跳过百分比换算。

无论使用哪种设置接口，SDK 在发送前都会查询内存中的角度映射表，把“标准 raw 值”转换为“硬件 raw 值”。默认映射是线性直通：`mapping[joint][i] = i`。

映射表形状为 `n x 256`，其中 `n` 是手型号自由度数量：

| 型号 | 自由度 | 映射表形状 |
| ---- | ------ | ---------- |
| L6 | 6 | `6 x 256` |
| O6 | 6 | `6 x 256` |
| L20Lite | 10 | `10 x 256` |
| L25 | 16 | `16 x 256` |

映射表默认保存到 `~/.config/linkerbot/hand_angle_mappings.toml`，并按手型号、左右手和 CAN 接口分别保存，例如 `l6:left:can0`。如果需要按项目或设备指定独立配置文件，可以在构造手对象时传入 `angle_mapping_path`。

```python
from linkerbot import L6

with L6(side="left", interface_name="can0") as hand:
    # 标准 raw 角度输入，范围 0-255
    hand.angle.set_raw_angles([128, 96, 160, 160, 160, 160])

    # 查询并替换完整映射表
    mapping = hand.angle.get_angle_mapping()
    mapping[0] = list(reversed(range(256)))
    hand.angle.set_angle_mapping(mapping)

    # 恢复默认线性映射
    hand.angle.reset_angle_mapping()
```

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
