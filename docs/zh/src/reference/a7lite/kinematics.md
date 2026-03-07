# 运动学

## 正运动学

根据关节角度计算 TCP 位姿。

```python
pose = arm.forward_kinematics([0.0, 0.0, 0.0, 1.57, 0.0, 0.0, 0.0])
print(f"TCP: ({pose.x:.3f}, {pose.y:.3f}, {pose.z:.3f})")
```

**参数：**

- `angles`: 7 个关节角度（rad），类型 `list[float]`

**返回值：**

- `Pose`: TCP 位姿

## 逆运动学

根据 TCP 位姿求解关节角度。

```python
from linkerbot import Pose

target = Pose(x=0.0, y=0.33, z=-0.25, rx=1.85, ry=0.0, rz=-1.57)
angles = arm.inverse_kinematics(target)
print(f"关节角度：{angles}")
```

**参数：**

- `pose`: 目标 TCP 位姿，类型 `Pose`
- `current_angles`: IK 初始猜测关节角度，类型 `list[float] | None`，`None` 时从电机读取

**返回值：**

- `list[float]`: 7 个关节角度（rad）

## 关节限位

```python
# 获取当前关节限位
limits = arm.get_joint_limits()
print(limits)  # [(lower0, upper0), (lower1, upper1), ...]

# 设置自定义关节限位
arm.set_joint_limits([(-1.0, 1.0)] * 7)
```
