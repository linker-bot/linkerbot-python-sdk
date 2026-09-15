# 设备编码与版本信息

通过 `hand.version` 读取 L30 的设备编码、产品编码、NodeID 和左右手信息。

L30 的左右手不是通过构造参数指定的，而是通过设备内部编码查询。

## 读取完整 DeviceInfo

```python
from linkerbot import L30

with L30(auto_start_periodic=False) as hand:
    info = hand.version.get_device_info(timeout_ms=1000)
    print("产品 ID：", info.product_id)
    print("序列号：", info.serial_number)
    print("软件版本：", info.software_version)
    print("硬件版本：", info.hardware_version)
    print("结构版本：", info.structure_version)
    print("NodeID:", info.node_id)
    print("左右手：", info.hand_side.value)
    print("传感器类型：", info.sensor_type)
    print("组装厂：", info.origin)
```

## 读取产品编码

```python
from linkerbot import L30

with L30(auto_start_periodic=False) as hand:
    code = hand.version.get_product_code(timeout_ms=1000)
    print("产品编码：", code)
```

## 读取当前 NodeID

```python
from linkerbot import L30

with L30(auto_start_periodic=False) as hand:
    node_id = hand.version.get_node_id(timeout_ms=1000)
    print("设备当前 NodeID：", node_id)
```

## 判断当前连接的是左手还是右手

```python
from linkerbot import L30
from linkerbot.hand.l30 import L30HandSide

with L30(auto_start_periodic=False) as hand:
    side = hand.version.get_hand_side(timeout_ms=1000)
    if side is L30HandSide.LEFT:
        print("当前连接的是左手")
    else:
        print("当前连接的是右手")
```

## 完整示例

```python
from linkerbot import L30

with L30(auto_start_periodic=False) as hand:
    info = hand.version.get_device_info(timeout_ms=1000)
    product_code = hand.version.get_product_code(timeout_ms=1000)

    print("产品编码：", product_code)
    print("NodeID:", info.node_id)
    print("左右手：", info.hand_side.value)
```
