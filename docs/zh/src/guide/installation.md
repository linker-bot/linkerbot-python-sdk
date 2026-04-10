# 安装

从 PyPI 安装：

```bash
# pip
pip install linkerbot

# uv
uv add linkerbot
```

从 Git 仓库安装：

```bash
# pip
pip install git+https://github.com/linker-bot/linkerbot-python-sdk.git

# uv
uv add "linkerbot @ git+https://github.com/linker-bot/linkerbot-python-sdk"
```

## 可选依赖

### Kinetix（运动学，机械臂必需）

机械臂（A7 / A7 Lite）依赖 [Pinocchio](https://github.com/stack-of-tasks/pinocchio) 进行运动学计算，需要额外安装：

```bash
# pip (Linux / macOS)
pip install linkerbot[kinetix]

# uv
uv add linkerbot --extra kinetix
```

> **Windows 用户注意**：Pinocchio 不支持在 Windows 上通过 pip 安装。请使用 Conda：
>
> ```bash
> conda install pinocchio -c conda-forge
> ```

如果只使用灵巧手（L6 / L20 Lite / L25 等），无需安装此依赖。
