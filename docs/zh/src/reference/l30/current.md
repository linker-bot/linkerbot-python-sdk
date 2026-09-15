# 电流读取

通过 `hand.current` 读取 L30 的 17 个关节电流数据。

## 阻塞读取

```python
from linkerbot import L30

with L30() as hand:
    data = hand.current.get_blocking(timeout_ms=1000)
    print(data.currents)
```

## 缓存读取

```python
from linkerbot import L30

with L30() as hand:
    hand.current.get_blocking(timeout_ms=1000)
    data = hand.current.get_snapshot()
    if data is not None:
        print(data.currents)
```

## 完整示例

```python
from linkerbot import L30

with L30() as hand:
    current = hand.current.get_blocking(timeout_ms=1000)
    print("电流：", current.currents)
```
