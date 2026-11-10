"""Host power-off used when the runtime enters Shutdown.

Other devices that need a graceful stop belong next to the Raspberry Pi halt
in ``CoolingRuntime._shutdown_devices``.
"""

from __future__ import annotations

import os
import sys


def raspberry_pi_halt_command() -> list[str] | None:
    """Argv that halts the Pi, or None when this process is not on Linux.

    Root calls ``shutdown`` directly. Otherwise ``sudo -n`` is used so a
    missing password fails instead of waiting.
    """
    if sys.platform != "linux":
        return None
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        return ["shutdown", "-h", "now"]
    return ["sudo", "-n", "shutdown", "-h", "now"]
