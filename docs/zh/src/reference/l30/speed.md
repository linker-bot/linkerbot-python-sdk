# 速度控制

通过 `hand.speed` 设置和读取 L30 的 17 个关节速度。

- **数量**：17 个关节，顺序为 `J1` 到 `J17`
- **范围**：1-250

## 设置每个关节速度

```python
from linkerbot import L30

with L30() as hand:
    hand.speed.set_speeds([50] * 17)
```

## 设置所有关节相同速度

```python
from linkerbot import L30

with L30() as hand:
    hand.speed.set_all(50)
```

## 阻塞读取速度

```python
from linkerbot import L30

with L30() as hand:
    data = hand.speed.get_blocking(timeout_ms=1000)
    print(data.speeds)
```

## 缓存读取

```python
from linkerbot import L30

with L30() as hand:
    hand.speed.get_blocking(timeout_ms=1000)
    data = hand.speed.get_snapshot()
    if data is not None:
        print(data.speeds)
```

## 完整示例

```python
from linkerbot import L30

with L30() as hand:
    hand.speed.set_all(50)
    data = hand.speed.get_blocking(timeout_ms=1000)
    print("当前速度：", data.speeds)
```
