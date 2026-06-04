"""Shared CANFD bus/session for managing multiple L30 hands."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import Path
from types import MappingProxyType

from linkerbot.comm.canfd import CANFDConfigOptions, CANFDMessageDispatcher
from linkerbot.exceptions import ValidationError

from . import protocol
from .client import L30DispatcherLike
from .l30 import L30


class L30Bus:
    """Manage any number of L30 hands on one shared CANFD bus.

    L30 devices are addressed by NodeID. A single CANFD adapter/channel can host
    multiple L30 hands as long as each hand has a unique NodeID. L30Bus owns one
    dispatcher by default and returns normal L30 objects that share that dispatcher.
    """

    def __init__(
        self,
        *,
        host_id: int = 0,
        device_index: int = 0,
        channel_index: int = 0,
        library_path: str | Path | None = None,
        config: CANFDConfigOptions | None = None,
        auto_start_periodic: bool = True,
        dispatcher: L30DispatcherLike | None = None,
    ) -> None:
        """Open a shared CANFD bus for one or more L30 hands.

        Args:
            host_id: Host node ID used as source ID for all created hands.
            device_index: Vendor CANFD adapter device index.
            channel_index: Vendor CANFD adapter channel index.
            library_path: Optional vendor dynamic library path. If omitted, the
                CANFD backend uses its default lookup, including the system loader.
            config: CANFD adapter configuration.
            auto_start_periodic: Default periodic-report behavior for new hands.
            dispatcher: Optional dispatcher-like transport for tests or advanced use.
        """
        protocol._validate_range(
            host_id, "host_id", protocol.L30_HOST_ID_MIN, protocol.L30_HOST_ID_MAX
        )
        self._host_id = host_id
        self._auto_start_periodic = auto_start_periodic
        self._owns_dispatcher = dispatcher is None
        if dispatcher is None:
            dispatcher = CANFDMessageDispatcher(
                device_index=device_index,
                channel_index=channel_index,
                library_path=library_path,
                config=config,
                on_bus_error=self._on_bus_error,
            )
        self._dispatcher = dispatcher
        self._hands_by_node_id: dict[int, L30] = {}
        self._hand_order: list[int] = []
        self._closed = False
        self._bus_error: Exception | None = None

    @property
    def hands(self) -> tuple[L30, ...]:
        """Connected L30 hand objects in creation order."""
        return tuple(self._hands_by_node_id[node_id] for node_id in self._hand_order)

    @property
    def by_node_id(self) -> Mapping[int, L30]:
        """Read-only mapping from NodeID to connected L30 hand."""
        return MappingProxyType(self._hands_by_node_id)

    def connect(
        self, node_ids: Iterable[int], *, auto_start_periodic: bool | None = None
    ) -> list[L30]:
        """Create and register multiple L30 hands on this bus.

        Args:
            node_ids: Distinct L30 NodeIDs to connect.
            auto_start_periodic: Optional override for new hands.

        Returns:
            L30 objects in the same order as node_ids.
        """
        normalized = self._validate_new_node_ids(node_ids)
        created: list[L30] = []
        try:
            for node_id in normalized:
                created.append(
                    self._create_hand_unchecked(
                        node_id,
                        auto_start_periodic=self._resolve_auto_start_periodic(
                            auto_start_periodic
                        ),
                    )
                )
        except Exception:
            for hand in created:
                hand.close()
                self._hands_by_node_id.pop(hand.node_id, None)
                if hand.node_id in self._hand_order:
                    self._hand_order.remove(hand.node_id)
            raise
        return created

    def connect_map(
        self, node_ids: Iterable[int], *, auto_start_periodic: bool | None = None
    ) -> dict[int, L30]:
        """Create multiple hands and return them keyed by NodeID."""
        hands = self.connect(node_ids, auto_start_periodic=auto_start_periodic)
        return {hand.node_id: hand for hand in hands}

    def create_hand(
        self, node_id: int, *, auto_start_periodic: bool | None = None
    ) -> L30:
        """Create and register one L30 hand on this bus."""
        return self.connect([node_id], auto_start_periodic=auto_start_periodic)[0]

    def get(self, node_id: int) -> L30:
        """Return an already connected L30 hand by NodeID."""
        return self._hands_by_node_id[node_id]

    def close_all(self) -> None:
        """Close all managed hands and release the owned dispatcher."""
        if self._closed:
            return
        for node_id in reversed(self._hand_order):
            self._hands_by_node_id[node_id].close()
        if self._owns_dispatcher:
            self._dispatcher.stop()
        self._closed = True

    def close(self) -> None:
        """Alias for close_all()."""
        self.close_all()

    def __enter__(self) -> L30Bus:
        """Enter the context manager."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        """Exit the context manager and release bus resources."""
        self.close_all()
        return False

    def _validate_new_node_ids(self, node_ids: Iterable[int]) -> list[int]:
        if self._closed:
            raise ValidationError("L30Bus is closed")
        normalized = list(node_ids)
        seen: set[int] = set()
        for node_id in normalized:
            protocol._validate_range(
                node_id,
                "node_id",
                protocol.L30_NODE_ID_MIN,
                protocol.L30_NODE_ID_MAX,
            )
            if node_id in seen or node_id in self._hands_by_node_id:
                raise ValidationError(
                    f"duplicate L30 node_id {node_id} on this CANFD bus"
                )
            seen.add(node_id)
        return normalized

    def _create_hand_unchecked(self, node_id: int, *, auto_start_periodic: bool) -> L30:
        hand = L30(
            node_id=node_id,
            host_id=self._host_id,
            auto_start_periodic=auto_start_periodic,
            dispatcher=self._dispatcher,
        )
        self._hands_by_node_id[node_id] = hand
        self._hand_order.append(node_id)
        return hand

    def _resolve_auto_start_periodic(self, auto_start_periodic: bool | None) -> bool:
        if auto_start_periodic is None:
            return self._auto_start_periodic
        return auto_start_periodic

    def _on_bus_error(self, error: Exception) -> None:
        self._bus_error = error
        self.close_all()
