"""
Integration adapters.

`FileSystemAdapter` is real. `OpenClawAdapter`, `HermesAdapter`, and `WindowsOSAdapter` are
simulations and declare themselves as such.
"""

from orrery.adapters.base import BaseAdapter
from orrery.adapters.conformance import ConformanceReport, run_conformance
from orrery.adapters.filesystem import FileSystemAdapter
from orrery.adapters.openclaw import OpenClawAdapter
from orrery.adapters.hermes import HermesAdapter
from orrery.adapters.windows_os import WindowsOSAdapter

__all__ = [
    "BaseAdapter",
    "ConformanceReport",
    "run_conformance",
    "FileSystemAdapter",
    "OpenClawAdapter",
    "HermesAdapter",
    "WindowsOSAdapter",
]
