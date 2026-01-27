"""L6 robotic hand data types with user-friendly 0-100 range.

This module defines strongly-typed data classes for L6 hand joint control and sensing.
All values use a normalized 0-100 range for better user experience.
"""

from dataclasses import dataclass
from enum import Flag


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
        # Internal: Convert to hardware communication format
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
        # Internal: Construct from hardware communication format
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
        # Internal: Convert to hardware communication format
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
        # Internal: Construct from hardware communication format
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
        # Internal: Convert to hardware communication format
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
        # Internal: Construct from hardware communication format
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
        # Internal: Convert to hardware communication format
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
        # Internal: Construct from hardware communication format
        if len(values) != 6:
            raise ValueError(f"Expected 6 values, got {len(values)}")
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
        # Internal: Convert to hardware communication format
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
        # Internal: Construct from hardware communication format
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


class FaultCode(Flag):
    """Motor fault code flags.

    Each bit represents a specific fault condition:
    - BIT0 (1): Phase B overcurrent
    - BIT1 (2): Phase C overcurrent
    - BIT2 (4): Phase A overcurrent
    - BIT3 (8): Overload level 1
    - BIT4 (16): Overload level 2
    - BIT5 (32): Motor overtemperature
    - BIT6 (64): MCU overtemperature
    - BIT7 (128): Reserved
    """

    NONE = 0
    PHASE_B_OVERCURRENT = 1 << 0  # BIT0: Phase B overcurrent
    PHASE_C_OVERCURRENT = 1 << 1  # BIT1: Phase C overcurrent
    PHASE_A_OVERCURRENT = 1 << 2  # BIT2: Phase A overcurrent
    OVERLOAD_1 = 1 << 3  # BIT3: Overload level 1
    OVERLOAD_2 = 1 << 4  # BIT4: Overload level 2
    MOTOR_OVERTEMP = 1 << 5  # BIT5: Motor overtemperature
    MCU_OVERTEMP = 1 << 6  # BIT6: MCU overtemperature

    def has_fault(self) -> bool:
        """Check if this fault code has any fault.

        Returns:
            True if any fault bit is set, False otherwise.

        Example:
            >>> code = FaultCode.PHASE_A_OVERCURRENT | FaultCode.OVERLOAD_1
            >>> code.has_fault()
            True
            >>> FaultCode.NONE.has_fault()
            False
        """
        return self != FaultCode.NONE

    def get_fault_names(self) -> list[str]:
        """Get human-readable fault names for this fault code.

        Returns:
            List of fault names. Returns ["No faults"] if no faults are present.

        Example:
            >>> code = FaultCode.PHASE_A_OVERCURRENT | FaultCode.OVERLOAD_1
            >>> code.get_fault_names()
            ['Phase A overcurrent', 'Overload level 1']
            >>> FaultCode.NONE.get_fault_names()
            ['No faults']
        """
        if not self.has_fault():
            return ["No faults"]

        names: list[str] = []
        if self & FaultCode.PHASE_B_OVERCURRENT:
            names.append("Phase B overcurrent")
        if self & FaultCode.PHASE_C_OVERCURRENT:
            names.append("Phase C overcurrent")
        if self & FaultCode.PHASE_A_OVERCURRENT:
            names.append("Phase A overcurrent")
        if self & FaultCode.OVERLOAD_1:
            names.append("Overload level 1")
        if self & FaultCode.OVERLOAD_2:
            names.append("Overload level 2")
        if self & FaultCode.MOTOR_OVERTEMP:
            names.append("Motor overtemperature")
        if self & FaultCode.MCU_OVERTEMP:
            names.append("MCU overtemperature")
        return names


@dataclass
class L6Fault:
    """Joint fault codes for L6 hand.

    Each attribute is a FaultCode enum value representing the fault status
    for that joint. You can directly call methods on each joint's fault code.

    Attributes:
        thumb_flex: Thumb flexion motor fault code
        thumb_abd: Thumb abduction motor fault code
        index: Index finger motor fault code
        middle: Middle finger motor fault code
        ring: Ring finger motor fault code
        pinky: Pinky finger motor fault code

    Example:
        >>> faults = L6Fault(...)
        >>> # Check if thumb flex has any fault
        >>> if faults.thumb_flex.has_fault():
        ...     print(f"Thumb flex faults: {faults.thumb_flex.get_fault_names()}")
        >>> # Check all joints
        >>> if faults.has_any_fault():
        ...     print("Some joints have faults")
        >>> # Access via index
        >>> print(faults[0].get_fault_names())  # thumb_flex
    """

    thumb_flex: FaultCode
    thumb_abd: FaultCode
    index: FaultCode
    middle: FaultCode
    ring: FaultCode
    pinky: FaultCode

    def to_list(self) -> list[FaultCode]:
        """Convert to list of FaultCode in joint order.

        Returns:
            List of 6 joint fault codes [thumb_flex, thumb_abd, index, middle, ring, pinky]
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
        # Internal: Convert to hardware communication format
        return [int(code.value) & 0x7F for code in self.to_list()]

    @classmethod
    def from_list(cls, values: list[FaultCode]) -> "L6Fault":
        """Construct from list of FaultCode enum values.

        Args:
            values: List of 6 FaultCode values

        Returns:
            L6Fault instance

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
    def from_raw(cls, values: list[int]) -> "L6Fault":
        # Internal: Construct from hardware communication format
        if len(values) != 6:
            raise ValueError(f"Expected 6 values, got {len(values)}")
        fault_codes = [FaultCode(v & 0x7F) for v in values]
        return cls.from_list(fault_codes)

    def has_any_fault(self) -> bool:
        """Check if any joint has a fault.

        Returns:
            True if any joint has a fault, False otherwise.

        Example:
            >>> faults = L6Fault(...)
            >>> if faults.has_any_fault():
            ...     print("At least one joint has a fault")
        """
        return any(code.has_fault() for code in self.to_list())

    def __getitem__(self, index: int) -> FaultCode:
        """Support indexing: faults[0] returns thumb_flex.

        Args:
            index: Joint index (0-5)

        Returns:
            Joint fault code value

        Raises:
            IndexError: If index is out of range
        """
        return self.to_list()[index]

    def __len__(self) -> int:
        """Return number of joints (always 6 for L6)."""
        return 6
