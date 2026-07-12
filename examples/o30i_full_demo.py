"""O30i 实物只读诊断、轮询和低幅度单关节点动示例。

准备 SocketCAN FD（默认 1 Mbit/s 仲裁、5 Mbit/s 数据段）：

    sudo ip link set can0 down
    sudo ip link set can0 type can bitrate 1000000 dbitrate 5000000 fd on
    sudo ip link set can0 up

执行只读诊断（默认不会发送运动命令）：

    uv run python examples/o30i_full_demo.py --channel can0

使用厂商动态库：

    uv run python examples/o30i_full_demo.py \
        --interface ctypes --library-path /usr/local/lib/libcanbus.so

低幅度点动食指指尖；程序会要求输入 ``MOVE``，并在 finally 中恢复原值：

    uv run python examples/o30i_full_demo.py \
        --channel can0 --move --joint tip_1 --delta-raw 8

O30i 高层 SDK 没有可靠的使能/失能接口。运行 ``--move`` 前必须确保设备
处于可运动状态、手部无负载、人员远离机构，并准备好硬件急停或断电手段。
"""

from __future__ import annotations

import argparse
import sys
import threading
import time
from collections import Counter
from collections.abc import Callable, Sequence

from linkerbot.exceptions import LinkerbotError
from linkerbot.hand.o30i import (
    O30I_DEFAULT_RAW_VALUES,
    O30I_JOINT_COUNT,
    O30I_JOINT_SPECS,
    O30i,
    SensorSource,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="O30i 实物全功能示例（默认仅执行只读诊断）"
    )
    parser.add_argument(
        "--interface",
        choices=("socketcan", "ctypes"),
        default="socketcan",
        help="CAN FD 后端，默认 socketcan",
    )
    parser.add_argument("--channel", default="can0", help="SocketCAN 接口名")
    parser.add_argument("--device", type=int, default=0, help="厂商适配器设备索引")
    parser.add_argument(
        "--adapter-channel", type=int, default=0, help="厂商适配器通道索引"
    )
    parser.add_argument("--library-path", help="libcanbus.so / HCanbus.dll 路径")
    parser.add_argument("--request-id", type=_auto_int, default=0x001)
    parser.add_argument("--response-id", type=_auto_int)
    parser.add_argument("--bitrate", type=int, default=1_000_000)
    parser.add_argument("--data-bitrate", type=int, default=5_000_000)
    parser.add_argument(
        "--auto-reconfigure",
        action="store_true",
        help="允许 SDK 配置 SocketCAN 链路；需要 CAP_NET_ADMIN",
    )
    parser.add_argument("--timeout-ms", type=float, default=1000.0)
    parser.add_argument(
        "--poll-seconds",
        type=float,
        default=2.0,
        help="全部运行时状态的主机轮询时长",
    )
    parser.add_argument(
        "--skip-polling", action="store_true", help="跳过轮询和事件流测试"
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="任一可选只读功能失败时立即退出；默认记录后继续",
    )
    parser.add_argument(
        "--move",
        action="store_true",
        help="显式允许执行一次低幅度单关节点动",
    )
    parser.add_argument(
        "--joint",
        default="tip_1",
        help="点动关节的 ID 或 SDK 索引，默认 tip_1",
    )
    parser.add_argument(
        "--delta-raw",
        type=int,
        default=8,
        help="相对当前位置的原始字节增量，建议绝对值不超过 16",
    )
    parser.add_argument("--hold-seconds", type=float, default=1.0)
    parser.add_argument(
        "--move-method",
        choices=("slice", "sparse"),
        default="slice",
        help="使用普通位置切片或 MI=0x30 稀疏位置点动",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="跳过 MOVE 交互确认；仅用于已建立外部安全措施的自动化环境",
    )
    return parser.parse_args()


