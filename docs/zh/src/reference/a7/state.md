# 状态读取

## 完整状态快照

一次性读取完整的机械臂状态，包含 TCP 位姿、所有关节的角度、速度、加速度、扭矩和温度。

```python
from linkerbot import A7

with A7(side="left", interface_name="can0") as arm:
    arm.enable()
    state = arm.get_state()
    print(state.pose)
    print(f"第一个关节实际角度：{state.joint_angles[0].angle:.4f} rad")
```

**返回值**

- `State`: 包含 `pose`、`joint_angles`、`joint_control_angles`、`joint_velocities`、`joint_control_velocities`、`joint_control_acceleration`、`joint_torques`、`joint_temperatures`

### State 数据模型

| 属性                         | 说明                                            |
| ---------------------------- | ----------------------------------------------- |
| `pose`                       | TCP 位姿（Pose）                                |
| `joint_angles`               | 7 个关节的实际角度（list[AngleState]）          |
| `joint_control_angles`       | 7 个关节的控制角度（list[AngleState]）          |
| `joint_velocities`           | 7 个关节的实际速度（list[VelocityState]）       |
| `joint_control_velocities`   | 7 个关节的控制速度（list[VelocityState]）       |
| `joint_control_acceleration` | 7 个关节的控制加速度（list[AccelerationState]） |
| `joint_torques`              | 7 个关节的实际扭矩（list[TorqueState]）         |
| `joint_temperatures`         | 7 个关节的温度（list[TemperatureState]）        |

各子状态模型均包含值字段和 `timestamp`（UNIX 时间戳，秒）。

### 子状态模型字段

| 模型                | 值字段          | 时间戳字段   |
| ------------------- | --------------- | ------------ |
| `AngleState`        | `.angle`        | `.timestamp` |
| `VelocityState`     | `.velocity`     | `.timestamp` |
| `AccelerationState` | `.acceleration` | `.timestamp` |
| `TorqueState`       | `.torque`       | `.timestamp` |
| `TemperatureState`  | `.temperature`  | `.timestamp` |

## 单项状态读取

除 `get_state()` 外，以下方法分别返回单一类型的状态数据，均返回 7 个关节的列表（`get_pose()` 除外）。

```python
from linkerbot import A7

with A7(side="left", interface_name="can0") as arm:
    arm.enable()
    angles = arm.get_angles()
    velocities = arm.get_velocities()
    temps = arm.get_temperatures()
    pose = arm.get_pose()
    print(f"第二个关节实际角度：{angles[1]:.4f} rad")
    print(f"第三个关节实际速度：{velocities[2]:.4f} rad/s")
    print(f"第四个关节实际温度：{temps[3]:.1f} °C")
    print(f"TCP: ({pose.x:.3f}m, {pose.y:.3f}m, {pose.z:.3f}m)")
```

**返回值**

| 方法                         | 返回值               | 单位   |
| ---------------------------- | -------------------- | ------ |
| `get_angles()`               | 7 个关节的实际角度   | rad    |
| `get_control_angles()`       | 7 个关节的控制角度   | rad    |
| `get_velocities()`           | 7 个关节的实际速度   | rad/s  |
| `get_control_velocities()`   | 7 个关节的控制速度   | rad/s  |
| `get_control_acceleration()` | 7 个关节的控制加速度 | rad/s² |
| `get_torques()`              | 7 个关节的实际扭矩   | Nm     |
| `get_temperatures()`         | 7 个关节的温度       | °C     |
| `get_pose()`                 | TCP 位姿             | m, rad |

## 传感器数据

A7 使用轮询模式采集传感器数据，`get_*()` 返回的是上一次轮询时的值。

| 数据类型 | 单位  | 默认轮询间隔 | 最大延迟  |
| -------- | ----- | ------------ | --------- |
| 角度     | rad   | 10 ms        | ≈ 10 ms   |
| 速度     | rad/s | 10 ms        | ≈ 10 ms   |
| 扭矩     | Nm    | 50 ms        | ≈ 50 ms   |
| 温度     | °C    | 1000 ms      | ≈ 1000 ms |

如需更低延迟，可通过 `start_polling()` 方法自定义不同传感器的轮询间隔：

```python
from linkerbot import A7
from linkerbot.arm.a7 import SensorType

with A7(side="left", interface_name="can0") as arm:
    arm.start_polling(
        {
            SensorType.POSITION: 0.005,  # 5 ms = 200 Hz
            SensorType.VELOCITY: 0.005,
            SensorType.TORQUE: 0.1,
            SensorType.TEMPERATURE: 2.0,
        }
    )
    arm.enable()
    arm.home()
```
