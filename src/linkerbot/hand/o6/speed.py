"""Speed and acceleration control for O6 robotic hand.

This module provides the SpeedManager and AccelerationManager classes for
controlling motor speeds and accelerations via CAN bus communication.
"""

import time
from collections.abc import Callable
from dataclasses import dataclass

import can

from linkerbot.comm import CANMessageDispatcher
from linkerbot.exceptions import ValidationError
from linkerbot.relay import DataRelay


@dataclass
class O6Speed:
    """Motor speeds for O6 hand (0-100 range or RPM).

    Speeds can be specified either as normalized 0-100 values or in RPM units.
    Maximum speed: 186.66 RPM (corresponds to 100).

    Attributes:
        thumb_flex: Thumb flexion motor speed (0-100). Higher values = faster.
        thumb_abd: Thumb abduction motor speed (0-100). Higher values = faster.
        index: Index finger motor speed (0-100). Higher values = faster.
        middle: Middle finger motor speed (0-100). Higher values = faster.
        ring: Ring finger motor speed (0-100). Higher values = faster.
        pinky: Pinky finger motor speed (0-100). Higher values = faster.
    """

    thumb_flex: float
    thumb_abd: float
    index: float
    middle: float
    ring: float
    pinky: float

    # Hardware conversion constant: 1 hardware unit = 0.732 RPM
    _RPM_PER_UNIT: float = 0.732
    _MAX_RPM: float = 255 * _RPM_PER_UNIT  # 186.66 RPM

    def to_list(self) -> list[float]:
        """Convert to list of floats in joint order.

        Returns:
            List of 6 motor speeds [thumb_flex, thumb_abd, index, middle, ring, pinky]
        """
        return [
            self.thumb_flex,
            self.thumb_abd,
            self.index,
            self.middle,
            self.ring,
            self.pinky,
        ]

    @classmethod
    def from_list(cls, values: list[float]) -> "O6Speed":
        """Construct from list of floats (0-100 range).

        Args:
            values: List of 6 float values in 0-100 range

        Returns:
            O6Speed instance

        Raises:
            ValueError: If list doesn't have exactly 6 elements
        """
        if len(values) != 6:
            raise ValueError(f"Expected 6 values, got {len(values)}")
        for value in values:
            if not isinstance(value, (float, int)):
                raise ValueError(f"Speed value {value} must be float/int")
            if value < 0 or value > 100:
                raise ValueError(f"Value {value} out of range [0, 100]")
        return cls(
            thumb_flex=values[0],
            thumb_abd=values[1],
            index=values[2],
            middle=values[3],
            ring=values[4],
            pinky=values[5],
        )

    def to_raw(self) -> list[int]:
        # Internal: Convert to hardware communication format
        # Use round() for better precision and clamp to valid range [0, 255]
        return [max(0, min(255, round(v * 255 / 100))) for v in self.to_list()]

    @classmethod
    def from_raw(cls, values: list[int]) -> "O6Speed":
        # Internal: Construct from hardware communication format
        if len(values) != 6:
            raise ValueError(f"Expected 6 values, got {len(values)}")
        for value in values:
            if value < 0 or value > 255:
                raise ValueError(f"Value {value} out of range [0, 255]")
        normalized = [v * 100 / 255 for v in values]
        return cls.from_list(normalized)

    def to_rpm(self) -> list[float]:
        """Convert to list of speeds in RPM units.

        Returns:
            List of 6 motor speeds in RPM [thumb_flex, thumb_abd, index, middle, ring, pinky]

        Example:
            >>> speed = O6Speed(50.0, 50.0, 50.0, 50.0, 50.0, 50.0)
            >>> rpm_values = speed.to_rpm()
            >>> print(rpm_values[0])  # ~93.33 RPM
        """
        return [v * self._MAX_RPM / 100 for v in self.to_list()]

    @classmethod
    def from_rpm(cls, rpm_values: list[float]) -> "O6Speed":
        """Construct from list of speeds in RPM units.

        Args:
            rpm_values: List of 6 speed values in RPM (0 to 186.66 RPM)

        Returns:
            O6Speed instance

        Raises:
            ValueError: If list doesn't have exactly 6 elements or values are out of range.

        Example:
            >>> # Set all motors to 90 RPM
            >>> speed = O6Speed.from_rpm([90.0, 90.0, 90.0, 90.0, 90.0, 90.0])
            >>> # Set different speeds per motor
            >>> speed = O6Speed.from_rpm([100.0, 80.0, 120.0, 120.0, 120.0, 120.0])
        """
        if len(rpm_values) != 6:
            raise ValueError(f"Expected 6 values, got {len(rpm_values)}")

        # Validate RPM values
        for i, rpm in enumerate(rpm_values):
            if rpm < 0 or rpm > cls._MAX_RPM:
                raise ValueError(
                    f"RPM value {i} ({rpm}) out of range [0, {cls._MAX_RPM:.2f}]"
                )

        # Convert RPM to 0-100 range
        normalized = [rpm * 100 / cls._MAX_RPM for rpm in rpm_values]
        return cls.from_list(normalized)

    def __getitem__(self, index: int) -> float:
        """Support indexing: speeds[0] returns thumb_flex.

        Args:
            index: Joint index (0-5)

        Returns:
            Motor speed value

        Raises:
            IndexError: If index is out of range
        """
        return self.to_list()[index]

    def __len__(self) -> int:
        """Return number of motors (always 6 for O6)."""
        return 6


