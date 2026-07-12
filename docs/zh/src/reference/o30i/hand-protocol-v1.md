# HandProtocol_v1.0 (HOP)

`HandProtocolV1` 是与具体手型、`libcanbus.so` 和 SocketCAN 解耦的对象协议层。O30i 在它之上提供设备对象定义和安全的高层 manager。

## 帧格式

O30i 默认使用标准帧请求 ID `0x001` 和响应 ID `0x401`：

```text
Byte 0   CTRL：bit7=RTS，bit0..6=主索引 MI
Byte 1   SI：对象内字节偏移
Byte 2   EDL：有效数据长度
Byte 3.. Payload：写请求或响应的有效数据
```

读请求只有三个头字节；写请求在头后携带 EDL 个数据字节：

```text
01 14 05                   读取五指指尖实际位置
81 14 05                   读取五指指尖设定位置（RTS=1）
01 14 05 80 80 80 80 80    写入五指指尖位置
```

对应 `can-utils` 命令：

```bash
cansend can0 001##0011405
cansend can0 001##0811405
cansend can0 001##00114058080808080
```

`##0` 表示 CAN FD 且 flags 为 0，即不启用 BRS。

## EDL 与 CAN FD padding

CAN FD DLC 只能表示固定容量。设备可能为 EDL=36 的响应发送 48 字节线长，其尾部是 padding。SDK 始终只取 EDL 指定的有效 payload，不把 padding 当作对象内容。

单帧最多容纳 61 字节 HOP payload。长对象由同一个 MI、不同 SI 的片段组成。例如 72 字节 `MI=0x20`：

```text
20 00 3D <61 bytes>
20 3D 0B <11 bytes>
```

`HandProtocolV1.read()` 会按 SI 组合不重叠片段，直到请求区间的每一个字节都已收到。由于 HOP 没有 transaction ID，同一 endpoint 上的所有读写都由协议层串行化，避免上一请求的后续片段被下一请求误收。

## 错误响应

设备错误格式为：

```text
4F <error_index> 01 <error_code>
```

当前确认的错误码：

| 错误码 | 说明 |
| -----: | ---- |
| `0x02` | SI 不存在或对象越界 |
| `0x40` | 写入值非法 |

SDK 会抛出 `HandProtocolDeviceError`，并保留 `.error_index` 和 `.error_code`。主动读取 `MI=0x4F` 时，`4F` 是正常对象响应，不会误判为异常。

## 原始对象 API

每个 `O30i` 实例通过 `hand.protocol` 暴露传输无关客户端：

```python
from linkerbot import O30i

with O30i(interface_type="socketcan", socketcan_channel="can0") as hand:
    # 读取实际值：CTRL 的 RTS=0
    actual_tips = hand.protocol.read(
        main_index=0x01,
        sub_index=0x14,
        length=5,
        timeout_ms=1000,
    )

    # 读取设定值：CTRL 的 RTS=1
    target_tips = hand.protocol.read(
        main_index=0x01,
        sub_index=0x14,
        length=5,
        rts=True,
        timeout_ms=1000,
    )

    print(list(actual_tips), list(target_tips))
```

写入单帧对象切片：

```python
hand.protocol.write(
    main_index=0x01,
    sub_index=0x14,
    payload=b"\x80" * 5,
    timeout_ms=1000,
)
```

单次写 payload 限制为 1～61 字节，且 `SI + length` 不得超过 256。原始 API 不替调用者判断某个固件对象是否安全；位置、速度等常用操作优先使用高层 manager，它会阻止写入预留槽。

## 直接绑定自定义传输

需要复用已有 CAN FD 调度器时，可以直接构造协议层：

```python
from linkerbot.hand.hand_protocol_v1 import HandProtocolV1

client = HandProtocolV1(
    dispatcher,
    request_id=0x001,
    response_id=0x401,
    frame_type=0x04,
)
try:
    protocol_name = client.read(main_index=0x41, sub_index=0x59, length=8)
finally:
    client.close()
```

dispatcher 需要提供 `send`、`subscribe`、`unsubscribe` 和 `stop`；如果还提供 `subscribe_filter`，协议层会在分发前按标准帧响应 ID 过滤。`HandProtocolV1.close()` 只取消自己的订阅，不停止外部 dispatcher。
