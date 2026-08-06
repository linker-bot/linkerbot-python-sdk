# 零点标定

通过 `hand.calibration` 将 L30 当前全部关节（J1～J17）的机械位置标定为新零点。

> **警告：** 标定成功后，设备会把当前位置写入 EEPROM，并立即将其作为全部关节的新零点。`confirm=True` 只表示调用者已确认风险，SDK 无法判断当前机械姿态是否正确。执行前必须按照机械装配要求摆放各关节，并确认手指周围无障碍物、无外力和无并发控制命令。

## 执行标定

```python
from linkerbot import L30

with L30(auto_start_periodic=False) as hand:
    hand.stop_polling()
    hand.calibration.calibrate_zero(confirm=True, timeout_ms=1000)
    print("零点标定完成，电机仍处于失能状态")
```

`calibrate_zero()` 会严格执行以下协议时序，只有收到当前步骤的成功 ACK 后才会继续：

| 步骤 | 操作                          | 请求 CAN FD ID（NodeID=1，HostID=0） |
| ---- | ----------------------------- | ------------------------------------ |
| 1    | 全局失能                      | `0x02210100`                         |
| 2    | 使用协议固定密码配置解锁      | `0x02602100`                         |
| 3    | 标定全部关节零点并写入 EEPROM | `0x0260A100`                         |

任一步失败时，SDK 会立即抛出异常，不发送后续写命令。方法成功返回后不会自动重新使能电机；应先读取并检查新的关节位置，再由应用显式决定是否使能。

全局失能一旦成功，后续解锁或标定失败也会保持失能状态。若标定请求已经发出但 ACK 超时，设备可能仍已完成 EEPROM 写入；此时不要直接重复标定，应先检查设备状态和关节零点。

`timeout_ms` 分别应用于三次 ACK 等待，不是整个流程共用的总超时。

## 参数保护

必须显式传入 `confirm=True`，否则不会发送任何 CAN FD 帧：

```python
from linkerbot import L30
from linkerbot.exceptions import ValidationError

with L30(auto_start_periodic=False) as hand:
    try:
        hand.calibration.calibrate_zero()
    except ValidationError as error:
        print(error)
```

配置解锁密码由 L30 通讯协议固定，SDK 不接受自定义密码，也不会自动重试。设备连续收到 10 次错误密码后会锁定配置写操作，必须重启设备才能再次尝试。

## 异常

| 异常或状态码             | 含义                                       |
| ------------------------ | ------------------------------------------ |
| `ValidationError`        | 未传 `confirm=True`，或 `timeout_ms` 非法  |
| `TimeoutError`           | 失能、解锁或标定 ACK 超时                  |
| `ProtocolError` / `0x20` | 配置未解锁或密码错误                       |
| `ProtocolError` / `0x23` | 当前状态不允许标定，例如舵机仍处于使能状态 |
| `ProtocolError` / `0x31` | 标定或 EEPROM 写入失败                     |
| `ProtocolError` / `0xF0` | 设备忙，应确认设备状态后再重试             |

不要在自动化测试或无人值守程序中调用零点标定。SDK 的单元测试只使用模拟 CAN FD 总线，不会修改实机零点。