@dataclass(frozen=True)
class SpeedData:
    """Immutable speed data container.

    Attributes:
        speeds: O6Speed instance containing motor speeds (0-100 range).
        timestamp: Unix timestamp when the data was received.
    """

    speeds: O6Speed
    timestamp: float


class SpeedManager:
    """Manager for motor speed control and sensing.

    This class provides three access modes for speed operations:
    1. Speed control: set_speeds() - send 6 target speeds and cache response
    2. Blocking mode: get_blocking() - request and wait for 6 current speeds
    3. Cache reading: get_snapshot() - non-blocking read of cached speeds
    """

    _CONTROL_CMD = 0x05
    _SENSE_CMD = [0x05]
    _SPEED_COUNT = 6

    def __init__(self, arbitration_id: int, dispatcher: CANMessageDispatcher) -> None:
        """Initialize the speed manager.

        Args:
            arbitration_id: CAN arbitration ID for speed control/sensing.
            dispatcher: CAN message dispatcher to use for communication.
        """
        self._arbitration_id = arbitration_id
        self._dispatcher = dispatcher
        self._dispatcher.subscribe(self._on_message)
        self._relay = DataRelay[SpeedData]()

    def set_speeds(self, speeds: O6Speed | list[float]) -> None:
        """Send target speeds to the robotic hand motors.

        Args:
            speeds: O6Speed instance or list of 6 target speeds (range 0-100 each).

        Raises:
            ValidationError: If speeds count is not 6 or values are out of range.

        Example:
            >>> manager.set_speeds(O6Speed(thumb_flex=50.0, thumb_abd=50.0,
            ...                            index=50.0, middle=50.0, ring=50.0, pinky=50.0))
            >>> manager.set_speeds([50.0, 50.0, 50.0, 50.0, 50.0, 50.0])
        """
        if isinstance(speeds, O6Speed):
            raw_speeds = speeds.to_raw()
        elif isinstance(speeds, list):
            raw_speeds = O6Speed.from_list(speeds).to_raw()
        else:
            raise ValidationError(
                f"Expected O6Speed or list, got {type(speeds).__name__}"
            )

        # Build and send message
        data = [self._CONTROL_CMD, *raw_speeds]
        msg = can.Message(
            arbitration_id=self._arbitration_id,
            data=data,
            is_extended_id=False,
        )
        self._dispatcher.send(msg)

    def get_blocking(self, timeout_ms: float = 100) -> SpeedData:
        """Request and wait for current motor speeds (blocking).

        Args:
            timeout_ms: Maximum time to wait in milliseconds (default: 100).

        Returns:
            SpeedData instance containing speeds and timestamp.

        Raises:
            TimeoutError: If no response is received within timeout.
            ValidationError: If timeout_ms is not positive.

        Example:
            >>> data = manager.get_blocking(timeout_ms=500)
            >>> print(f"Current speeds: {data.speeds}")
        """
        if timeout_ms <= 0:
            raise ValidationError("timeout_ms must be positive")
        self._send_sense_request()
        return self._relay.wait(timeout_ms / 1000.0)

    def get_snapshot(self) -> SpeedData | None:
        """Get the most recent cached speed data (non-blocking).

        Returns:
            SpeedData instance or None if no data received yet.

        Example:
            >>> data = manager.get_snapshot()
            >>> if data:
            ...     print(f"Fresh speeds: {data.speeds}")
        """
        return self._relay.snapshot()

    def _set_event_sink(self, sink: Callable[[SpeedData], None]) -> None:
        self._relay.set_sink(sink)

    def _send_sense_request(self) -> None:
        msg = can.Message(
            arbitration_id=self._arbitration_id,
            data=self._SENSE_CMD,
            is_extended_id=False,
        )
        self._dispatcher.send(msg)

    def _on_message(self, msg: can.Message) -> None:
        if msg.arbitration_id != self._arbitration_id:
            return

        if len(msg.data) < 2 or msg.data[0] != self._CONTROL_CMD:
            return

        raw_speeds = list(msg.data[1:])

        if len(raw_speeds) != self._SPEED_COUNT:
            return

        speeds = O6Speed.from_raw(raw_speeds)
        speed_data = SpeedData(speeds=speeds, timestamp=time.time())
        self._relay.push(speed_data)


