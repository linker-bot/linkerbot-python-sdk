# 角度控制

通过 `hand.angle` 控制和读取 O20 的 16 个关节角度。API 与 L6 / L30 对齐:`set_angles` 走 **0-100 归一化百分比**,`set_raw_angles` 走协议原始整数(度)。

- **关节数量**:16 个,按 motor ID 1~16 顺序
- **默认单位**:0-100 float 百分比。0% 映射到关节的 `spec.minimum`,100% 映射到 `spec.maximum`
- **对称外展关节**(`index_abd` / `middle_abd` / `ring_abd` / `pinky_abd`):50% 是中立位(0 度)
- **原始范围**:通过 `O20_JOINT_SPECS` 查看每个关节的 `[minimum, maximum]`(单位度)

## 设置角度(推荐:0-100 百分比)

```python
from linkerbot.hand.o20 import O20

# 每关节 30 %:屈曲关节稍微弯曲,外展关节偏一侧
half_flex = [30.0] * 16

with O20(side="right") as hand:
    hand.speed.set_all(40)     # 建议先设速度上限
    hand.torque.set_all(400)   # 建议先设扭矩上限
    hand.angle.set_angles(half_flex)
```

想要「手掌张开、外展关节居中」的中立姿势,外展关节要写 50%:

```python
from linkerbot.hand.o20 import O20, O20_JOINT_SPECS

# 屈曲关节 0%(完全张开),对称外展 50%(中立)
neutral = [50.0 if spec.minimum < 0 else 0.0 for spec in O20_JOINT_SPECS]

with O20(side="right") as hand:
    hand.angle.set_angles(neutral)
```

## 设置原始角度(协议整数,单位度)

需要直接下发协议原始度数时使用 `set_raw_angles`,每个值需在关节 `spec` 范围内:

```python
from linkerbot.hand.o20 import O20

with O20(side="right") as hand:
    # 所有关节到 raw 0(屈曲关节 = 完全张开;外展关节 = 中立 0 度)
    hand.angle.set_raw_angles([0] * 16)
```

## 使用 O20Angle 对象

`O20Angle` 内部存 0-100 百分比,提供 `to_raw() / from_raw()` 双向转换:

```python
from linkerbot.hand.o20 import O20, O20Angle, O20_JOINT_SPECS

# 从百分比构造
angle = O20Angle.from_list([30.0] * 16)
print(angle.to_list())      # → 16 个 30.0
print(angle.to_raw())       # → 16 个 raw 整数,每关节 spec.range 的 30%

# 从原始度数构造(严格校验 spec 范围)
angle = O20Angle.from_raw([spec.maximum for spec in O20_JOINT_SPECS])
print(angle.to_list())      # → 16 个 100.0

with O20(side="right") as hand:
    hand.angle.set_angles(angle)
```

## 查看关节范围

```python
from linkerbot.hand.o20 import O20_JOINT_SPECS

for index, spec in enumerate(O20_JOINT_SPECS):
    print(index, spec.name, spec.finger, spec.minimum, spec.maximum)
```

## 阻塞读取角度

读回的 `data.angles` 是 `O20Angle` 百分比表示,`to_raw()` 可拿到原始 sensor 度数:

```python
from linkerbot.hand.o20 import O20
from linkerbot.exceptions import TimeoutError

with O20(side="right") as hand:
    try:
        data = hand.angle.get_blocking(timeout_ms=1000)
        print("百分比:", data.angles.to_list())     # 0-100 float(硬件超调时可略超范围)
        print("原始度:", data.angles.to_raw())      # 协议整数,单位度
        print("时间戳:", data.timestamp)
    except TimeoutError:
        print("角度读取超时")
```

## 缓存读取(非阻塞)

`get_snapshot()` 返回最近一次收到的角度数据,没有触发新读:

```python
from linkerbot.hand.o20 import O20

with O20(side="right") as hand:
    hand.angle.get_blocking(timeout_ms=1000)  # 先触发一次真读
    data = hand.angle.get_snapshot()
    if data is not None:
        print(data.angles.to_list())
```

## 完整示例

```python
from linkerbot.hand.o20 import O20, O20_JOINT_SPECS

with O20(side="right") as hand:
    hand.speed.set_all(40)
    hand.torque.set_all(400)

    neutral = [50.0 if spec.minimum < 0 else 0.0 for spec in O20_JOINT_SPECS]
    hand.angle.set_angles(neutral)

    data = hand.angle.get_blocking(timeout_ms=1000)
    print("当前角度(百分比):", [round(v, 1) for v in data.angles.to_list()])
    print("当前角度(度):    ", data.angles.to_raw())
```

## 与 L6 / L30 差异

| 项 | L6 | L30 | O20 |
| ---- | ---- | ---- | ---- |
| `set_angles(list)` | 6 个 float 0-100 | 17 个 float 0-100 | **16 个 float 0-100** |
| `set_raw_angles(list)` | 6 个 int 0-255 | 17 个 int,每关节 spec 范围 | **16 个 int,每关节 spec 范围(单位度)** |
| 角度值物理单位 | 无(归一化) | 无(归一化 raw) | 度(spec 用度数标注) |
| `to_raw()` | 0-255 | 每关节 spec 整数 | 每关节 spec 整数(度) |
