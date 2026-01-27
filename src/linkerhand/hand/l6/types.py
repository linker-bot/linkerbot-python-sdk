"""L6 robotic hand data types with user-friendly 0-100 range.

This module defines strongly-typed data classes for L6 hand joint control and sensing.
All values use a normalized 0-100 range for better user experience.
"""

from dataclasses import dataclass


@dataclass
class L6Angle:
    """Joint angles for L6 hand (0-100 range).

    Attributes:
        thumb_flex: Thumb flexion joint angle (0-100)
        thumb_abd: Thumb abduction joint angle (0-100)
        index: Index finger flexion joint angle (0-100)
        middle: Middle finger flexion joint angle (0-100)
        ring: Ring finger flexion joint angle (0-100)
        pinky: Pinky finger flexion joint angle (0-100)
    """

    thumb_flex: float
    thumb_abd: float
    index: float
    middle: float
    ring: float
    pinky: float

    def to_list(self) -> list[float]:
        """Convert to list of floats in joint order.

        Returns:
            List of 6 joint angles [thumb_flex, thumb_abd, index, middle, ring, pinky]
        """
        return [
            self.thumb_flex,
            self.thumb_abd,
            self.index,
            self.middle,
            self.ring,
            self.pinky,
        ]

    def to_raw(self) -> list[int]:
        """Convert to raw CAN protocol format (0-255).

        Returns:
            List of 6 integers in 0-255 range for CAN communication
        """
        return [int(v * 255 / 100) for v in self.to_list()]

    @classmethod
    def from_list(cls, values: list[float]) -> "L6Angle":
        """Construct from list of floats (0-100 range).

        Args:
            values: List of 6 float values in 0-100 range

        Returns:
            L6Angle instance

        Raises:
            ValueError: If list doesn't have exactly 6 elements
        """
        if len(values) != 6:
            raise ValueError(f"Expected 6 values, got {len(values)}")
        return cls(
            thumb_flex=values[0],
            thumb_abd=values[1],
            index=values[2],
            middle=values[3],
            ring=values[4],
            pinky=values[5],
        )

    @classmethod
    def from_raw(cls, values: list[int]) -> "L6Angle":
        """Construct from raw CAN protocol format (0-255).

        Args:
            values: List of 6 integers in 0-255 range

        Returns:
            L6Angle instance with values converted to 0-100 range

        Raises:
            ValueError: If list doesn't have exactly 6 elements
        """
        if len(values) != 6:
            raise ValueError(f"Expected 6 values, got {len(values)}")
        normalized = [v * 100 / 255 for v in values]
        return cls.from_list(normalized)

    def __getitem__(self, index: int) -> float:
        """Support indexing: angles[0] returns thumb_flex.

        Args:
            index: Joint index (0-5)

        Returns:
            Joint angle value

        Raises:
            IndexError: If index is out of range
        """
        return self.to_list()[index]

    def __len__(self) -> int:
        """Return number of joints (always 6 for L6)."""
        return 6


@dataclass
class L6Torque:
    """Joint torques for L6 hand (0-100 range).

    Attributes:
        thumb_flex: Thumb flexion joint torque (0-100)
        thumb_abd: Thumb abduction joint torque (0-100)
        index: Index finger flexion joint torque (0-100)
        middle: Middle finger flexion joint torque (0-100)
        ring: Ring finger flexion joint torque (0-100)
        pinky: Pinky finger flexion joint torque (0-100)
    """

    thumb_flex: float
    thumb_abd: float
    index: float
    middle: float
    ring: float
    pinky: float

    def to_list(self) -> list[float]:
        """Convert to list of floats in joint order.

        Returns:
            List of 6 joint torques [thumb_flex, thumb_abd, index, middle, ring, pinky]
        """
        return [
            self.thumb_flex,
            self.thumb_abd,
            self.index,
            self.middle,
            self.ring,
            self.pinky,
        ]

    def to_raw(self) -> list[int]:
        """Convert to raw CAN protocol format (0-255).

        Returns:
            List of 6 integers in 0-255 range for CAN communication
        """
        return [int(v * 255 / 100) for v in self.to_list()]

    @classmethod
    def from_list(cls, values: list[float]) -> "L6Torque":
        """Construct from list of floats (0-100 range).

        Args:
            values: List of 6 float values in 0-100 range

        Returns:
            L6Torque instance

        Raises:
            ValueError: If list doesn't have exactly 6 elements
        """
        if len(values) != 6:
            raise ValueError(f"Expected 6 values, got {len(values)}")
        return cls(
            thumb_flex=values[0],
            thumb_abd=values[1],
            index=values[2],
            middle=values[3],
            ring=values[4],
            pinky=values[5],
        )

    @classmethod
    def from_raw(cls, values: list[int]) -> "L6Torque":
        """Construct from raw CAN protocol format (0-255).

        Args:
            values: List of 6 integers in 0-255 range

        Returns:
            L6Torque instance with values converted to 0-100 range

        Raises:
            ValueError: If list doesn't have exactly 6 elements
        """
        if len(values) != 6:
            raise ValueError(f"Expected 6 values, got {len(values)}")
        normalized = [v * 100 / 255 for v in values]
        return cls.from_list(normalized)

    def __getitem__(self, index: int) -> float:
        """Support indexing: torques[0] returns thumb_flex.

        Args:
            index: Joint index (0-5)

        Returns:
            Joint torque value

        Raises:
            IndexError: If index is out of range
        """
        return self.to_list()[index]

    def __len__(self) -> int:
        """Return number of joints (always 6 for L6)."""
        return 6


