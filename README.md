# Linkerbot Python SDK

Pure Python SDK for [Linkerbot](https://linkerbot.cn) dexterous hands.

> **Note:** This project is under active development. APIs may change between versions.

[中文文档](README_zh.md)

## Installation

```bash
pip install linkerbot-py
```

### Arm users

Arms (A7 / A7 Lite) require Pinocchio for kinematics. Install the `kinetix` extra:

```bash
pip install linkerbot-py[kinetix]
```

> **Windows users:** Pinocchio does not support pip on Windows. Use `conda install pinocchio -c conda-forge` instead.
