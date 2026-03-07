# 参数配置

## 速度与加速度限制

设置 7 个关节的速度和加速度限制，影响 `move_j`、`move_p` 等运动。

```python
from linkerbot import A7lite

with A7lite(side="left", interface_name="can0") as arm:
    arm.enable()
    # 将所有关节速度限制设为 2.0 rad/s
    arm.set_velocities([2.0] * 7)
    # 分别设置各关节加速度限制
    arm.set_accelerations([10.0, 9.0, 8.0, 7.0, 6.0, 5.0, 4.0])
```

| 方法                               | 参数                           | 范围        | 说明      |
| ---------------------------------- | ------------------------------ | ----------- | --------- |
| `set_velocities(velocities)`       | 7 个关节的速度上限（rad/s）    | [0.0, 50.0] | 默认 0.5  |
| `set_accelerations(accelerations)` | 7 个关节的加速度上限（rad/s²） | [1.0, 50.0] | 默认 10.0 |

**异常**：`ValidationError`（必须提供恰好 7 个值，或值超出范围时）

## PID 参数设置

设置 7 个关节的 PID 参数。

```python
from linkerbot import A7lite

with A7lite(side="left", interface_name="can0") as arm:
    arm.set_position_kps([100.0] * 7)
    arm.set_velocity_kps([0.5] * 7)
    arm.set_velocity_kis([0.01] * 7)
    arm.set_velocity_filt_gains([0.8] * 7)
```

| 方法                             | 参数                     | 说明                         |
| -------------------------------- | ------------------------ | ---------------------------- |
| `set_position_kps(kps)`          | 7 个关节的位置 Kp 值     | 位置环比例增益               |
| `set_velocity_kps(kps)`          | 7 个关节的速度 Kp 值     | 速度环比例增益               |
| `set_velocity_kis(kis)`          | 7 个关节的速度 Ki 值     | 速度环积分增益               |
| `set_velocity_filt_gains(gains)` | 7 个关节的速度滤波器增益 | 增益越大滤波越强，响应越滞后 |

### 参数速查

| 参数类型              | 默认值      | 范围               |
| --------------------- | ----------- | ------------------ |
| 速度限制              | 0.5 rad/s   | [0.0, 50.0] rad/s  |
| 加速度限制            | 10.0 rad/s² | [1.0, 50.0] rad/s² |
| `move_l` 最大平移速度 | 0.05 m/s    | (0, 0.4] m/s       |
| `move_l` 最大角速度   | 0.3 rad/s   | (0, 3.0] rad/s     |
| `move_l` 平移加速度   | 0.1 m/s²    | (0, 1.0] m/s²      |
| `move_l` 角加速度     | 0.1 rad/s²  | (0, 1.0] rad/s²    |

## 示例

### 设置 PID 参数、速度和加速度限制

```python
from linkerbot import A7lite

with A7lite(side="left", interface_name="can0") as arm:
    arm.set_position_kps([80.0] * 7)
    arm.set_velocity_kps([0.4] * 7)
    arm.set_velocity_kis([0.008] * 7)
    arm.set_velocity_filt_gains([0.9] * 7)
    arm.set_velocities([1.0] * 7)
    arm.set_accelerations([5.0] * 7)
```