@dataclass
class O6Acceleration:
    """Motor accelerations for O6 hand (0-100 range or deg/s²).

    Accelerations can be specified either as normalized 0-100 values or in deg/s² units.
    Maximum acceleration: 2209.8 deg/s² (corresponds to 100).

    Attributes:
        thumb_flex: Thumb flexion motor acceleration (0-100). Higher values = faster acceleration.
        thumb_abd: Thumb abduction motor acceleration (0-100). Higher values = faster acceleration.
        index: Index finger motor acceleration (0-100). Higher values = faster acceleration.
        middle: Middle finger motor acceleration (0-100). Higher values = faster acceleration.
        ring: Ring finger motor acceleration (0-100). Higher values = faster acceleration.
        pinky: Pinky finger motor acceleration (0-100). Higher values = faster acceleration.
    """

    thumb_flex: float
    thumb_abd: float
    index: float
    middle: float
    ring: float
    pinky: float

    # Hardware conversion constant: 1 hardware unit = 8.7 deg/s²
    _DEG_PER_SEC2_PER_UNIT: float = 8.7
    _MAX_DEG_PER_SEC2: float = 254 * _DEG_PER_SEC2_PER_UNIT  # 2209.8 deg/s²

    def to_list(self) -> list[float]:
        """Convert to list of floats in joint order.

        Returns:
            List of 6 motor accelerations [thumb_flex, thumb_abd, index, middle, ring, pinky]
        """
        return [
            self.thumb_flex,
            self.thumb_abd,
            self.index,
            self.middle,
            self.ring,
            self.pinky,
        ]

    @classmethod
    def from_list(cls, values: list[float]) -> "O6Acceleration":
        """Construct from list of floats (0-100 range).

        Args:
            values: List of 6 float values in 0-100 range

        Returns:
            O6Acceleration instance

        Raises:
            ValueError: If list doesn't have exactly 6 elements
        """
        if len(values) != 6:
            raise ValueError(f"Expected 6 values, got {len(values)}")
        for value in values:
            if not isinstance(value, (float, int)):
                raise ValueError(f"Acceleration value {value} must be float/int")
            if value < 0 or value > 100:
                raise ValueError(f"Value {value} out of range [0, 100]")
        return cls(
            thumb_flex=values[0],
            thumb_abd=values[1],
            index=values[2],
            middle=values[3],
            ring=values[4],
            pinky=values[5],
        )

    def to_raw(self) -> list[int]:
        # Internal: Convert to hardware communication format with special mapping
        # User sees 0-100 where 100 is max acceleration
        # Hardware has special mapping:
        #   - 0 = maximum acceleration (special value)
        #   - 1-254 = increasing acceleration (1 is min, 254 is near-max)
        # Mapping:
        #   - User 100 -> Hardware 0 (special case for maximum)
        #   - User 0-99 -> Hardware 1-254 (linear increasing)
        def convert_single(v: float) -> int:
            if v >= 100:
                return 0  # Maximum acceleration
            else:
                # Map 0-99 linearly to 1-254
                # v=0 -> 1, v=99 -> 254
                result = round(1 + v * 253 / 99)
                return max(1, min(254, result))  # Clamp to [1, 254]

        return [convert_single(v) for v in self.to_list()]

    @classmethod
    def from_raw(cls, values: list[int]) -> "O6Acceleration":
        # Internal: Construct from hardware communication format with special mapping
        # Hardware to user mapping:
        #   - Hardware 0 -> User 100 (special case)
        #   - Hardware 1-254 -> User 0-99 (linear increasing)
        if len(values) != 6:
            raise ValueError(f"Expected 6 values, got {len(values)}")
        for value in values:
            if value < 0 or value > 254:
                raise ValueError(f"Value {value} out of range [0, 254]")

        def convert_single(v: int) -> float:
            if v == 0:
                return 100.0  # Maximum acceleration
            else:
                # Map 1-254 to 0-99
                # hw=1 -> 0, hw=254 -> 99
                return (v - 1) * 99 / 253

        normalized = [convert_single(v) for v in values]
        return cls.from_list(normalized)

    def to_deg_per_sec2(self) -> list[float]:
        """Convert to list of accelerations in deg/s² units.

        Returns:
            List of 6 motor accelerations in deg/s² [thumb_flex, thumb_abd, index, middle, ring, pinky]

        Example:
            >>> accel = O6Acceleration(50.0, 50.0, 50.0, 50.0, 50.0, 50.0)
            >>> deg_s2_values = accel.to_deg_per_sec2()
            >>> print(deg_s2_values[0])  # ~1104.9 deg/s²
        """
        return [v * self._MAX_DEG_PER_SEC2 / 100 for v in self.to_list()]

    @classmethod
    def from_deg_per_sec2(cls, deg_per_sec2_values: list[float]) -> "O6Acceleration":
        """Construct from list of accelerations in deg/s² units.

        Args:
            deg_per_sec2_values: List of 6 acceleration values in deg/s² (0 to 2209.8 deg/s²)

        Returns:
            O6Acceleration instance

        Raises:
            ValueError: If list doesn't have exactly 6 elements or values are out of range.

        Example:
            >>> # Set all motors to 1000 deg/s²
            >>> accel = O6Acceleration.from_deg_per_sec2([1000.0] * 6)
            >>> # Set different accelerations per motor
            >>> accel = O6Acceleration.from_deg_per_sec2([1500.0, 1200.0, 1800.0, 1800.0, 1800.0, 1800.0])
        """
        if len(deg_per_sec2_values) != 6:
            raise ValueError(f"Expected 6 values, got {len(deg_per_sec2_values)}")

        # Validate acceleration values
        for i, acc in enumerate(deg_per_sec2_values):
            if acc < 0 or acc > cls._MAX_DEG_PER_SEC2:
                raise ValueError(
                    f"Acceleration value {i} ({acc}) out of range [0, {cls._MAX_DEG_PER_SEC2:.2f}]"
                )

        # Convert deg/s² to 0-100 range
        normalized = [acc * 100 / cls._MAX_DEG_PER_SEC2 for acc in deg_per_sec2_values]
        return cls.from_list(normalized)

    def __getitem__(self, index: int) -> float:
        """Support indexing: accelerations[0] returns thumb_flex.

        Args:
            index: Joint index (0-5)

        Returns:
            Motor acceleration value

        Raises:
            IndexError: If index is out of range
        """
        return self.to_list()[index]

    def __len__(self) -> int:
        """Return number of motors (always 6 for O6)."""
        return 6


