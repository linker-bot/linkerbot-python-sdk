from enum import Enum, auto


class ControlMode(Enum):
    """Arm / joint control mode.

    ``PP``
        Profile Position (trapezoidal profile inside the driver).
    ``MIT``
        Operation-control / MIT impedance mode (``run_mode=0`` on RS00
        private protocol). Host streams ``(p, v, kp, kd, t_ff)`` each
        cycle. Not the separate RS00 "MIT protocol" (standard-frame
        protocol switch via comm type 25).
    ``CSP``
        Cyclic Synchronous Position (``run_mode=5``). Host streams
        ``loc_ref``; speed capped by ``limit_spd`` (``0x7017``).
    """

    PP = auto()
    MIT = auto()
    CSP = auto()
