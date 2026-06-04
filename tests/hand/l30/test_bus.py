from __future__ import annotations

import pytest

from linkerbot.comm.canfd import CANFDMessage
from linkerbot.exceptions import ValidationError
from linkerbot.hand.l30 import L30, L30Bus
from tests.hand.l30.fakes import FakeDispatcher

pytestmark = [pytest.mark.l30, pytest.mark.canfd]


def test_bus_connect_returns_l30_hands_in_node_order() -> None:
    dispatcher = FakeDispatcher()
    bus = L30Bus(dispatcher=dispatcher, auto_start_periodic=False)

    hands = bus.connect([1, 2, 3])

    assert [hand.node_id for hand in hands] == [1, 2, 3]
    assert all(isinstance(hand, L30) for hand in hands)
    assert bus.hands == tuple(hands)
    assert bus.get(2) is hands[1]

    bus.close()


def test_bus_connect_map_returns_hands_by_node_id() -> None:
    bus = L30Bus(dispatcher=FakeDispatcher(), auto_start_periodic=False)

    hands = bus.connect_map([1, 2, 3])

    assert list(hands) == [1, 2, 3]
    assert hands[1].node_id == 1
    assert hands[2].node_id == 2
    assert hands[3].node_id == 3
    assert bus.by_node_id[2] is hands[2]

    bus.close()


def test_bus_rejects_duplicate_node_ids_without_partial_create() -> None:
    bus = L30Bus(dispatcher=FakeDispatcher(), auto_start_periodic=False)

    with pytest.raises(ValidationError):
        bus.connect([1, 2, 2])

    assert bus.hands == ()
    bus.close()


def test_bus_rejects_already_connected_node_id() -> None:
    bus = L30Bus(dispatcher=FakeDispatcher(), auto_start_periodic=False)
    bus.create_hand(1)

    with pytest.raises(ValidationError):
        bus.connect([1])

    assert [hand.node_id for hand in bus.hands] == [1]
    bus.close()


def test_bus_routes_reports_to_matching_node_only() -> None:
    dispatcher = FakeDispatcher()
    bus = L30Bus(dispatcher=dispatcher, auto_start_periodic=False)
    left, right, extra = bus.connect([1, 2, 3])

    dispatcher.inject(CANFDMessage(arbitration_id=0x00802008, data=_i16_report(1)))
    dispatcher.inject(CANFDMessage(arbitration_id=0x00802010, data=_i16_report(2)))
    dispatcher.inject(CANFDMessage(arbitration_id=0x00802018, data=_i16_report(3)))

    assert left.angle.get_snapshot().angles.to_list() == [1] * 17
    assert right.angle.get_snapshot().angles.to_list() == [2] * 17
    assert extra.angle.get_snapshot().angles.to_list() == [3] * 17

    bus.close()


def test_closing_one_hand_does_not_stop_shared_dispatcher_or_other_hands() -> None:
    dispatcher = FakeDispatcher()
    bus = L30Bus(dispatcher=dispatcher, auto_start_periodic=False)
    first, second = bus.connect([1, 2])

    first.close()
    dispatcher.inject(CANFDMessage(arbitration_id=0x00802010, data=_i16_report(2)))

    assert not dispatcher.stopped
    assert second.angle.get_snapshot().angles.to_list() == [2] * 17

    bus.close()


def test_bus_close_closes_all_hands_and_owned_dispatcher() -> None:
    dispatcher = FakeDispatcher()
    bus = L30Bus(dispatcher=dispatcher, auto_start_periodic=False)
    bus._owns_dispatcher = True
    bus.connect([1, 2])

    bus.close_all()
    bus.close_all()

    assert dispatcher.stopped
    assert all(hand.is_closed() for hand in bus.hands)


def test_bus_close_does_not_stop_injected_dispatcher() -> None:
    dispatcher = FakeDispatcher()
    bus = L30Bus(dispatcher=dispatcher, auto_start_periodic=False)
    bus.connect([1, 2])

    bus.close()

    assert not dispatcher.stopped
    assert all(hand.is_closed() for hand in bus.hands)


def test_bus_context_manager_closes_hands() -> None:
    dispatcher = FakeDispatcher()

    with L30Bus(dispatcher=dispatcher, auto_start_periodic=False) as bus:
        hands = bus.connect([1, 2])

    assert all(hand.is_closed() for hand in hands)


def test_bus_get_unknown_node_id_raises_key_error() -> None:
    bus = L30Bus(dispatcher=FakeDispatcher(), auto_start_periodic=False)

    with pytest.raises(KeyError):
        bus.get(1)

    bus.close()


def test_duplicate_node_ids_are_allowed_on_different_buses() -> None:
    bus0 = L30Bus(dispatcher=FakeDispatcher(), auto_start_periodic=False)
    bus1 = L30Bus(dispatcher=FakeDispatcher(), auto_start_periodic=False)

    hand0 = bus0.create_hand(1)
    hand1 = bus1.create_hand(1)

    assert hand0.node_id == 1
    assert hand1.node_id == 1
    assert hand0 is not hand1

    bus0.close()
    bus1.close()


def test_same_node_id_on_different_buses_routes_independently() -> None:
    dispatcher0 = FakeDispatcher()
    dispatcher1 = FakeDispatcher()
    bus0 = L30Bus(dispatcher=dispatcher0, auto_start_periodic=False)
    bus1 = L30Bus(dispatcher=dispatcher1, auto_start_periodic=False)
    hand0 = bus0.create_hand(1)
    hand1 = bus1.create_hand(1)

    dispatcher0.inject(CANFDMessage(arbitration_id=0x00802008, data=_i16_report(1)))
    dispatcher1.inject(CANFDMessage(arbitration_id=0x00802008, data=_i16_report(2)))

    assert hand0.angle.get_snapshot().angles.to_list() == [1] * 17
    assert hand1.angle.get_snapshot().angles.to_list() == [2] * 17

    bus0.close()
    bus1.close()


def test_closing_one_bus_does_not_close_another_bus() -> None:
    dispatcher0 = FakeDispatcher()
    dispatcher1 = FakeDispatcher()
    bus0 = L30Bus(dispatcher=dispatcher0, auto_start_periodic=False)
    bus1 = L30Bus(dispatcher=dispatcher1, auto_start_periodic=False)
    hand0 = bus0.create_hand(1)
    hand1 = bus1.create_hand(1)

    bus0.close()
    dispatcher1.inject(CANFDMessage(arbitration_id=0x00802008, data=_i16_report(2)))

    assert hand0.is_closed()
    assert not hand1.is_closed()
    assert not dispatcher1.stopped
    assert hand1.angle.get_snapshot().angles.to_list() == [2] * 17

    bus1.close()


def _i16_report(value: int) -> bytes:
    return bytes([0x22, 0x00]) + value.to_bytes(2, "big", signed=True) * 17
