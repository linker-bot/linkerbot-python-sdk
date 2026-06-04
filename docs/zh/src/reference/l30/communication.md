# 通讯与生命周期

本页说明 L30 的连接方式、关闭方式、使能/失能，以及单设备、多设备、多 CANFD 模块通讯示例。

## 单只手连接

`L30()` 适合一只手连接到一个 CANFD 模块/通道的场景。

```python
from linkerbot import L30

with L30(node_id=1, device_index=0, channel_index=0) as hand:
    print("连接成功，NodeID：", hand.node_id)
```

如果动态库不在系统搜索路径中：

```python
from linkerbot import L30

with L30(
    node_id=1,
    device_index=0,
    channel_index=0,
    library_path="/home/linkerhand/code/HK/libcanbus.so",
) as hand:
    print("连接成功")
```

## 关闭连接

推荐使用 `with` 自动关闭：

```python
from linkerbot import L30

with L30() as hand:
    print(hand.is_closed())
```

也可以手动关闭：

```python
from linkerbot import L30

hand = L30()
try:
    print("是否已关闭：", hand.is_closed())
finally:
    hand.close()
```

`close()` 会释放 SDK 资源，并关闭本实例开启过的周期上报，但不会自动发送电机失能命令。

## 使能电机

```python
from linkerbot import L30

with L30() as hand:
    hand.control.enable(timeout_ms=1000)
    print("已使能")
```

## 失能电机

```python
from linkerbot import L30

with L30() as hand:
    hand.control.disable(timeout_ms=1000)
    print("已失能")
```

## 一个 CANFD 模块/通道连接多只手

如果同一条 CANFD 总线上有多只 L30，不要为每只手分别创建独立 `L30()` 去连接同一个模块/通道。应该使用一个 `L30Bus`，让这些手共享同一个 dispatcher。

```python
from linkerbot import L30Bus

with L30Bus(device_index=0, channel_index=0, auto_start_periodic=False) as bus:
    hands = bus.connect([1, 2, 3])

    for hand in hands:
        print("NodeID：", hand.node_id)
        print("角度：", hand.angle.get_blocking(timeout_ms=1000).angles.to_list())
```

按 NodeID 字典访问：

```python
from linkerbot import L30Bus

with L30Bus(device_index=0, channel_index=0, auto_start_periodic=False) as bus:
    hands = bus.connect_map([1, 2])

    hands[1].control.enable(timeout_ms=1000)
    hands[2].control.enable(timeout_ms=1000)
```

一只一只创建：

```python
from linkerbot import L30Bus

with L30Bus(device_index=0, channel_index=0, auto_start_periodic=False) as bus:
    hand1 = bus.create_hand(1)
    hand2 = bus.create_hand(2)

    print(hand1.version.get_hand_side(timeout_ms=1000).value)
    print(hand2.version.get_hand_side(timeout_ms=1000).value)
```

同一个 `L30Bus` 内，NodeID 必须唯一。

## 多个 CANFD 模块/通道连接多只手

如果你有多个 CANFD 模块，或者一个模块上有多个通道，就为每个模块/通道创建一个 `L30Bus`。不同 `L30Bus` 之间是不同物理总线，因此可以复用相同 NodeID。

```python
from contextlib import ExitStack

from linkerbot import L30Bus

with ExitStack() as stack:
    bus0 = stack.enter_context(
        L30Bus(device_index=0, channel_index=0, auto_start_periodic=False)
    )
    bus1 = stack.enter_context(
        L30Bus(device_index=1, channel_index=0, auto_start_periodic=False)
    )

    # 两只手都使用 NodeID=1，但它们在不同 CANFD 模块上，所以不会冲突。
    hand_on_module0 = bus0.create_hand(1)
    hand_on_module1 = bus1.create_hand(1)

    print("模块 0 / 节点 1 手型：", hand_on_module0.version.get_hand_side(timeout_ms=1000).value)
    print("模块 1 / 节点 1 手型：", hand_on_module1.version.get_hand_side(timeout_ms=1000).value)
```

应用层统一管理时，建议使用 `(device_index, channel_index, node_id)` 或业务别名作为 key：

```python
from contextlib import ExitStack

from linkerbot import L30Bus

with ExitStack() as stack:
    bus0 = stack.enter_context(L30Bus(device_index=0, channel_index=0))
    bus1 = stack.enter_context(L30Bus(device_index=1, channel_index=0))

    hands = {
        (0, 0, 1): bus0.create_hand(1),
        (1, 0, 1): bus1.create_hand(1),
    }

    print(hands[(0, 0, 1)].angle.get_blocking(timeout_ms=1000).angles.to_list())
    print(hands[(1, 0, 1)].angle.get_blocking(timeout_ms=1000).angles.to_list())
```

## 通讯拓扑规则

- `device_index`：厂商动态库扫描到的第几个 CANFD 模块/适配器。
- `channel_index`：该 CANFD 模块上的第几个 CANFD 通道。
- `node_id`：某一条 CANFD 总线上的 L30 手节点 ID。
- `host_id`：主机在 L30 CANFD 协议帧里的源 ID。
- 同一个 `L30Bus` 中 NodeID 必须唯一。
- 不同 `L30Bus`（不同 CANFD 模块/通道）可以复用相同 NodeID。
- `L30Bus` 返回的是普通 `L30` 对象，所以 `hand.angle`、`hand.speed`、`hand.force_sensor` 等接口完全一样。
- 左右手请通过 `hand.version.get_hand_side()` 或 `hand.version.get_device_info()` 查询，不要只靠变量名猜测。
