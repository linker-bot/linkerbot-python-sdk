"""Internal helpers shared by O30 one-byte runtime-object managers."""

from __future__ import annotations

from linkerbot.hand.hand_protocol_v1 import HandProtocolV1

from . import protocol


def read_vector(
    client: HandProtocolV1,
    *,
    main_index: int,
    timeout_ms: float,
    rts: bool = False,
) -> tuple[int, ...]:
    response = client.read(
        main_index=main_index,
        length=protocol.O30_RUNTIME_SLOT_COUNT,
        rts=rts,
        timeout_ms=timeout_ms,
    )
    return protocol.decode_runtime_vector(response)


def write_vector(
    client: HandProtocolV1,
    *,
    main_index: int,
    values: list[int] | tuple[int, ...],
    timeout_ms: float,
) -> None:
    for sub_index, payload in protocol.encode_control_vector(values):
        client.write(
            main_index=main_index,
            sub_index=sub_index,
            payload=payload,
            timeout_ms=timeout_ms,
        )
