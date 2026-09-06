"""
Integration adapters.

Every adapter here is real: `FileSystemAdapter` performs sandboxed file I/O and
`ProcessAdapter` runs allowlisted programs. The three simulated adapters that used to live
here now sit in `examples/simulated/`, so a simulation cannot be imported by reflex while
scanning this package for integrations.
"""

from orrery.adapters.base import BaseAdapter
from orrery.adapters.conformance import ConformanceReport, run_conformance
from orrery.adapters.filesystem import FileSystemAdapter
from orrery.adapters.openrouter import OpenRouterAdapter
from orrery.adapters.process import ProcessAdapter

__all__ = [
    "BaseAdapter",
    "ConformanceReport",
    "run_conformance",
    "FileSystemAdapter",
    "OpenRouterAdapter",
    "ProcessAdapter",
]
