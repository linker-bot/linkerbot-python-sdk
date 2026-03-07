# 版本信息

获取 O6 灵巧手的版本信息。

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
from linkerbot import O6

hand = O6(side="left", interface_name="can0")

info = hand.version.get_device_info()
print(f"序列号：{info.serial_number}")
print(f"PCB 版本：{info.pcb_version}")
print(f"固件版本：{info.firmware_version}")
print(f"机械版本：{info.mechanical_version}")

hand.close()
```