def run() -> None:
    args = parse_args()
    _validate_args(args)
    joint_index = _resolve_joint(args.joint)
    if args.move:
        _confirm_motion(args, joint_index)

    print(
        f"[O30i] interface={args.interface}, request_id=0x{args.request_id:03X}, "
        f"response_id={_format_response_id(args.response_id)}"
    )
    hand = _open_hand(args)
    with hand:
        print(
            f"[O30i] 已连接：request_id=0x{hand.request_id:03X}, "
            f"response_id=0x{hand.response_id:03X}"
        )
        _show_joint_definitions()

        _step(
            "读取产品与版本信息",
            lambda: _show_device_info(hand, args.timeout_ms),
            strict=args.strict,
        )
        _step(
            "读取 8 位实际位置和目标位置",
            lambda: _show_angles(hand, args.timeout_ms),
            strict=args.strict,
        )
        _step(
            "读取完整 16 位位置对象",
            lambda: _show_i16_angles(hand, args.timeout_ms),
            strict=args.strict,
        )
        for state_name, reader in _runtime_readers(hand, args.timeout_ms):
            _step(
                f"读取 {state_name}",
                lambda reader=reader: _show_runtime_state(state_name, reader()),
                strict=args.strict,
            )
        _step(
            "读取关节故障字节",
            lambda: _show_faults(hand, args.timeout_ms),
            strict=args.strict,
        )
        _step(
            "读取传感器能力信息",
            lambda: _show_sensor_info(hand, args.timeout_ms),
            strict=args.strict,
        )
        _step(
            "读取通信错误历史",
            lambda: _show_diagnostics(hand, args.timeout_ms),
            strict=args.strict,
        )

        if not args.skip_polling:
            _step(
                "测试全部运行时来源的主机轮询和事件流",
                lambda: _poll_all_sources(hand, args.poll_seconds),
                strict=args.strict,
            )

        if args.move:
            _step(
                f"低幅度点动 {O30I_JOINT_SPECS[joint_index].id}",
                lambda: _move_one_joint(
                    hand,
                    joint_index=joint_index,
                    delta_raw=args.delta_raw,
                    hold_seconds=args.hold_seconds,
                    timeout_ms=args.timeout_ms,
                    method=args.move_method,
                ),
                strict=True,
            )
        else:
            print("\n[O30i] 未传 --move：没有发送任何运动命令")

        _show_snapshot_summary(hand)

    print(f"\n[O30i] 连接已关闭：closed={hand.is_closed()}")


def _open_hand(args: argparse.Namespace) -> O30i:
    if args.interface == "socketcan":
        return O30i(
            request_id=args.request_id,
            response_id=args.response_id,
            interface_type="socketcan",
            socketcan_channel=args.channel,
            bitrate=args.bitrate,
            data_bitrate=args.data_bitrate,
            auto_reconfigure=args.auto_reconfigure,
        )
    return O30i(
        request_id=args.request_id,
        response_id=args.response_id,
        interface_type="ctypes",
        device=args.device,
        channel=args.adapter_channel,
        library_path=args.library_path,
    )


def _show_joint_definitions() -> None:
    print("\n[O30i] 20 个实际关节（SDK index -> wire SI）")
    for index, spec in enumerate(O30I_JOINT_SPECS):
        print(
            f"  {index:2d}  {spec.id:8s}  {spec.name:6s}  "
            f"SI={spec.wire_slot:02d}  default={spec.default:3d}"
        )
    print("  default raw:", list(O30I_DEFAULT_RAW_VALUES))


def _show_device_info(hand: O30i, timeout_ms: float) -> None:
    info = hand.version.get_device_info(timeout_ms=timeout_ms)
    print("  product_model:", info.product_model)
    print("  voltage_range:", info.voltage_range)
    print("  device_uid:", info.device_uid)
    print("  protocol:", info.protocol_name, info.protocol_version)
    print("  application_version:", info.application_version)
    print("  hardware versions:", end=" ")
    print(
        info.interface_hardware_version,
        info.adapter_hardware_version,
        info.controller_hardware_version,
    )
    print("  mechanical_version:", info.mechanical_version)
    print("  compile_time:", info.compile_time)
    print("  supported_interfaces:", info.supported_interfaces)


def _show_angles(hand: O30i, timeout_ms: float) -> None:
    actual = hand.angle.get_blocking(timeout_ms=timeout_ms).angles
    target = hand.angle.get_target_blocking(timeout_ms=timeout_ms)
    _print_joint_values("actual raw", actual.to_raw())
    _print_joint_values("target raw", target.to_raw())
    print("  actual percent:", [round(value, 2) for value in actual.to_list()])


