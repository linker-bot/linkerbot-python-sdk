# O6 灵巧手

## 快速开始

```python
from linkerbot import O6

with O6(side='left', interface_name='can0') as hand:
    # 设置角度
    hand.angle.set_angles((10, 20, 30, 40, 50, 60))

    # 读取角度
    data = hand.angle.get_angles_blocking(timeout_ms=500)
    print(data.angles)
```

**构造参数**

| 参数 | 类型 | 说明 |
|------|------|------|
| `side` | `"left"` \| `"right"` | 左手或右手 |
| `interface_name` | `str` | CAN 接口名，如 `"can0"` |
| `interface_type` | `str` | CAN 接口类型，默认 `"socketcan"`。Windows 用法参考 [CAN 总线](../can.md) 文档 |

## 关节说明

| 索引 | 名称 | 标识 |
|------|------|------|
| 0 | 拇指弯曲 | `thumb_flex` |
| 1 | 拇指外展 | `thumb_abd` |
| 2 | 食指 | `index` |
| 3 | 中指 | `middle` |
| 4 | 无名指 | `ring` |
| 5 | 小指 | `pinky` |

## 功能模块

| 模块 | 说明 |
|------|------|
| `hand.angle` | 关节角度控制与读取 |
| `hand.speed` | 速度控制（支持读取和 RPM 单位） |
| `hand.acceleration` | 加速度控制 |
| `hand.torque` | 扭矩控制（支持 mA 单位） |
| `hand.temperature` | 温度读取 |
| `hand.force_sensor` | 力传感器数据 |
| `hand.fault` | 故障读取 |
| `hand.version` | 设备版本信息 |
