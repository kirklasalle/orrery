"""
Integration Adapters for target platforms (OpenClaw, Hermes, Windows OS Agent).
"""

from orrery.adapters.base import BaseAdapter
from orrery.adapters.openclaw import OpenClawAdapter
from orrery.adapters.hermes import HermesAdapter
from orrery.adapters.windows_os import WindowsOSAdapter

__all__ = [
    "BaseAdapter",
    "OpenClawAdapter",
    "HermesAdapter",
    "WindowsOSAdapter",
]
