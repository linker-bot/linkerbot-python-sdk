# 变更日志

本文件记录 Linkerbot Python SDK 的重要变更。

格式遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号遵循
[语义化版本](https://semver.org/lang/zh-CN/)。合入 `main` 的功能、行为变更和缺陷修复应先写入
`Unreleased`，发布时再移入对应版本。

> 历史范围：以下内容由仓库标签和 `main` 提交记录回溯整理，首个可识别的合入 PR 为 #2。
> `v0.5.1` 是单独的稳定发布分支，因具有用户可见变更而保留；`v0.6.0a1` 至 `v0.6.0a3`
> 位于未合入 `main` 的实验分支，不作为主线发布记录。

## [Unreleased]

### 变更

- 统一灵巧手型号命名：L25 SDK 重命名为 L20，O30i SDK 重命名为 O30；新 API 仅使用 L20 和 O30。

### 新增

- 新增灵巧手原始角度与逻辑角度映射，覆盖 L6、O6、L20Lite 和 L25
  ([#128](https://gitea.linkerhub.work/linker-bot/linkerbot-python-sdk/pulls/128))。
- 新增 CAN FD 通信层及 L30 SDK，包括控制、遥测、事件、版本信息和硬件测试支持
  ([#129](https://gitea.linkerhub.work/linker-bot/linkerbot-python-sdk/pulls/129)、
  [#131](https://gitea.linkerhub.work/linker-bot/linkerbot-python-sdk/pulls/131))。
- 新增 O20 CAN FD 协议层、关节模型、控制与传感器 API
  ([#134](https://gitea.linkerhub.work/linker-bot/linkerbot-python-sdk/pulls/134))。
- 新增 A7 V2 机械臂、运动学模型和左右臂 URDF
  ([#140](https://gitea.linkerhub.work/linker-bot/linkerbot-python-sdk/pulls/140))。
- CAN FD 后端新增基于 `python-can` 的 SocketCAN 支持，L30 和 O20 可直接使用 Linux CAN
  接口 ([#147](https://gitea.linkerhub.work/linker-bot/linkerbot-python-sdk/pulls/147))。
- 新增基于 Hand Object Protocol 的 20 关节 O30i SDK，提供控制、诊断、传感器、文档及默认只读的
  实物诊断示例 ([#149](https://gitea.linkerhub.work/linker-bot/linkerbot-python-sdk/pulls/149))。
- 新增 L30 SocketCAN 全功能实物诊断示例；默认只读，只有显式传入 `--move` 才会执行低幅度运动
  ([#150](https://gitea.linkerhub.work/linker-bot/linkerbot-python-sdk/pulls/150))。

### 变更

- 顶层、机械臂和灵巧手包改用 PEP 562 延迟导入，未安装可选机械臂依赖时不再影响灵巧手导入
  ([#136](https://gitea.linkerhub.work/linker-bot/linkerbot-python-sdk/pulls/136))。
- 新增 `just test` 和 `just check`，统一本地与 CI 的格式、lint、类型及测试命令，并补充缺失的
  pytest marker 注册
  ([#150](https://gitea.linkerhub.work/linker-bot/linkerbot-python-sdk/pulls/150))。
- 运行时与开发依赖升级到当前稳定版本，包括 Pydantic 2.13、pytest 9.1、Ruff 0.15.21 和 Ty
  0.0.58；本地与 CI 使用同一锁文件
  ([#150](https://gitea.linkerhub.work/linker-bot/linkerbot-python-sdk/pulls/150))。

### 修复

- 修复经典手型快速响应丢失与 polling 请求状态竞争，移除五指触觉轮询固定发送间隔，并使
  CAN FD 后台物理发送失败可由 O20/L30 调用方观测
  ([#175](https://gitea.linkerhub.work/linker-bot/linkerbot-python-sdk/pulls/175))。
- CAN FD 通用默认帧改为不启用 BRS，并缓存厂商动态库句柄、隔离硬件测试配置路径
  ([#175](https://gitea.linkerhub.work/linker-bot/linkerbot-python-sdk/pulls/175))。
- 修复 O30i 百分比角度方向与实物语义相反的问题：`0%` 为张开端、`100%` 为闭合端；原始值 API 保持设备协议方向
  ([#150](https://gitea.linkerhub.work/linker-bot/linkerbot-python-sdk/pulls/150))。
- 统一管理厂商 CAN FD 动态库的初始化与退出生命周期，避免重复初始化和提前释放
  ([#142](https://gitea.linkerhub.work/linker-bot/linkerbot-python-sdk/pulls/142))。
- 修复 O20 协议、关节数据与运行时行为，并补充回归测试
  ([#144](https://gitea.linkerhub.work/linker-bot/linkerbot-python-sdk/pulls/144))。
- 修复 classic CAN/CAN FD 的忙等待、错误退避、并发关闭、厂商库生命周期、返回帧计数与
  SocketCAN 零超时读取问题
  ([#150](https://gitea.linkerhub.work/linker-bot/linkerbot-python-sdk/pulls/150))。
- 修复 L30、O20 和 HOP 客户端的关闭竞态、广播端点过滤、非有限超时/轮询间隔，以及 L30Bus
  构造期总线错误清理
  ([#150](https://gitea.linkerhub.work/linker-bot/linkerbot-python-sdk/pulls/150))。
- 修复 `IterableQueue` 忽略超时及关闭时生产者阻塞，并防止旧的 `MotionTimer` 回调提前结束新运动
  ([#150](https://gitea.linkerhub.work/linker-bot/linkerbot-python-sdk/pulls/150))。

### 文档

- 新增 O20 CAN FD 的完整中文参考文档
  ([#146](https://gitea.linkerhub.work/linker-bot/linkerbot-python-sdk/pulls/146))。
- 建立覆盖首个可识别 PR 至当前主线的变更日志、PR 模板和主分支 changelog 检查
  ([#150](https://gitea.linkerhub.work/linker-bot/linkerbot-python-sdk/pulls/150))。

## [0.5.4] - 2026-05-10

### 新增

- CAN 通信对象可查询当前接口信息
  ([#117](https://gitea.linkerhub.work/linker-bot/linkerbot-python-sdk/pulls/117))。
- `ArmKinetix` 新增 `side` 属性，便于调用方识别左右臂
  ([#122](https://gitea.linkerhub.work/linker-bot/linkerbot-python-sdk/pulls/122))。

## [0.5.3] - 2026-04-10

### 变更

- Python 发行包名称由 `linkerbot-py` 改为 `linkerbot`。

## [0.5.1] - 2026-04-10

### 变更

- 为即将移除或替换的 API 增加弃用警告。此版本从 `release/0.5` 发布，不属于后续 `main`
  的祖先提交。

## [0.5.0] - 2026-04-09

### 变更

- **破坏性变更：** `ArmKinetix` 接受任意 URDF 路径，调用方不再受内置模型路径限制
  ([#110](https://gitea.linkerhub.work/linker-bot/linkerbot-python-sdk/pulls/110))。

### 文档

- 增加同时使用多个 CAN 接口的配置示例
  ([#107](https://gitea.linkerhub.work/linker-bot/linkerbot-python-sdk/pulls/107))。

## [0.4.2] - 2026-03-18

### 变更

- 将机械臂运动学依赖改为可选安装项，纯灵巧手用户无需安装 Pinocchio
  ([#104](https://gitea.linkerhub.work/linker-bot/linkerbot-python-sdk/pulls/104))。

## [0.4.1] - 2026-03-18

### 修复

- 读取各手指力传感器时增加 MCU 所需等待，降低连续请求丢帧概率
  ([#98](https://gitea.linkerhub.work/linker-bot/linkerbot-python-sdk/pulls/98))。
- L6 的阻塞式全手力传感器读取改为串行请求，避免并行响应相互干扰
  ([#101](https://gitea.linkerhub.work/linker-bot/linkerbot-python-sdk/pulls/101))。

### 测试

- 补全 L20Lite 和 L25 的后台传感器轮询测试
  ([#102](https://gitea.linkerhub.work/linker-bot/linkerbot-python-sdk/pulls/102))。

## [0.4.0] - 2026-03-16

### 变更

- **破坏性变更：** 传感器轮询支持按传感器分别设置周期，替代共享周期配置
  ([#93](https://gitea.linkerhub.work/linker-bot/linkerbot-python-sdk/pulls/93))。
- 优化机械臂运动学算法性能
  ([#91](https://gitea.linkerhub.work/linker-bot/linkerbot-python-sdk/pulls/91))。

### 修复

- 修正 A7 读取速度环积分增益 `VELOCITY_KI` 时使用的命令
  ([#95](https://gitea.linkerhub.work/linker-bot/linkerbot-python-sdk/pulls/95))。

### 移除

- **破坏性变更：** 移除尚未稳定的 O7 脚本、SDK 入口和文档
  ([#89](https://gitea.linkerhub.work/linker-bot/linkerbot-python-sdk/pulls/89))。

### 测试

- 重构 L6、L20Lite、L25 和 O6 测试，扩大控制、传感器与生命周期覆盖
  ([#96](https://gitea.linkerhub.work/linker-bot/linkerbot-python-sdk/pulls/96))。

## [0.3.4] - 2026-03-09

### 修复

- 修正 L25 版本和序列号响应所使用的 CAN 帧 ID。

## [0.3.3] - 2026-03-09

### 新增

- 新增 A7 与 A7 Lite 机械臂 SDK，包括配置、状态、运动控制和运动学接口
  ([#81](https://gitea.linkerhub.work/linker-bot/linkerbot-python-sdk/pulls/81))。

### 修复

- 消除包初始化期间的循环导入。

## [0.2.2] - 2026-03-04

### 修复

- CAN 调度器遇到后台错误时会主动退出并向调用方传播错误，避免线程静默失效
  ([#75](https://gitea.linkerhub.work/linker-bot/linkerbot-python-sdk/pulls/75))。

## [0.2.1] - 2026-03-04

### 变更

- PyPI 发行包名称改为 `linkerbot-py`，并同步安装说明。

### 修复

- O6 连续读取多个力传感器时增加请求间隔，以适配 MCU 处理速度
  ([#66](https://gitea.linkerhub.work/linker-bot/linkerbot-python-sdk/pulls/66))。

### 文档与测试

- 增加文档自动发布流程
  ([#64](https://gitea.linkerhub.work/linker-bot/linkerbot-python-sdk/pulls/64))。
- 增加 L20Lite 安全动作测试，防止弯曲食指夹住拇指
  ([#69](https://gitea.linkerhub.work/linker-bot/linkerbot-python-sdk/pulls/69))。
- 增加灵巧手张开与闭合示例
  ([#72](https://gitea.linkerhub.work/linker-bot/linkerbot-python-sdk/pulls/72))。

## [0.2.0] - 2026-02-15

### 新增

- 初步支持 O7、L20Lite 和 L25 灵巧手
  ([#60](https://gitea.linkerhub.work/linker-bot/linkerbot-python-sdk/pulls/60))。
- 建立 SDK 文档站点及基础使用文档
  ([#63](https://gitea.linkerhub.work/linker-bot/linkerbot-python-sdk/pulls/63))。

### 变更

- 重构 CAN 数据中继，改善订阅者等待与数据分发行为
  ([#56](https://gitea.linkerhub.work/linker-bot/linkerbot-python-sdk/pulls/56))。

## [0.1.1a3] - 2026-02-10

### 变更

- **破坏性变更：** 重新设计 L6 与 O6 的公共 API、管理器和数据模型
  ([#53](https://gitea.linkerhub.work/linker-bot/linkerbot-python-sdk/pulls/53))。

## [0.1.1a2] - 2026-02-05

### 变更

- 将最低 Python 版本调整为 3.10
  ([#51](https://gitea.linkerhub.work/linker-bot/linkerbot-python-sdk/pulls/51))。

## [0.1.1a1] - 2026-02-04

### 新增

- 建立 SDK、异常体系、CAN 消息调度与订阅机制，并实现首个 L6 角度控制接口。
- L6 新增扭矩与速度管理器
  ([#2](https://gitea.linkerhub.work/linker-bot/linkerbot-python-sdk/pulls/2)、
  [#3](https://gitea.linkerhub.work/linker-bot/linkerbot-python-sdk/pulls/3))。
- L6 新增温度、电流、故障管理器，并完成故障信息和整手功能
  ([#14](https://gitea.linkerhub.work/linker-bot/linkerbot-python-sdk/pulls/14)、
  [#30](https://gitea.linkerhub.work/linker-bot/linkerbot-python-sdk/pulls/30)、
  [#34](https://gitea.linkerhub.work/linker-bot/linkerbot-python-sdk/pulls/34))。
- O6 新增角度、扭矩、速度、温度等管理器及完整设备入口
  ([#13](https://gitea.linkerhub.work/linker-bot/linkerbot-python-sdk/pulls/13)、
  [#37](https://gitea.linkerhub.work/linker-bot/linkerbot-python-sdk/pulls/37))。
- 力传感器支持整手多帧采集、可迭代数据队列和 `uint8` 矩阵
  ([#4](https://gitea.linkerhub.work/linker-bot/linkerbot-python-sdk/pulls/4)、
  [#6](https://gitea.linkerhub.work/linker-bot/linkerbot-python-sdk/pulls/6)、
  [#32](https://gitea.linkerhub.work/linker-bot/linkerbot-python-sdk/pulls/32))。
- 增加 L6/O6 测试、中文文档和打包发布流水线
  ([#39](https://gitea.linkerhub.work/linker-bot/linkerbot-python-sdk/pulls/39)、
  [#46](https://gitea.linkerhub.work/linker-bot/linkerbot-python-sdk/pulls/46)、
  [#47](https://gitea.linkerhub.work/linker-bot/linkerbot-python-sdk/pulls/47))。

### 变更

- L6/O6 的角度、扭矩、速度、温度和电流读取统一返回结构化数据
  ([#19](https://gitea.linkerhub.work/linker-bot/linkerbot-python-sdk/pulls/19)、
  [#21](https://gitea.linkerhub.work/linker-bot/linkerbot-python-sdk/pulls/21)、
  [#25](https://gitea.linkerhub.work/linker-bot/linkerbot-python-sdk/pulls/25))。
- 控制 API 接受 `list[int]`，减少调用方手动转换
  ([#41](https://gitea.linkerhub.work/linker-bot/linkerbot-python-sdk/pulls/41))。
- 移除未完成的速度控制代码并修正参数类型
  ([#9](https://gitea.linkerhub.work/linker-bot/linkerbot-python-sdk/pulls/9))。
- Python 模块由 `linkerhand` 更名为 `linkerbot`
  ([#43](https://gitea.linkerhub.work/linker-bot/linkerbot-python-sdk/pulls/43))。
- 清理 L6 文档并修正 `just` 发布命令的远端选择
  ([#26](https://gitea.linkerhub.work/linker-bot/linkerbot-python-sdk/pulls/26)、
  [#49](https://gitea.linkerhub.work/linker-bot/linkerbot-python-sdk/pulls/49))。

### 修复

- 修正力传感器响应索引
  ([#5](https://gitea.linkerhub.work/linker-bot/linkerbot-python-sdk/pulls/5))。
- 修复 `IterableQueue.close()` 在队列满时可能永久阻塞的问题
  ([#15](https://gitea.linkerhub.work/linker-bot/linkerbot-python-sdk/pulls/15))。
- 设置 L6 限位补偿前先验证密码
  ([#38](https://gitea.linkerhub.work/linker-bot/linkerbot-python-sdk/pulls/38))。

[Unreleased]: https://gitea.linkerhub.work/linker-bot/linkerbot-python-sdk/compare/v0.5.4...main
[0.5.4]: https://gitea.linkerhub.work/linker-bot/linkerbot-python-sdk/compare/v0.5.3...v0.5.4
[0.5.3]: https://gitea.linkerhub.work/linker-bot/linkerbot-python-sdk/compare/v0.5.0...v0.5.3
[0.5.1]: https://gitea.linkerhub.work/linker-bot/linkerbot-python-sdk/compare/v0.5.0...v0.5.1
[0.5.0]: https://gitea.linkerhub.work/linker-bot/linkerbot-python-sdk/compare/v0.4.2...v0.5.0
[0.4.2]: https://gitea.linkerhub.work/linker-bot/linkerbot-python-sdk/compare/v0.4.1...v0.4.2
[0.4.1]: https://gitea.linkerhub.work/linker-bot/linkerbot-python-sdk/compare/v0.4.0...v0.4.1
[0.4.0]: https://gitea.linkerhub.work/linker-bot/linkerbot-python-sdk/compare/v0.3.4...v0.4.0
[0.3.4]: https://gitea.linkerhub.work/linker-bot/linkerbot-python-sdk/compare/v0.3.3...v0.3.4
[0.3.3]: https://gitea.linkerhub.work/linker-bot/linkerbot-python-sdk/compare/v0.2.2...v0.3.3
[0.2.2]: https://gitea.linkerhub.work/linker-bot/linkerbot-python-sdk/compare/v0.2.1...v0.2.2
[0.2.1]: https://gitea.linkerhub.work/linker-bot/linkerbot-python-sdk/compare/v0.2.0...v0.2.1
[0.2.0]: https://gitea.linkerhub.work/linker-bot/linkerbot-python-sdk/compare/v0.1.1a3...v0.2.0
[0.1.1a3]: https://gitea.linkerhub.work/linker-bot/linkerbot-python-sdk/compare/v0.1.1a2...v0.1.1a3
[0.1.1a2]: https://gitea.linkerhub.work/linker-bot/linkerbot-python-sdk/compare/v0.1.1a1...v0.1.1a2
[0.1.1a1]: https://gitea.linkerhub.work/linker-bot/linkerbot-python-sdk/releases/tag/v0.1.1a1
