# 角度控制

通过 `hand.angle` 控制和读取 L30 的 17 个关节角度。API 与 L6 对齐:`set_angles` 走 **0-100 归一化百分比**,`set_raw_angles` 走协议原始整数。

- **关节数量**:17 个,顺序 `J1` 到 `J17`
- **默认单位**:0-100 float 百分比。0% 映射到关节的 `spec.minimum`,100% 映射到 `spec.maximum`
- **对称关节**(J5 / J12–J14 / J17):50% 是中立位(raw 0)
- **原始范围**:通过 `L30_JOINT_SPECS` 查看每个关节的 `[minimum, maximum]`

## 设置角度(推荐:0-100 百分比)

```python
from linkerbot import L30

# 每关节 30 % → 弯曲手指指端 30 %,对称关节 30 % 略偏向一侧
half_open = [30.0] * 17

with L30() as hand:
    hand.control.enable(timeout_ms=1000)
    hand.angle.set_angles(half_open)
```

想要"手掌张开、腕关节居中"的中立姿势,对称关节要写 50%:

```python
from linkerbot.hand.l30 import L30_JOINT_SPECS

# 屈曲关节 0%(完全张开),对称/腕关节 50%(中立)
neutral = [50.0 if spec.minimum < 0 else 0.0 for spec in L30_JOINT_SPECS]

with L30() as hand:
    hand.control.enable(timeout_ms=1000)
    hand.angle.set_angles(neutral)
```

## 设置原始角度(协议整数)

需要直接下发协议原始值时使用 `set_raw_angles`,每个值需在关节 `spec` 范围内:

```python
from linkerbot import L30

with L30() as hand:
    hand.control.enable(timeout_ms=1000)
    # 全部下发 raw 0(J1-J4/J6-J11/J15/J16 = 完全张开;J5/J12-J14/J17 = 中立)
    hand.angle.set_raw_angles([0] * 17)
```

## 使用 L30Angle 对象

`L30Angle` 内部存 0-100 百分比,提供 `to_raw()` / `from_raw()` 两个转换方法:

```python
from linkerbot import L30
from linkerbot.hand.l30 import L30Angle, L30_JOINT_SPECS

# 从百分比构造
angle = L30Angle.from_list([30.0] * 17)
print(angle.to_list())      # → 17 个 30.0
print(angle.to_raw())       # → 17 个 raw 整数,每关节对应 spec.range 的 30%

# 从原始整数构造(严格校验 spec 范围)
angle = L30Angle.from_raw([spec.maximum for spec in L30_JOINT_SPECS])
print(angle.to_list())      # → 17 个 100.0

with L30() as hand:
    hand.control.enable(timeout_ms=1000)
    hand.angle.set_angles(angle)
```

## 查看关节范围

```python
from linkerbot.hand.l30 import L30_JOINT_SPECS

for index, spec in enumerate(L30_JOINT_SPECS):
    print(index, spec.name, spec.minimum, spec.maximum)
```

## 阻塞读取角度

读回的 `data.angles` 是 `L30Angle` 百分比表示,`to_raw()` 可拿到原始 sensor 值:

```python
from linkerbot import L30
from linkerbot.exceptions import TimeoutError

with L30() as hand:
    try:
        data = hand.angle.get_blocking(timeout_ms=1000)
        print("百分比:", data.angles.to_list())     # 0-100 float(硬件超调时可能略超范围)
        print("原始值:", data.angles.to_raw())      # 协议整数
        print("时间戳:", data.timestamp)
    except TimeoutError:
        print("角度读取超时")
```

## 缓存读取

```python
from linkerbot import L30

with L30() as hand:
    hand.angle.get_blocking(timeout_ms=1000)
    data = hand.angle.get_snapshot()
    if data is not None:
        print(data.angles.to_list())
```

## 完整示例

```python
from linkerbot import L30

with L30() as hand:
    hand.control.enable(timeout_ms=1000)
    hand.angle.set_angles([30.0] * 17)          # 每关节 30 %
    data = hand.angle.get_blocking(timeout_ms=1000)
    print("当前角度(百分比):", data.angles.to_list())
    print("当前角度(原始值):", data.angles.to_raw())
```

## 与 L6 API 差异

| 项 | L6 | L30 |
|---|---|---|
| `set_angles(list)` | 6 个 float 0-100 | **17 个 float 0-100**(与 L6 语义一致) |
| `set_raw_angles(list)` | 6 个 int 0-255 | **17 个 int,每关节独立 spec 范围** |
| `L30Angle` / `L6Angle` | 存 0-100 float | 存 0-100 float |
| `to_raw()` | 0-255 | 每关节 spec 整数 |
