try:
    from .kinetix import ArmKinetix
except ImportError as exc:
    raise ImportError(
        "ArmKinetix requires the 'kinetix' extra (Pinocchio). "
        "Install it with: pip install linkerbot-py[kinetix]\n"
        "Note: Pinocchio does not support pip install on Windows. "
        "Use conda instead: conda install pinocchio -c conda-forge"
    ) from exc

__all__ = ["ArmKinetix"]
