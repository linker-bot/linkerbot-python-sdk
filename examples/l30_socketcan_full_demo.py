"""L30 通过 python-can SocketCAN 使用全部高层功能的完整示例。

准备 SocketCAN FD（默认 1 Mbit/s 仲裁、5 Mbit/s 数据段）：

    sudo ip link set can0 down
    sudo ip link set can0 type can \
      bitrate 1000000 sample-point 0.800 \
      dbitrate 5000000 dsample-point 0.750 fd on
    sudo ip link set can0 up

运行完整的只读诊断、周期上报、轮询和事件流示例：

    uv run python examples/l30_socketcan_full_demo.py --channel can0

允许 SDK 自动配置链路（需要 CAP_NET_ADMIN，并会影响共享该链路的进程）：

    sudo -E uv run python examples/l30_socketcan_full_demo.py \
        --channel can0 --auto-reconfigure

显式允许低幅度运动后，示例还会覆盖使能/失能、百分比角度、原始角度、
逐关节/全关节速度以及逐关节/全关节力矩命令：

    uv run python examples/l30_socketcan_full_demo.py --channel can0 --move

默认不会使能电机或下发运动目标。触觉读取默认开启，可用 ``--skip-tactile``
跳过；触觉后台轮询开销较大，只有传入 ``--poll-tactile`` 才会启用。
主机发送默认使用 ``frame_type=0x04``（CAN FD、无 BRS）；确认适配器的
BRS 发送路径稳定后，可传 ``--frame-type 0x0C`` 显式启用 BRS。
"""

from __future__ import annotations

import argparse
import sys
import threading
import time
from collections.abc import Callable, Sequence

from linkerbot.exceptions import LinkerbotError
from linkerbot.hand.l30 import (
    L30,
    L30_JOINT_COUNT,
    L30_JOINT_SPECS,
    AngleEvent,
    CurrentEvent,
    FaultEvent,
    Finger,
    ForceSensorEvent,
    L30Angle,
    ReportSource,
    SensorEvent,
    SensorSource,
    SpeedEvent,
    TemperatureEvent,
    TorqueEvent,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="L30 SocketCAN FD 全功能示例（默认不执行运动）"
    )
    parser.add_argument("--channel", default="can0", help="SocketCAN 接口名")
    parser.add_argument("--node-id", type=_auto_int, default=1)
    parser.add_argument("--host-id", type=_auto_int, default=0)
    parser.add_argument("--bitrate", type=int, default=1_000_000)
    parser.add_argument("--data-bitrate", type=int, default=5_000_000)
    parser.add_argument(
        "--frame-type",
        type=_auto_int,
        default=0x04,
        help="发送帧类型：0x04=CAN FD 无 BRS（默认），0x0C=CAN FD+BRS",
    )
    parser.add_argument(
        "--auto-reconfigure",
        action="store_true",
        help="由 SDK 执行 ip link 配置；需要 CAP_NET_ADMIN",
    )
    parser.add_argument("--timeout-ms", type=float, default=1000.0)
    parser.add_argument(
        "--stream-seconds",
        type=float,
        default=2.0,
        help="设备周期上报和主机轮询各自运行的时间",
    )
    parser.add_argument("--period-ms", type=int, default=100)
    parser.add_argument("--max-printed-events", type=int, default=20)
    parser.add_argument("--skip-tactile", action="store_true")
    parser.add_argument(
        "--poll-tactile",
        action="store_true",
        help="后台轮询五指触觉；总线开销较大",
    )
    parser.add_argument(
        "--move",
        action="store_true",
        help="显式允许使能电机并执行低幅度运动",
    )
    parser.add_argument("--target-percent", type=float, default=10.0)
    parser.add_argument("--move-seconds", type=float, default=1.0)
    parser.add_argument("--speed", type=int, default=50)
    parser.add_argument("--torque", type=int, default=100)
    parser.add_argument(
        "--strict",
        action="store_true",
        help="任一可选功能失败时立即退出；默认打印错误后继续",
    )
    return parser.parse_args()


