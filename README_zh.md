# Linkerbot Python SDK

Linkerbot 灵巧手纯 Python SDK。

> **注意：** 本项目正在快速迭代中，API 可能会在版本间发生变化。

## 安装

从 PyPI 安装：

```bash
# pip
pip install linkerbot-py

# uv
uv add linkerbot-py
```

从 Git 仓库安装：

```bash
# pip
pip install git+https://github.com/linker-bot/linkerbot-python-sdk.git

# uv
uv add "linkerbot-py @ git+https://github.com/linker-bot/linkerbot-python-sdk"
```

### 机械臂用户

机械臂（A7 / A7 Lite）依赖 Pinocchio 进行运动学计算，需要额外安装 `kinetix`：

```bash
# pip
pip install linkerbot-py[kinetix]

# uv
uv add linkerbot-py --extra kinetix
```

> **Windows 用户**：Pinocchio 不支持 pip 安装，请使用 `conda install pinocchio -c conda-forge`。

## 快速开始

```python
from linkerbot import L6

with L6(side="left", interface_name="can0") as hand:
    # 握拳
    hand.angle.set_angles([0, 0, 0, 0, 0, 0])

    # 张开
    hand.angle.set_angles([100, 50, 100, 100, 100, 100])

    # 读取角度
    data = hand.angle.get_blocking(timeout_ms=100)
    print(f"当前角度：{data.angles.to_list()}")
```

更多用法请参阅[完整文档](https://docs.linkerhub.work/sdk/zh-cn/)。
