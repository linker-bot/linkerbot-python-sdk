# 角度控制

通过 `hand.angle` 控制和读取 L6 灵巧手的 6 个关节电机角度。

- **角度范围**: 0-100
- **单位**: 无量纲（映射到关节电机实际角度）

## 设置角度

```python
from linkerbot import L6
from linkerbot.hand.l6 import L6Angle

# 使用列表
hand.angle.set_angles([50.0, 30.0, 60.0, 60.0, 60.0, 60.0])

# 使用 L6Angle 对象
angles = L6Angle(
    thumb_flex=50.0,  # 拇指屈曲
    thumb_abd=30.0,  # 拇指侧摆
    index=60.0,  # 食指
    middle=60.0,  # 中指
    ring=60.0,  # 无名指
    pinky=60.0,  # 小指
)
hand.angle.set_angles(angles)
```

## 原始角度与映射

除了 0-100 的百分比角度，`hand.angle` 还支持直接设置标准 raw 角度：

```python
# 6 个关节，标准 raw 范围为 0-255
hand.angle.set_raw_angles([128, 96, 160, 160, 160, 160])
```

SDK 发送控制帧前会将“标准 raw 值”通过角度映射表转换为“硬件 raw 值”。默认映射是线性直通：`0 -> 0`，`255 -> 255`。

L6 的映射表形状为 `6 x 256`：

- 行：关节索引，顺序与 [关节说明](./README.md#关节说明) 一致。
- 列：标准 raw 输入值 `0-255`。
- 值：实际发送给硬件的 raw 值 `0-255`。

```python
# 查询当前映射表
mapping = hand.angle.get_angle_mapping()

# 修改完整映射表后保存到 TOML
mapping[0] = list(reversed(range(256)))
hand.angle.set_angle_mapping(mapping)

# 恢复默认线性映射
hand.angle.reset_angle_mapping()
```

映射表默认保存到 `~/.config/linkerbot/hand_angle_mappings.toml`。保存时会按手型号、左右手和 CAN 接口区分，例如 `l6:left:can0`。也可以在构造手对象时通过 `angle_mapping_path` 指定 TOML 路径。

## 读取角度

### 阻塞读取

```python
from linkerbot import L6
from linkerbot.exceptions import TimeoutError

try:
    data = hand.angle.get_blocking(timeout_ms=500)
    print(f"拇指屈曲：{data.angles.thumb_flex}")
    print(f"全部角度：{data.angles.to_list()}")
except TimeoutError:
    print("读取超时")
```

### 缓存读取

```python
data = hand.angle.get_snapshot()
if data:
    print(f"角度：{data.angles.to_list()}")
    print(f"时间戳：{data.timestamp}")
```

## 流式读取

通过顶层 `hand.stream()` 统一接收所有传感器事件：

```python
from linkerbot.hand.l6 import SensorSource, AngleEvent

hand.start_polling({SensorSource.ANGLE: 0.1})

for event in hand.stream():
    match event:
        case AngleEvent(data=data):
            print(f"角度：{data.angles.to_list()}")

hand.stop_polling()
hand.stop_stream()
```

## 完整示例

```python
from linkerbot import L6

with L6(side="left", interface_name="can0") as hand:
    # 设置角度
    hand.angle.set_angles([0.0, 0.0, 0.0, 0.0, 0.0, 0.0])

    # 读取当前角度
    data = hand.angle.get_blocking(timeout_ms=500)
    print(f"当前角度：{data.angles.to_list()}")

    # 渐进移动
    for i in range(0, 101, 10):
        hand.angle.set_angles([float(i)] * 6)
```