@dataclass(frozen=True)
class AccelerationData:
    """Immutable acceleration data container.

    Attributes:
        accelerations: O6Acceleration instance containing motor accelerations (0-100 range).
        timestamp: Unix timestamp when the data was received.
    """

    accelerations: O6Acceleration
    timestamp: float


class AccelerationManager:
    """Manager for motor acceleration control and sensing.

    This class provides three access modes for acceleration operations:
    1. Acceleration control: set_accelerations() - send 6 target accelerations and cache response
    2. Blocking mode: get_blocking() - request and wait for 6 current accelerations
    3. Cache reading: get_snapshot() - non-blocking read of cached accelerations
    """

    _CONTROL_CMD = 0x87
    _SENSE_CMD = [0x87]
    _ACCELERATION_COUNT = 6

    def __init__(self, arbitration_id: int, dispatcher: CANMessageDispatcher) -> None:
        """Initialize the acceleration manager.

        Args:
            arbitration_id: CAN arbitration ID for acceleration control/sensing.
            dispatcher: CAN message dispatcher to use for communication.
        """
        self._arbitration_id = arbitration_id
        self._dispatcher = dispatcher
        self._dispatcher.subscribe(self._on_message)
        self._relay = DataRelay[AccelerationData]()

    def set_accelerations(self, accelerations: O6Acceleration | list[float]) -> None:
        """Send target accelerations to the robotic hand motors.

        Args:
            accelerations: O6Acceleration instance or list of 6 target accelerations
                (range 0-100 each, where 100 is maximum acceleration).

        Raises:
            ValidationError: If accelerations count is not 6 or values are out of range.

        Example:
            >>> manager.set_accelerations(O6Acceleration(thumb_flex=80.0, thumb_abd=80.0,
            ...                                          index=80.0, middle=80.0,
            ...                                          ring=80.0, pinky=80.0))
            >>> manager.set_accelerations([80.0, 80.0, 80.0, 80.0, 80.0, 80.0])
        """
        if isinstance(accelerations, O6Acceleration):
            raw_accelerations = accelerations.to_raw()
        elif isinstance(accelerations, list):
            # Validate input
            if len(accelerations) != self._ACCELERATION_COUNT:
                raise ValidationError(
                    f"Expected {self._ACCELERATION_COUNT} accelerations, got {len(accelerations)}"
                )
            # Validate acceleration values (0-100 range)
            for i, acceleration in enumerate(accelerations):
                if not isinstance(acceleration, (float, int)):
                    raise ValidationError(
                        f"Acceleration {i} must be float or int, got {type(acceleration)}"
                    )
            raw_accelerations = O6Acceleration.from_list(accelerations).to_raw()

        # Build and send message
        data = [self._CONTROL_CMD, *raw_accelerations]
        msg = can.Message(
            arbitration_id=self._arbitration_id,
            data=data,
            is_extended_id=False,
        )
        self._dispatcher.send(msg)

    def get_blocking(self, timeout_ms: float = 100) -> AccelerationData:
        """Request and wait for current motor accelerations (blocking).

        Args:
            timeout_ms: Maximum time to wait in milliseconds (default: 100).

        Returns:
            AccelerationData instance containing accelerations and timestamp.

        Raises:
            TimeoutError: If no response is received within timeout.
            ValidationError: If timeout_ms is not positive.

        Example:
            >>> data = manager.get_blocking(timeout_ms=500)
            >>> print(f"Current accelerations: {data.accelerations}")
        """
        if timeout_ms <= 0:
            raise ValidationError("timeout_ms must be positive")
        self._send_sense_request()
        return self._relay.wait(timeout_ms / 1000.0)

    def get_snapshot(self) -> AccelerationData | None:
        """Get the most recent cached acceleration data (non-blocking).

        Returns:
            AccelerationData instance or None if no data received yet.

        Example:
            >>> data = manager.get_snapshot()
            >>> if data:
            ...     print(f"Fresh accelerations: {data.accelerations}")
        """
        return self._relay.snapshot()

    def _set_event_sink(self, sink: Callable[[AccelerationData], None]) -> None:
        self._relay.set_sink(sink)

    def _send_sense_request(self) -> None:
        msg = can.Message(
            arbitration_id=self._arbitration_id,
            data=self._SENSE_CMD,
            is_extended_id=False,
        )
        self._dispatcher.send(msg)

    def _on_message(self, msg: can.Message) -> None:
        if msg.arbitration_id != self._arbitration_id:
            return

        if len(msg.data) < 2 or msg.data[0] != self._CONTROL_CMD:
            return

        raw_accelerations = list(msg.data[1:])

        if len(raw_accelerations) != self._ACCELERATION_COUNT:
            return

        accelerations = O6Acceleration.from_raw(raw_accelerations)
        acceleration_data = AccelerationData(
            accelerations=accelerations, timestamp=time.time()
        )
        self._relay.push(acceleration_data)