def run() -> None:
    args = parse_args()
    _validate_args(args)

    print(
        f"[L30] 连接 {args.channel}: node_id={args.node_id}, "
        f"host_id={args.host_id}, bitrate={args.bitrate}, "
        f"data_bitrate={args.data_bitrate}, frame_type=0x{args.frame_type:02X}"
    )
    with L30(
        node_id=args.node_id,
        host_id=args.host_id,
        interface_type="socketcan",
        channel=args.channel,
        bitrate=args.bitrate,
        data_bitrate=args.data_bitrate,
        frame_type=args.frame_type,
        auto_reconfigure=args.auto_reconfigure,
        auto_start_periodic=False,
    ) as hand:
        print(
            f"[L30] 已连接：node_id={hand.node_id}, host_id={hand.host_id}, "
            f"closed={hand.is_closed()}"
        )
        consumer, event_counts = _start_event_consumer(
            hand, print_limit=args.max_printed_events
        )
        try:
            _step(
                "读取完整 DeviceInfo",
                lambda: _show_device_info(hand, args.timeout_ms),
                strict=args.strict,
            )
            _step(
                "分别读取产品编码、NodeID 和左右手",
                lambda: _show_identity_fields(hand, args.timeout_ms),
                strict=args.strict,
            )
            _step(
                "阻塞读取角度",
                lambda: _show_angle(hand, args.timeout_ms),
                strict=args.strict,
            )
            _step(
                "阻塞读取速度",
                lambda: _show_speed(hand, args.timeout_ms),
                strict=args.strict,
            )
            _step(
                "阻塞读取电流",
                lambda: _show_current(hand, args.timeout_ms),
                strict=args.strict,
            )
            _step(
                "阻塞读取温度",
                lambda: _show_temperature(hand, args.timeout_ms),
                strict=args.strict,
            )
            _step(
                "阻塞读取并解析故障",
                lambda: _show_faults(hand, args.timeout_ms),
                strict=args.strict,
            )
            if not args.skip_tactile:
                _step(
                    "读取单指与五指触觉矩阵",
                    lambda: _show_tactile(hand, args.timeout_ms),
                    strict=args.strict,
                )
            _step(
                "设备端周期上报（默认和自定义来源）",
                lambda: _device_periodic_reports(
                    hand,
                    duration_s=args.stream_seconds,
                    period_ms=args.period_ms,
                    timeout_ms=args.timeout_ms,
                ),
                strict=args.strict,
            )
            _step(
                "主机轮询所有传感器来源",
                lambda: _host_polling(
                    hand,
                    duration_s=args.stream_seconds,
                    include_tactile=args.poll_tactile,
                ),
                strict=args.strict,
            )
            if args.move:
                _step(
                    "使能并执行低幅度运动",
                    lambda: _motion_demo(
                        hand,
                        timeout_ms=args.timeout_ms,
                        target_percent=args.target_percent,
                        hold_s=args.move_seconds,
                        speed=args.speed,
                        torque=args.torque,
                    ),
                    strict=True,
                )
            else:
                print("\n[L30] 未传 --move：跳过使能及所有运动命令")

            _show_snapshots(hand)
        finally:
            hand.stop_polling()
            hand.stop_stream()
            consumer.join(timeout=2.0)

        print(f"\n[L30] 事件计数：{event_counts}")

    print(f"[L30] context manager 已释放资源，closed={hand.is_closed()}")


def _show_device_info(hand: L30, timeout_ms: float) -> None:
    info = hand.version.get_device_info(timeout_ms=timeout_ms)
    print(
        "  model/product_id=",
        info.product_id,
        " serial=",
        info.serial_number,
        " software=",
        info.software_version,
        " hardware=",
        info.hardware_version,
        " structure=",
        info.structure_version,
        " side=",
        info.hand_side.value,
        " sensor=",
        info.sensor_type,
        " origin=",
        info.origin,
        sep="",
    )


def _show_identity_fields(hand: L30, timeout_ms: float) -> None:
    print("  product_code:", hand.version.get_product_code(timeout_ms=timeout_ms))
    print("  device node_id:", hand.version.get_node_id(timeout_ms=timeout_ms))
    print("  hand side:", hand.version.get_hand_side(timeout_ms=timeout_ms).value)


def _show_angle(hand: L30, timeout_ms: float) -> None:
    data = hand.angle.get_blocking(timeout_ms=timeout_ms)
    print("  percentage[:6]:", _head(data.angles.to_list(), 6))
    print("  raw[:6]:", _head(data.angles.to_raw(), 6))


