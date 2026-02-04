# CAN 总线

L6/O6 灵巧手通过 CAN 总线通信。构造函数中的 `interface_type` 参数指定 CAN 适配器类型。

## 构造参数

```python
from linkerbot import L6

hand = L6(
    side="left",           # "left" 或 "right"
    interface_name="can0", # 接口名称
    interface_type="socketcan"  # 适配器类型
)
```

| 参数 | 说明 |
|------|------|
| `side` | 左手 `"left"` 或右手 `"right"` |
| `interface_name` | 接口名称，取决于操作系统和适配器 |
| `interface_type` | CAN 适配器类型，默认 `"socketcan"` |

## Linux (SocketCAN)

Linux 默认使用 SocketCAN，无需指定 `interface_type`。

```python
hand = L6(side="left", interface_name="can0")
```

配置 CAN 接口：

```bash
sudo ip link set can0 type can bitrate 1000000
sudo ip link set can0 up
```

## Windows (PCAN)

Windows 使用 PCAN 适配器：

```python
hand = L6(
    side="left",
    interface_name="PCAN_USBBUS1",
    interface_type="pcan"
)
```

其他适配器类型参考 [python-can 文档](https://python-can.readthedocs.io/en/stable/interfaces.html)。
