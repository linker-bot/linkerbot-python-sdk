"""Manual L30 CANFD enable/disable smoke test.

Run from the repository root with hardware connected:

    uv run --group test python tests/l30test.py \
        --library-path src/linkerbot/hand/libcanbus.so
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import time
from linkerbot.comm.canfd import CANFDConfigOptions, CANFDInterface, CANFDMessage

DEFAULT_LIBRARY_PATH = "src/linkerbot/hand/libcanbus.so"
DEFAULT_DEVICE_INDEX = 0
DEFAULT_CHANNEL_INDEX = 0
DEFAULT_NODE_ID = 1
DEFAULT_HOST_ID = 0
DEFAULT_FRAME_TYPE = 0x0C
DEFAULT_TIMEOUT_MS = 100
DEFAULT_RECEIVE_ATTEMPTS = 50

L30_PRIORITY_CONTROL = 0
L30_ACCESS_READ = 0
L30_ACCESS_WRITE = 1
L30_PARENT_CONTROL = 0x1
L30_SUBCMD_ENABLE = 0x07
L30_SUBCMD_DISABLE = 0x08
L30_SINGLE_FRAME_TRANSACTION = 0x00
L30_EMPTY_PAYLOAD_LENGTH = 0x00
L30_STATUS_OK = 0x00
L30_STATUS_BYTE_INDEX = 2
L30_HEADER_LENGTH = 2
L30_ACK_DLC = 3


@dataclass(frozen=True, slots=True)
class L30Command:
    name: str
    subcmd: int


L30_ENABLE = L30Command(name="enable", subcmd=L30_SUBCMD_ENABLE)
L30_DISABLE = L30Command(name="disable", subcmd=L30_SUBCMD_DISABLE)


def build_l30_can_id(
    *,
    priority: int,
    access: int,
    parent_cmd: int,
    subcmd: int,
    dst_id: int,
    src_id: int,
) -> int:
    """Build an L30 v2 CANFD extended arbitration ID."""
    return (
        (priority << 26)
        | (access << 25)
        | (parent_cmd << 21)
        | (subcmd << 13)
        | (dst_id << 8)
        | (src_id << 3)
    )


def build_control_request(
    command: L30Command,
    *,
    node_id: int,
    host_id: int,
    frame_type: int,
) -> tuple[CANFDMessage, int]:
    """Build one global enable/disable request and its expected response ID."""
    request_id = build_l30_can_id(
        priority=L30_PRIORITY_CONTROL,
        access=L30_ACCESS_WRITE,
        parent_cmd=L30_PARENT_CONTROL,
        subcmd=command.subcmd,
        dst_id=node_id,
        src_id=host_id,
    )
    response_id = build_l30_can_id(
        priority=L30_PRIORITY_CONTROL,
        access=L30_ACCESS_WRITE,
        parent_cmd=L30_PARENT_CONTROL,
        subcmd=command.subcmd,
        dst_id=host_id,
        src_id=node_id,
    )
    message = CANFDMessage(
        arbitration_id=request_id,
        data=bytes([L30_EMPTY_PAYLOAD_LENGTH, L30_SINGLE_FRAME_TRANSACTION]),
        dlc=L30_ACK_DLC,
        is_extended_id=True,
        frame_type=frame_type,
    )
    return message, response_id


def run_command(
    interface: CANFDInterface,
    command: L30Command,
    *,
    node_id: int,
    host_id: int,
    frame_type: int,
    timeout_ms: int,
    receive_attempts: int,
) -> None:
    """Send one L30 global command and wait for its v2 write ACK."""
    request, response_id = build_control_request(
        command,
        node_id=node_id,
        host_id=host_id,
        frame_type=frame_type,
    )
    print(
        f"send {command.name}: "
        f"request_id=0x{request.arbitration_id:08X}, "
        f"expected_response_id=0x{response_id:08X}, "
        f"data={request.data.hex(' ')}, dlc=0x{request.dlc:02X}"
    )
    interface.send(request, timeout_ms=timeout_ms)

    for _ in range(receive_attempts):
        for response in interface.receive(max_frames=16, timeout_ms=timeout_ms):
            print(
                f"recv: id=0x{response.arbitration_id:08X}, "
                f"dlc=0x{response.dlc:02X}, data={response.data.hex(' ')}"
            )
            if response.arbitration_id != response_id:
                continue
            validate_control_response(command, response)
            print(f"{command.name} ok")
            return
    raise TimeoutError(f"no matching {command.name} response received")


def validate_control_response(command: L30Command, response: CANFDMessage) -> None:
    """Validate the single-frame ACK payload for L30 global enable/disable."""
    if len(response.data) < L30_STATUS_BYTE_INDEX + 1:
        raise RuntimeError(
            f"{command.name} response too short: {response.data.hex(' ')}"
        )
    if response.data[:L30_HEADER_LENGTH] != bytes(
        [L30_EMPTY_PAYLOAD_LENGTH, L30_SINGLE_FRAME_TRANSACTION]
    ):
        raise RuntimeError(
            f"{command.name} response header unexpected: {response.data.hex(' ')}"
        )
    status = response.data[L30_STATUS_BYTE_INDEX]
    if status != L30_STATUS_OK:
        raise RuntimeError(f"{command.name} failed with status 0x{status:02X}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--library-path", default=DEFAULT_LIBRARY_PATH)
    parser.add_argument("--device-index", type=int, default=DEFAULT_DEVICE_INDEX)
    parser.add_argument("--channel-index", type=int, default=DEFAULT_CHANNEL_INDEX)
    parser.add_argument("--node-id", type=int, default=DEFAULT_NODE_ID)
    parser.add_argument("--host-id", type=int, default=DEFAULT_HOST_ID)
    parser.add_argument(
        "--frame-type", type=lambda value: int(value, 0), default=DEFAULT_FRAME_TYPE
    )
    parser.add_argument("--timeout-ms", type=int, default=DEFAULT_TIMEOUT_MS)
    parser.add_argument(
        "--receive-attempts", type=int, default=DEFAULT_RECEIVE_ATTEMPTS
    )
    parser.add_argument("--disable-only", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = CANFDConfigOptions(frame_type=args.frame_type)
    with CANFDInterface(
        device_index=args.device_index,
        channel_index=args.channel_index,
        library_path=args.library_path,
        config=config,
    ) as interface:
        commands = [L30_DISABLE] if args.disable_only else [L30_ENABLE, L30_DISABLE]
        for command in commands:
            run_command(
                interface,
                command,
                node_id=args.node_id,
                host_id=args.host_id,
                frame_type=args.frame_type,
                timeout_ms=args.timeout_ms,
                receive_attempts=args.receive_attempts,
            )
            time.sleep(2)


if __name__ == "__main__":
    main()