def _show_i16_angles(hand: O30i, timeout_ms: float) -> None:
    values = hand.angle.get_i16_blocking(timeout_ms=timeout_ms)
    _print_joint_values("position i16", values)


def _runtime_readers(
    hand: O30i, timeout_ms: float
) -> tuple[tuple[str, Callable[[], Sequence[int]]], ...]:
    return (
        ("speed", lambda: hand.speed.get_blocking(timeout_ms).speeds),
        (
            "acceleration",
            lambda: hand.acceleration.get_blocking(timeout_ms).accelerations,
        ),
        ("current", lambda: hand.current.get_blocking(timeout_ms).currents),
        ("voltage", lambda: hand.voltage.get_blocking(timeout_ms).voltages),
        ("torque", lambda: hand.torque.get_blocking(timeout_ms).torques),
        (
            "temperature",
            lambda: hand.temperature.get_blocking(timeout_ms).temperatures,
        ),
        ("motion ticks", lambda: hand.motion_time.get_blocking(timeout_ms).ticks),
    )


def _show_runtime_state(name: str, values: Sequence[int]) -> None:
    print(f"  {name:12s}: {list(values)}")


def _show_faults(hand: O30i, timeout_ms: float) -> None:
    faults = hand.fault.get_blocking(timeout_ms)
    print("  raw:", list(faults.faults))
    active = [
        O30I_JOINT_SPECS[index].id
        for index in range(O30I_JOINT_COUNT)
        if faults.has_fault(index)
    ]
    print("  non-zero joints:", active or "none")


def _show_sensor_info(hand: O30i, timeout_ms: float) -> None:
    info = hand.sensor.get_info(timeout_ms=timeout_ms)
    print("  sensor_type:", info.sensor_type)
    print("  unit:", info.unit)
    print("  total_data_length:", info.total_data_length)
    print("  selected/shape:", info.selected_sensor, info.rows, info.columns)
    if not info.has_sensor_data:
        print("  当前固件没有可读取的触觉数据通道")


def _show_diagnostics(hand: O30i, timeout_ms: float) -> None:
    data = hand.diagnostics.get_communication_errors(timeout_ms=timeout_ms)
    print("  latest_index:", data.latest_index)
    print("  history:", data.history.hex(" "))


def _poll_all_sources(hand: O30i, duration_s: float) -> None:
    stream = hand.stream(maxsize=200)
    event_counts: Counter[str] = Counter()

    def consume() -> None:
        for event in stream:
            event_counts[type(event).__name__] += 1

    consumer = threading.Thread(target=consume, daemon=True, name="O30i-Demo-Stream")
    consumer.start()
    intervals = {
        SensorSource.ANGLE: 0.10,
        SensorSource.SPEED: 0.25,
        SensorSource.ACCELERATION: 0.50,
        SensorSource.CURRENT: 0.25,
        SensorSource.VOLTAGE: 0.50,
        SensorSource.TORQUE: 0.25,
        SensorSource.TEMPERATURE: 0.50,
        SensorSource.MOTION_TIME: 0.50,
        SensorSource.FAULT: 0.50,
    }
    try:
        hand.start_polling(intervals)
        time.sleep(duration_s)
    finally:
        hand.stop_polling()
        hand.stop_stream()
        consumer.join(timeout=2.0)
    print("  event counts:", dict(sorted(event_counts.items())))


def _move_one_joint(
    hand: O30i,
    *,
    joint_index: int,
    delta_raw: int,
    hold_seconds: float,
    timeout_ms: float,
    method: str,
) -> None:
    spec = O30I_JOINT_SPECS[joint_index]
    baseline = hand.angle.get_blocking(timeout_ms=timeout_ms).angles.to_raw()
    original = baseline[joint_index]
    target = max(spec.minimum, min(spec.maximum, original + delta_raw))
    if target == original:
        target = max(spec.minimum, min(spec.maximum, original - delta_raw))
    if target == original:
        raise RuntimeError(f"{spec.id} 已在边界，无法应用 delta {delta_raw}")

    print(
        f"  {joint_index}:{spec.id}/{spec.name}, raw {original} -> {target}, "
        f"method={method}"
    )
    try:
        _write_one_joint(hand, joint_index, target, timeout_ms, method)
        time.sleep(hold_seconds)
        actual = hand.angle.get_blocking(timeout_ms=timeout_ms).angles.to_raw()
        print("  点动后实际 raw:", actual[joint_index])
    finally:
        print(f"  恢复 {spec.id} 到 raw={original}")
        _write_one_joint(hand, joint_index, original, timeout_ms, method)
        time.sleep(hold_seconds)
        restored = hand.angle.get_blocking(timeout_ms=timeout_ms).angles.to_raw()
        print("  恢复后实际 raw:", restored[joint_index])


