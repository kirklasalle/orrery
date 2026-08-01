"""
Integration Adapters for target platforms (OpenClaw, Hermes, Windows OS Agent).
"""

from src.adapters.base import BaseAdapter
from src.adapters.openclaw import OpenClawAdapter
from src.adapters.hermes import HermesAdapter
from src.adapters.windows_os import WindowsOSAdapter

__all__ = [
    "BaseAdapter",
    "OpenClawAdapter",
    "HermesAdapter",
    "WindowsOSAdapter",
]
