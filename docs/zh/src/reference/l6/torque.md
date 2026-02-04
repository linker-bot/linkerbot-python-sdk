# 扭矩控制

## 概述

通过 `hand.torque` 访问扭矩控制功能，支持设置目标扭矩和读取当前扭矩。

扭矩值范围为 **0-100**（无量纲，表示关节电机的相对扭矩百分比），对应 L6 灵巧手的 6 个关节电机：

| 索引 | 属性 | 关节电机 |
|------|------|------|
| 0 | `thumb_flex` | 拇指弯曲 |
| 1 | `thumb_abd` | 拇指外展 |
| 2 | `index` | 食指 |
| 3 | `middle` | 中指 |
| 4 | `ring` | 无名指 |
| 5 | `pinky` | 小指 |

## 设置扭矩

```python
# 使用列表
hand.torque.set_torques([50.0, 30.0, 60.0, 60.0, 60.0, 60.0])

# 使用 L6Torque 对象
from linkerbot.hand.l6 import L6Torque

target = L6Torque(
    thumb_flex=50.0,
    thumb_abd=30.0,
    index=60.0,
    middle=60.0,
    ring=60.0,
    pinky=60.0
)
hand.torque.set_torques(target)
```

## 读取扭矩

### 阻塞读取

发送请求并等待响应：

```python
from linkerbot.exceptions import TimeoutError

try:
    data = hand.torque.get_torques_blocking(timeout_ms=500)
    print(f"拇指弯曲：{data.torques.thumb_flex}")
    print(f"食指：{data.torques.index}")
except TimeoutError:
    print("读取超时")
```

### 缓存读取

获取最近一次的缓存数据（非阻塞）：

```python
data = hand.torque.get_current_torques()
if data:
    print(f"扭矩：{data.torques.to_list()}")
```

## 流式读取

周期性获取扭矩数据。

**参数**：
- `interval_ms`：轮询间隔（毫秒）
- `maxsize`：队列大小

```python
q = hand.torque.stream(interval_ms=50, maxsize=10)

try:
    for data in q:
        print(f"扭矩：{data.torques.to_list()}")
        if should_stop:
            break
finally:
    hand.torque.stop_streaming()
```

## 示例

### 完整控制流程

```python
from linkerbot import L6
from linkerbot.hand.l6 import L6Torque

hand = L6()

# 设置扭矩
hand.torque.set_torques([50.0, 30.0, 60.0, 60.0, 60.0, 60.0])

# 阻塞读取当前扭矩
data = hand.torque.get_torques_blocking(timeout_ms=200)
print(f"当前扭矩：{data.torques.to_list()}")
```

### 实时监控

```python
from linkerbot import L6

hand = L6()
q = hand.torque.stream(interval_ms=100, maxsize=10)

try:
    for data in q:
        # 检测扭矩变化
        if data.torques.index > 80:
            print("食指关节电机扭矩过高")
            break
finally:
    hand.torque.stop_streaming()
```
