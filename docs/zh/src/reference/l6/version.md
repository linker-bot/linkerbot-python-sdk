# 版本信息

获取 L6 灵巧手的版本信息。

## 概述

通过 `hand.version` 访问版本管理功能：

- 获取设备完整信息（序列号、PCB/固件/机械版本）

## 获取设备信息

```python
hand.version.get_device_info() -> DeviceInfo
```

返回 `DeviceInfo` 对象，包含：

| 属性                 | 类型      | 说明                    |
| -------------------- | --------- | ----------------------- |
| `serial_number`      | `str`     | 设备序列号              |
| `pcb_version`        | `Version` | PCB 硬件版本            |
| `firmware_version`   | `Version` | 固件版本                |
| `mechanical_version` | `Version` | 机械结构版本            |
| `timestamp`          | `float`   | 获取时间（Unix 时间戳） |

`Version` 对象包含 `major`、`minor`、`patch` 属性，字符串格式为 `V{major}.{minor}.{patch}`。

**异常**：

- `TimeoutError`：请求超时

## 示例

### 读取设备信息

```python
from linkerbot import L6

hand = L6(channel="can0", hand_id=1)

info = hand.version.get_device_info()
print(f"序列号：{info.serial_number}")
print(f"固件版本：{info.firmware_version}")

hand.close()
```