def _write_one_joint(
    hand: O30i,
    joint_index: int,
    value: int,
    timeout_ms: float,
    method: str,
) -> None:
    if method == "sparse":
        hand.angle.set_sparse({joint_index: value}, timeout_ms=timeout_ms)
    else:
        hand.angle.set_raw_slice(joint_index, [value], timeout_ms=timeout_ms)


def _show_snapshot_summary(hand: O30i) -> None:
    snapshot = hand.get_snapshot()
    print("\n[O30i] manager snapshots")
    for name in (
        "angle",
        "speed",
        "acceleration",
        "current",
        "voltage",
        "torque",
        "temperature",
        "motion_time",
        "fault",
    ):
        print(f"  {name:12s}: {'ready' if getattr(snapshot, name) else 'none'}")


def _print_joint_values(label: str, values: Sequence[int]) -> None:
    print(f"  {label}:")
    for index, (spec, value) in enumerate(zip(O30I_JOINT_SPECS, values, strict=True)):
        print(f"    {index:2d}  {spec.id:8s}  {spec.name:6s}  {value}")


def _step(label: str, action: Callable[[], None], *, strict: bool) -> None:
    print(f"\n[O30i] {label}")
    try:
        action()
    except LinkerbotError as error:
        print(f"  [warning] {error}")
        if strict:
            raise


def _resolve_joint(value: str) -> int:
    try:
        index = int(value, 0)
    except ValueError:
        for index, spec in enumerate(O30I_JOINT_SPECS):
            if value == spec.id:
                return index
        raise SystemExit(f"unknown --joint {value!r}") from None
    if index < 0 or index >= O30I_JOINT_COUNT:
        raise SystemExit(f"--joint index must be between 0 and {O30I_JOINT_COUNT - 1}")
    return index


def _confirm_motion(args: argparse.Namespace, joint_index: int) -> None:
    spec = O30I_JOINT_SPECS[joint_index]
    print(
        "\n[O30i] 警告：即将向实物发送运动命令。SDK 无可靠的使能/失能接口。\n"
        f"目标关节：{joint_index}:{spec.id}/{spec.name}，delta={args.delta_raw}\n"
        "确认无负载、人员远离机构，并已准备硬件急停或断电。"
    )
    if args.yes:
        return
    if not sys.stdin.isatty():
        raise SystemExit("non-interactive --move requires --yes")
    if input("输入 MOVE 继续：").strip() != "MOVE":
        raise SystemExit("motion cancelled")


def _validate_args(args: argparse.Namespace) -> None:
    if args.device < 0 or args.adapter_channel < 0:
        raise SystemExit("--device and --adapter-channel must be non-negative")
    if args.timeout_ms <= 0:
        raise SystemExit("--timeout-ms must be positive")
    if args.poll_seconds <= 0:
        raise SystemExit("--poll-seconds must be positive")
    if args.delta_raw == 0 or abs(args.delta_raw) > 32:
        raise SystemExit("--delta-raw must be non-zero and between -32 and 32")
    if args.hold_seconds < 0:
        raise SystemExit("--hold-seconds must be non-negative")
    if args.yes and not args.move:
        raise SystemExit("--yes is only valid together with --move")


def _format_response_id(value: int | None) -> str:
    return "auto" if value is None else f"0x{value:03X}"


def _auto_int(value: str) -> int:
    return int(value, 0)


if __name__ == "__main__":
    try:
        run()
    except KeyboardInterrupt:
        print("\n[O30i] 用户中断，正在释放连接", file=sys.stderr)
        sys.exit(130)
    except LinkerbotError as error:
        print(f"[O30i] SDK 错误：{error}", file=sys.stderr)
        sys.exit(1)