def _show_speed(hand: L30, timeout_ms: float) -> None:
    data = hand.speed.get_blocking(timeout_ms=timeout_ms)
    print("  speeds[:6]:", _head(data.speeds, 6))


def _show_current(hand: L30, timeout_ms: float) -> None:
    data = hand.current.get_blocking(timeout_ms=timeout_ms)
    print("  currents[:6]:", _head(data.currents, 6))


def _show_temperature(hand: L30, timeout_ms: float) -> None:
    data = hand.temperature.get_blocking(timeout_ms=timeout_ms)
    print("  temperatures[:6]:", _head(data.temperatures, 6))


def _show_faults(hand: L30, timeout_ms: float) -> None:
    data = hand.fault.get_blocking(timeout_ms=timeout_ms)
    print("  raw fault bytes:", list(data.faults))
    for index in range(L30_JOINT_COUNT):
        flags = {
            "voltage": data.has_voltage_fault(index),
            "encoder": data.has_magnetic_encoder_fault(index),
            "temperature": data.has_temperature_fault(index),
            "current": data.has_current_fault(index),
            "load": data.has_load_fault(index),
        }
        active = [name for name, enabled in flags.items() if enabled]
        if active:
            print(f"  J{index + 1}: {', '.join(active)}")


def _show_tactile(hand: L30, timeout_ms: float) -> None:
    finger = hand.force_sensor.get_finger(Finger.THUMB, timeout_ms=timeout_ms)
    print(
        f"  {finger.finger.value}: shape={finger.values.shape}, "
        f"min={int(finger.values.min())}, max={int(finger.values.max())}"
    )
    all_fingers = hand.force_sensor.get_blocking(timeout_ms=timeout_ms)
    for name in ("thumb", "index", "middle", "ring", "pinky"):
        values = getattr(all_fingers, name)
        print(
            f"  {name}: shape={values.shape}, mean={float(values.mean()):.1f}, "
            f"max={int(values.max())}"
        )


def _device_periodic_reports(
    hand: L30, *, duration_s: float, period_ms: int, timeout_ms: float
) -> None:
    # 高层快捷 API：内部调用 report.start_default()/disable_all()。
    hand.start_periodic_reports(timeout_ms=timeout_ms)
    time.sleep(duration_s / 2)
    hand.stop_periodic_reports(timeout_ms=timeout_ms)

    # 直接 manager API：为五种设备端上报来源逐一配置。
    try:
        for source in ReportSource:
            hand.report.configure(
                source,
                enabled=True,
                period_ms=period_ms,
                timeout_ms=timeout_ms,
            )
        time.sleep(duration_s / 2)
        hand.report.disable(ReportSource.FAULT, timeout_ms=timeout_ms)
    finally:
        hand.report.disable_all(timeout_ms=timeout_ms)


def _host_polling(hand: L30, *, duration_s: float, include_tactile: bool) -> None:
    intervals = {
        SensorSource.ANGLE: 0.10,
        SensorSource.SPEED: 0.20,
        SensorSource.CURRENT: 0.20,
        SensorSource.TEMPERATURE: 0.50,
        SensorSource.FAULT: 0.50,
    }
    if include_tactile:
        intervals[SensorSource.FORCE_SENSOR] = 2.0
    hand.start_polling(intervals)
    try:
        time.sleep(duration_s)
    finally:
        hand.stop_polling()


def _motion_demo(
    hand: L30,
    *,
    timeout_ms: float,
    target_percent: float,
    hold_s: float,
    speed: int,
    torque: int,
) -> None:
    neutral = _neutral_target()
    target = [
        target_percent if spec.minimum >= 0 else neutral[index]
        for index, spec in enumerate(L30_JOINT_SPECS)
    ]
    target_model = L30Angle.from_list(target)
    enabled = False
    try:
        hand.control.enable(timeout_ms=timeout_ms)
        enabled = True

        # 同时展示全关节快捷设置和逐关节向量设置。
        hand.speed.set_all(speed)
        hand.speed.set_speeds([speed] * L30_JOINT_COUNT)
        hand.torque.set_all(torque)
        hand.torque.set_torques([torque] * L30_JOINT_COUNT)

        hand.angle.set_angles(neutral)  # list[float] 百分比接口
        time.sleep(0.3)
        hand.angle.set_angles(target_model)  # L30Angle 值对象接口
        time.sleep(hold_s)
        hand.angle.set_raw_angles(target_model.to_raw())  # 原始整数接口
        time.sleep(0.2)
        _show_angle(hand, timeout_ms)
    finally:
        if enabled:
            try:
                hand.angle.set_raw_angles(L30Angle.from_list(neutral).to_raw())
                time.sleep(0.3)
            finally:
                hand.control.disable(timeout_ms=timeout_ms)


