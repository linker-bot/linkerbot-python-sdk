# 运动控制

## 回零

将所有关节移动到零位。

```python
from linkerbot import A7

with A7(side="left", interface_name="can0") as arm:
    arm.enable()
    arm.home()  # 阻塞模式
    arm.home(blocking=False)  # 非阻塞模式
```

**参数：**

- `blocking`: 是否阻塞等待运动完成，默认 `True`。

## move_j

通过发送每个关节的目标角度，控制机械臂运动。

```python
from linkerbot import A7

with A7(side="left", interface_name="can0") as arm:
    arm.enable()
    arm.move_j([0.0, 0.0, 0.0, 1.57, 0.0, 0.0, 0.0])
```

**参数：**

- `target_joints`: 7 个关节的目标角度（rad），类型 `list[float]`
- `blocking`: 是否阻塞直到运动完成，默认 `True`，类型 `bool`

**异常：**

- `StateError`: 机械臂运动中再次调用时
- `ValidationError`: 目标角度超出关节限位时

## move_p

通过发送机械臂 TCP 6D 位姿（x, y, z, rx, ry, rz），控制机械臂运动。通过逆运动学求解目标关节角度后执行关节运动，末端路径**不保证**为直线。

```python
from linkerbot import A7, Pose

with A7(side="left", interface_name="can0") as arm:
    arm.enable()
    target = Pose(x=0.0, y=0.33, z=-0.25, rx=1.85, ry=0.0, rz=-1.57)
    arm.move_p(target)
```

**参数：**

- `target_pose`: 目标 TCP 位姿，类型 `linkerbot.arm.Pose`
- `current_angles`: IK 初始猜测关节角度，类型 `list[float] | None`，`None` 时从电机读取，
- `blocking`: 是否阻塞直到运动完成，类型 `bool`，默认 `True`，

**异常：**

- `StateError`: 机械臂运动中再次调用时
- `RuntimeError`: IK 求解失败时

## move_l

通过发送机械臂 TCP 6D 位姿（x, y, z, rx, ry, rz），控制机械臂**直线**运动。末端沿笛卡尔空间直线运动，位置使用梯形速度规划，姿态使用球面线性插值（Slerp）。`move_l` 始终阻塞直到运动完成，无 `blocking` 参数。

```python
from linkerbot import A7, Pose

with A7(side="left", interface_name="can0") as arm:
    arm.enable()
    target = Pose(x=0.0, y=0.33, z=-0.25, rx=1.85, ry=0.0, rz=-1.57)
    arm.move_l(target)
```

**参数：**

- `target_pose`: 目标 TCP 位姿，类型 `Pose`
- `max_velocity`: TCP 线性运动梯形速度规划的最大速度（m/s），默认 `0.05`，范围 `(0, 0.4]`
- `max_angular_velocity`: TCP 旋转运动梯形速度规划的最大角速度（rad/s），默认 `0.3`，范围 `(0, 3.0]`
- `acceleration`: TCP 线性运动梯形速度规划的最大加速度（m/s²），默认 `0.1`，范围 `(0, 1.0]`
- `angular_acceleration`: TCP 旋转运动梯形速度规划的最大角加速度（rad/s²），默认 `0.1`，范围 `(0, 1.0]`
- `current_pose`: 起始 TCP 位姿，`None` 时由 `current_angles` 或电机读取计算，类型 `Pose | None`
- `current_angles`: 起始关节角度，`None` 时从电机读取，类型 `list[float] | None`

**异常：**

- `StateError`: 机械臂运动中再次调用时
- `ValidationError`: 参数超出范围时
- `RuntimeError`: 路径点 IK 求解失败时

## 运动状态检测

返回机械臂当前是否处于运动状态。

```python
if arm.is_moving():
    print("正在运动中...")
```

**返回值：**

- `bool`: 是否在运动中

## 等待运动完成

阻塞当前线程，直到运动计时器归零。通常配合 `blocking=False` 使用。

```python
arm.move_j([0.0, 0.0, 0.0, 1.57, 0.0, 0.0, 0.0], blocking=False)
# ... 执行其他操作 ...
arm.wait_motion_done()  # 等待运动结束
```

## 示例

### 非阻塞运动与等待

```python
from linkerbot import A7, Pose

with A7(side="left", interface_name="can0") as arm:
    arm.enable()
    arm.home()

    # 设置速度和加速度
    arm.set_velocities([1.0] * 7)
    arm.set_accelerations([10.0] * 7)

    # 非阻塞 move_j：发送后立即返回，可执行其他操作
    arm.move_j([0.0, 0.0, 0.0, 1.57, 0.0, 0.0, 0.0], blocking=False)
    print("move_j 已发送，正在运动中...")
    arm.wait_motion_done()  # 等待运动完成

    # 阻塞 move_p：调用直接等到运动完成，无需 wait_motion_done
    target = Pose(x=0.0, y=0.33, z=-0.25, rx=1.85, ry=0.0, rz=-1.57)
    arm.move_p(target)

    # move_l 始终阻塞
    target = Pose(x=0.1, y=0.33, z=-0.2, rx=1.85, ry=0.0, rz=-1.57)
    arm.move_l(target)

    arm.home()
```