@dataclass
class L6Speed:
    """Motor speeds for L6 hand (0-100 range).

    Attributes:
        thumb_flex: Thumb flexion motor speed (0-100)
        thumb_abd: Thumb abduction motor speed (0-100)
        index: Index finger motor speed (0-100)
        middle: Middle finger motor speed (0-100)
        ring: Ring finger motor speed (0-100)
        pinky: Pinky finger motor speed (0-100)
    """

    thumb_flex: float
    thumb_abd: float
    index: float
    middle: float
    ring: float
    pinky: float

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

    def to_raw(self) -> list[int]:
        """Convert to raw CAN protocol format (0-255).

        Returns:
            List of 6 integers in 0-255 range for CAN communication
        """
        return [int(v * 255 / 100) for v in self.to_list()]

    @classmethod
    def from_list(cls, values: list[float]) -> "L6Speed":
        """Construct from list of floats (0-100 range).

        Args:
            values: List of 6 float values in 0-100 range

        Returns:
            L6Speed instance

        Raises:
            ValueError: If list doesn't have exactly 6 elements
        """
        if len(values) != 6:
            raise ValueError(f"Expected 6 values, got {len(values)}")
        return cls(
            thumb_flex=values[0],
            thumb_abd=values[1],
            index=values[2],
            middle=values[3],
            ring=values[4],
            pinky=values[5],
        )

    @classmethod
    def from_raw(cls, values: list[int]) -> "L6Speed":
        """Construct from raw CAN protocol format (0-255).

        Args:
            values: List of 6 integers in 0-255 range

        Returns:
            L6Speed instance with values converted to 0-100 range

        Raises:
            ValueError: If list doesn't have exactly 6 elements
        """
        if len(values) != 6:
            raise ValueError(f"Expected 6 values, got {len(values)}")
        normalized = [v * 100 / 255 for v in values]
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
        """Return number of motors (always 6 for L6)."""
        return 6


