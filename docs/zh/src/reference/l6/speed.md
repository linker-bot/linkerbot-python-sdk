# 速度控制

控制 L6 灵巧手各关节电机的运动速度。

## 设置速度

```python
hand.speed.set_speeds(speeds)
```

设置 6 个关节电机的目标速度。

**参数：**

- `speeds`: `L6Speed` 实例或 6 元素列表，速度范围 0-100（无单位）

**手指顺序：** 拇指弯曲、拇指侧摆、食指、中指、无名指、小指

## 示例

### 列表方式

```python
from linkerbot import L6

with L6(side="left", interface_name="can0") as hand:
    # 所有手指设为中速
    hand.speed.set_speeds([50.0, 50.0, 50.0, 50.0, 50.0, 50.0])
```

### L6Speed 方式

```python
from linkerbot import L6
from linkerbot.hand.l6 import L6Speed

with L6(side="left", interface_name="can0") as hand:
    # 拇指慢速，其他手指快速
    speed = L6Speed(
        thumb_flex=30.0, thumb_abd=30.0, index=80.0, middle=80.0, ring=80.0, pinky=80.0
    )
    hand.speed.set_speeds(speed)
```
