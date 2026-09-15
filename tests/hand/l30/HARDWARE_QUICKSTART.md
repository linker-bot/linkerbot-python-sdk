# L30 硬件测试快速开始

本文说明如何运行 `tests/hand/l30/` 下的 L30 CANFD 硬件测试。

## 前置条件

- L30 手已经连接到 CANFD 适配器。
- `libcanbus.so` 或 `HCanbus.dll` 可访问。
- Linux 下如果需要 root 权限访问 CANFD 适配器，使用 `sudo -E` 保留环境变量。
- 确认手周围没有障碍物，尤其是在运行 enable、speed、torque、angle 写命令测试前。

## 默认安全门控

所有 L30 硬件测试都带有以下 marker：

- `l30`
- `canfd`
- `hardware`
- `interactive`

项目默认 pytest 配置会排除 `interactive`，所以普通测试不会触碰真实 L30 硬件。

硬件测试还需要环境变量二次确认：

- `L30_HARDWARE_FULL=1`：允许运行 L30 硬件测试。
- `L30_ALLOW_MOTION=1`：允许运行 enable、speed、torque、angle 写命令测试。

只读测试不需要 `L30_ALLOW_MOTION`。

## 环境变量

必填：

```bash
export LINKERBOT_CANFD_LIB=/home/linkerhand/code/HK/libcanbus.so
```

常用可选项：

```bash
export L30_NODE_ID=1
export L30_HOST_ID=0
export L30_DEVICE_INDEX=0
export L30_CHANNEL_INDEX=0
export L30_TIMEOUT_MS=1000
```

写命令/运动相关可选项：

```bash
export L30_SAFE_SPEED=20
export L30_SAFE_TORQUE=60
export L30_SAFE_ANGLES=0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0
```

触觉传感器可选项：

```bash
export L30_FORCE_ALL_FINGERS=1
```

Polling 可选项：

```bash
export L30_POLL_INTERVAL_S=0.2
```

## 最小 smoke 测试

只打开设备并读取一次角度，不发送运动命令：

```bash
sudo -E env \
  L30_HARDWARE_SMOKE=1 \
  LINKERBOT_CANFD_LIB=/home/linkerhand/code/HK/libcanbus.so \
  uv run --group test pytest \
  tests/hand/l30/test_hardware_smoke.py \
  -m "hardware and interactive" -v
```

## 全量只读硬件测试

运行 lifecycle、角度读取、速度读取、电流、温度、故障、触觉单指、周期上报、stream、polling、snapshot 等测试；不会运行需要 `L30_ALLOW_MOTION=1` 的写命令测试。

```bash
sudo -E env \
  L30_HARDWARE_FULL=1 \
  LINKERBOT_CANFD_LIB=/home/linkerhand/code/HK/libcanbus.so \
  L30_NODE_ID=1 \
  L30_HOST_ID=0 \
  L30_DEVICE_INDEX=0 \
  L30_CHANNEL_INDEX=0 \
  L30_TIMEOUT_MS=1000 \
  uv run --group test pytest \
  tests/hand/l30 \
  -m "hardware and interactive" -v
```

## 写命令/运动 smoke 测试

这些测试会执行 enable/disable、设置速度、设置 torque，以及在提供 `L30_SAFE_ANGLES` 时发送 angle 目标。运行前确认手周围无障碍。

```bash
sudo -E env \
  L30_HARDWARE_FULL=1 \
  L30_ALLOW_MOTION=1 \
  LINKERBOT_CANFD_LIB=/home/linkerhand/code/HK/libcanbus.so \
  L30_SAFE_SPEED=20 \
  L30_SAFE_TORQUE=60 \
  uv run --group test pytest \
  tests/hand/l30/test_hardware_control.py \
  tests/hand/l30/test_hardware_speed.py \
  tests/hand/l30/test_hardware_torque.py \
  -m "hardware and interactive" -v
```

如果需要测试角度写入，显式提供 17 个安全 raw angle：

```bash
sudo -E env \
  L30_HARDWARE_FULL=1 \
  L30_ALLOW_MOTION=1 \
  LINKERBOT_CANFD_LIB=/home/linkerhand/code/HK/libcanbus.so \
  L30_SAFE_ANGLES=0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0 \
  uv run --group test pytest \
  tests/hand/l30/test_hardware_angle.py \
  -m "hardware and interactive" -v
```

## 每个测试文件覆盖的功能

| 文件                            | 功能                                                |
| ------------------------------- | --------------------------------------------------- |
| `test_hardware_smoke.py`        | 最小打开设备 + 角度读取                             |
| `test_hardware_lifecycle.py`    | context manager、`close()`、`is_closed()`           |
| `test_hardware_control.py`      | `control.enable()` / `control.disable()`            |
| `test_hardware_angle.py`        | `angle.get_blocking()`、snapshot、可选安全角度写入  |
| `test_hardware_speed.py`        | `speed.get_blocking()`、snapshot、可选安全速度写入  |
| `test_hardware_torque.py`       | `torque.set_all()`、target snapshot                 |
| `test_hardware_current.py`      | `current.get_blocking()`、snapshot                  |
| `test_hardware_temperature.py`  | `temperature.get_blocking()`、snapshot              |
| `test_hardware_fault.py`        | `fault.get_blocking()`、snapshot、fault bit helpers |
| `test_hardware_force_sensor.py` | 单指触觉读取；可选五指读取                          |
| `test_hardware_report.py`       | 周期上报配置、默认上报、disable/disable_all         |
| `test_hardware_stream.py`       | `stream()`、`stop_stream()`、周期 angle event       |
| `test_hardware_polling.py`      | host polling，非设备侧周期上报                      |
| `test_hardware_snapshot.py`     | 多传感器读取后的 `get_snapshot()`                   |

## 安全注意事项

- 默认只读硬件测试不会设置 `L30_ALLOW_MOTION`，不会主动发送 enable、torque、speed 或 angle movement。
- 写命令测试必须显式设置 `L30_ALLOW_MOTION=1`。
- `test_hardware_control.py` 会在 `finally` 中调用 disable。
- 周期上报相关测试会在 `finally` 中调用停止/禁用逻辑，避免测试结束后设备持续上报。
- 如果测试异常中断，建议手动断电或运行 disable 流程确认硬件处于安全状态。