def _show_snapshots(hand: L30) -> None:
    snapshot = hand.get_snapshot()
    manager_snapshots = {
        "angle": hand.angle.get_snapshot(),
        "speed": hand.speed.get_snapshot(),
        "torque": hand.torque.get_snapshot(),
        "current": hand.current.get_snapshot(),
        "temperature": hand.temperature.get_snapshot(),
        "fault": hand.fault.get_snapshot(),
        "force_sensor": hand.force_sensor.get_snapshot(),
    }
    print("\n[L30] manager snapshot 是否就绪：")
    print(" ", {name: value is not None for name, value in manager_snapshots.items()})
    print("[L30] aggregate snapshot timestamp:", snapshot.timestamp)


def _start_event_consumer(
    hand: L30, *, print_limit: int
) -> tuple[threading.Thread, dict[str, int]]:
    stream = hand.stream(maxsize=512)
    counts: dict[str, int] = {}

    def consume() -> None:
        printed = 0
        for event in stream:
            name = type(event).__name__
            counts[name] = counts.get(name, 0) + 1
            if printed < print_limit:
                print(f"  [event] {_describe_event(event)}")
                printed += 1

    thread = threading.Thread(target=consume, name="L30EventConsumer", daemon=True)
    thread.start()
    return thread, counts


def _describe_event(event: SensorEvent) -> str:
    if isinstance(event, AngleEvent):
        return f"AngleEvent {_head(event.data.angles.to_list())}"
    if isinstance(event, SpeedEvent):
        return f"SpeedEvent {_head(event.data.speeds)}"
    if isinstance(event, TorqueEvent):
        return f"TorqueEvent {_head(event.data.torques)}"
    if isinstance(event, CurrentEvent):
        return f"CurrentEvent {_head(event.data.currents)}"
    if isinstance(event, TemperatureEvent):
        return f"TemperatureEvent {_head(event.data.temperatures)}"
    if isinstance(event, FaultEvent):
        return f"FaultEvent {_head(event.data.faults)}"
    if isinstance(event, ForceSensorEvent):
        return f"ForceSensorEvent thumb_max={int(event.data.thumb.max())}"
    return type(event).__name__


def _neutral_target() -> list[float]:
    # 带负最小值的对称关节用 50% 对应原始 0；其余关节用 0%。
    return [50.0 if spec.minimum < 0 else 0.0 for spec in L30_JOINT_SPECS]


def _step(label: str, action: Callable[[], None], *, strict: bool) -> None:
    print(f"\n[L30] {label}")
    try:
        action()
    except LinkerbotError as error:
        print(f"  [warning] {error}")
        if strict:
            raise


def _head(values: Sequence[int | float], limit: int = 4) -> list[int | float]:
    return list(values[:limit])


def _auto_int(value: str) -> int:
    return int(value, 0)


def _validate_args(args: argparse.Namespace) -> None:
    if args.timeout_ms <= 0:
        raise SystemExit("--timeout-ms must be positive")
    if args.stream_seconds <= 0:
        raise SystemExit("--stream-seconds must be positive")
    if args.period_ms < 20:
        raise SystemExit("--period-ms must be at least 20")
    if not 0 <= args.target_percent <= 100:
        raise SystemExit("--target-percent must be between 0 and 100")
    if args.move_seconds < 0:
        raise SystemExit("--move-seconds must be non-negative")


if __name__ == "__main__":
    try:
        run()
    except KeyboardInterrupt:
        print("\n[L30] 用户中断，正在安全退出", file=sys.stderr)
        sys.exit(130)
    except LinkerbotError as error:
        print(f"[L30] SDK 错误：{error}", file=sys.stderr)
        sys.exit(1)
