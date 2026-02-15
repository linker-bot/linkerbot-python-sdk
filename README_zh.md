# Linkerbot Python SDK

Linkerbot 灵巧手纯 Python SDK。

> **注意：** 本项目正在快速迭代中，API 可能会在版本间发生变化。

## 安装

目前仅支持从 Git 仓库安装：

```bash
# pip
pip install git+https://github.com/linker-bot/linkerbot-python-sdk.git

# uv
uv add "linkerbot @ git+https://github.com/linker-bot/linkerbot-python-sdk"
```

## 快速开始

```python
from linkerbot import L6

with L6(side="left", interface_name="can0") as hand:
    # 张开手掌
    hand.angle.set_angles([0, 0, 0, 0, 0, 0])

    # 握拳
    hand.angle.set_angles([100, 50, 100, 100, 100, 100])

    # 读取角度
    data = hand.angle.get_blocking(timeout_ms=100)
    print(f"当前角度：{data.angles.to_list()}")
```

更多用法请参阅[完整文档](docs/zh/src/SUMMARY.md)。
