"""Custom exceptions for the Linkerbot SDK.

This module defines the exception hierarchy used throughout the SDK for
consistent error handling and reporting.
"""


class LinkerbotError(Exception):
    """Base exception for all Linkerbot SDK errors.

    All custom exceptions in the SDK inherit from this base class,
    making it easy to catch all SDK-related errors.
    """

    pass


class TimeoutError(LinkerbotError):
    """Raised when an operation times out.

    This exception is raised when a blocking operation (such as waiting for
    sensor data) does not complete within the specified timeout period.
    """

    pass


class CANError(LinkerbotError):
    """Raised when a CAN communication error occurs.

    This exception is raised for errors related to CAN bus communication,
    such as failed message sends or bus errors.
    """

    pass


class ValidationError(LinkerbotError):
    """Raised when input validation fails.

    This exception is raised when provided data does not meet the required
    format, range, or type constraints.
    """

    pass


class StateError(LinkerbotError):
    """Raised when an operation is attempted in an invalid state.

    This exception is raised when attempting operations that are not valid
    in the current state (e.g., starting streaming when already streaming).
    """

    pass