@dataclass
class L6Temperature:
    """Motor temperatures for L6 hand in degrees Celsius (°C).

    All values represent actual motor temperature in degrees Celsius.
    CAN protocol values (0-255) directly correspond to temperature in °C.

    Attributes:
        thumb_flex: Thumb flexion motor temperature in °C
        thumb_abd: Thumb abduction motor temperature in °C
        index: Index finger motor temperature in °C
        middle: Middle finger motor temperature in °C
        ring: Ring finger motor temperature in °C
        pinky: Pinky finger motor temperature in °C
    """

    thumb_flex: float
    thumb_abd: float
    index: float
    middle: float
    ring: float
    pinky: float

    def to_list(self) -> list[float]:
        """Convert to list of floats in joint order.

        Returns:
            List of 6 temperatures in °C [thumb_flex, thumb_abd, index, middle, ring, pinky]
        """
        return [
            self.thumb_flex,
            self.thumb_abd,
            self.index,
            self.middle,
            self.ring,
            self.pinky,
        ]

    def to_raw(self) -> list[int]:
        """Convert to raw CAN protocol format (0-255).

        Temperature in °C is directly converted to integer for CAN communication.

        Returns:
            List of 6 integers in 0-255 range for CAN communication
        """
        return [int(v) for v in self.to_list()]

    @classmethod
    def from_list(cls, values: list[float]) -> "L6Temperature":
        """Construct from list of floats in degrees Celsius.

        Args:
            values: List of 6 float values in °C

        Returns:
            L6Temperature instance

        Raises:
            ValueError: If list doesn't have exactly 6 elements
        """
        if len(values) != 6:
            raise ValueError(f"Expected 6 values, got {len(values)}")
        return cls(
            thumb_flex=values[0],
            thumb_abd=values[1],
            index=values[2],
            middle=values[3],
            ring=values[4],
            pinky=values[5],
        )

    @classmethod
    def from_raw(cls, values: list[int]) -> "L6Temperature":
        """Construct from raw CAN protocol format (0-255).

        CAN values directly represent temperature in degrees Celsius.

        Args:
            values: List of 6 integers in 0-255 range (representing °C)

        Returns:
            L6Temperature instance with temperatures in °C

        Raises:
            ValueError: If list doesn't have exactly 6 elements
        """
        if len(values) != 6:
            raise ValueError(f"Expected 6 values, got {len(values)}")
        # CAN values directly represent temperature in Celsius
        temperatures_celsius = [float(v) for v in values]
        return cls.from_list(temperatures_celsius)

    def __getitem__(self, index: int) -> float:
        """Support indexing: temperatures[0] returns thumb_flex.

        Args:
            index: Joint index (0-5)

        Returns:
            Temperature value

        Raises:
            IndexError: If index is out of range
        """
        return self.to_list()[index]

    def __len__(self) -> int:
        """Return number of temperature sensors (always 6 for L6)."""
        return 6


@dataclass
class L6Current:
    """Motor currents for L6 hand in milliamps (mA).

    All values represent actual motor current in milliamps.
    Conversion from CAN protocol: current_mA = (CAN_value × 1400) ÷ 255

    Attributes:
        thumb_flex: Thumb flexion motor current in mA
        thumb_abd: Thumb abduction motor current in mA
        index: Index finger motor current in mA
        middle: Middle finger motor current in mA
        ring: Ring finger motor current in mA
        pinky: Pinky finger motor current in mA
    """

    thumb_flex: float
    thumb_abd: float
    index: float
    middle: float
    ring: float
    pinky: float

    def to_list(self) -> list[float]:
        """Convert to list of floats in joint order.

        Returns:
            List of 6 currents [thumb_flex, thumb_abd, index, middle, ring, pinky]
        """
        return [
            self.thumb_flex,
            self.thumb_abd,
            self.index,
            self.middle,
            self.ring,
            self.pinky,
        ]

    def to_raw(self) -> list[int]:
        """Convert to raw CAN protocol format (0-255).

        Conversion formula: CAN_value = (current_mA × 255) ÷ 1400

        Returns:
            List of 6 integers in 0-255 range for CAN communication
        """
        return [int(v * 255 / 1400) for v in self.to_list()]

    @classmethod
    def from_list(cls, values: list[float]) -> "L6Current":
        """Construct from list of floats in milliamps.

        Args:
            values: List of 6 float values in mA

        Returns:
            L6Current instance

        Raises:
            ValueError: If list doesn't have exactly 6 elements
        """
        if len(values) != 6:
            raise ValueError(f"Expected 6 values, got {len(values)}")
        return cls(
            thumb_flex=values[0],
            thumb_abd=values[1],
            index=values[2],
            middle=values[3],
            ring=values[4],
            pinky=values[5],
        )

    @classmethod
    def from_raw(cls, values: list[int]) -> "L6Current":
        """Construct from raw CAN protocol format (0-255).

        Conversion formula: current_mA = (CAN_value × 1400) ÷ 255

        Args:
            values: List of 6 integers in 0-255 range

        Returns:
            L6Current instance with values converted to milliamps

        Raises:
            ValueError: If list doesn't have exactly 6 elements
        """
        if len(values) != 6:
            raise ValueError(f"Expected 6 values, got {len(values)}")
        currents_mA = [v * 1400 / 255 for v in values]
        return cls.from_list(currents_mA)

    def __getitem__(self, index: int) -> float:
        """Support indexing: currents[0] returns thumb_flex.

        Args:
            index: Joint index (0-5)

        Returns:
            Current value

        Raises:
            IndexError: If index is out of range
        """
        return self.to_list()[index]

    def __len__(self) -> int:
        """Return number of current sensors (always 6 for L6)."""
        return 6
