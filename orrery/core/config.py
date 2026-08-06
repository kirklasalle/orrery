"""
Runtime settings loaded from config/settings.yaml.
"""

from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Optional
import logging
import os

import yaml
from pydantic import BaseModel, Field

from orrery.core.types import CycleTier

logger = logging.getLogger(__name__)

# Repository layout: orrery/core/config.py -> <root>/config/settings.yaml
_BUNDLED_SETTINGS_PATH = Path(__file__).resolve().parents[2] / "config" / "settings.yaml"

_DEFAULT_TIER_TIMEOUTS: Dict[CycleTier, float] = {
    CycleTier.META: 300.0,
    CycleTier.MACRO: 120.0,
    CycleTier.MESO: 60.0,
    CycleTier.MICRO: 15.0,
}


class DispatcherSettings(BaseModel):
    max_cycle_iterations: int = 50
    auto_checkpoint: bool = True


class CritiqueSettings(BaseModel):
    threshold: float = 0.70
    strict_mode: bool = False


class CheckpointSettings(BaseModel):
    max_checkpoints_in_memory: int = 100
    storage_dir: str = ".checkpoints"


class BacktrackingSettings(BaseModel):
    max_retries_per_step: int = 3


class Settings(BaseModel):
    dispatcher: DispatcherSettings = Field(default_factory=DispatcherSettings)
    critique: CritiqueSettings = Field(default_factory=CritiqueSettings)
    checkpointing: CheckpointSettings = Field(default_factory=CheckpointSettings)
    backtracking: BacktrackingSettings = Field(default_factory=BacktrackingSettings)
    tier_timeouts: Dict[CycleTier, float] = Field(default_factory=lambda: dict(_DEFAULT_TIER_TIMEOUTS))
    allow_simulated_adapters: bool = True

    def timeout_for(self, tier: CycleTier) -> float:
        return self.tier_timeouts.get(tier, _DEFAULT_TIER_TIMEOUTS[CycleTier.MICRO])


def _read_yaml(path: Path) -> Dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return yaml.safe_load(handle) or {}
    except FileNotFoundError:
        logger.warning("Settings file not found at %s; using built-in defaults.", path)
    except (yaml.YAMLError, OSError) as exc:
        logger.error("Could not read settings from %s (%s); using built-in defaults.", path, exc)
    return {}


def load_settings(path: Optional[Path] = None) -> Settings:
    """
    Builds Settings from a YAML file, falling back to defaults for anything absent.
    The ORRERY_SETTINGS environment variable overrides the bundled path.
    """
    if path is None:
        env_path = os.environ.get("ORRERY_SETTINGS")
        path = Path(env_path) if env_path else _BUNDLED_SETTINGS_PATH

    raw = _read_yaml(Path(path))
    meta_skills = raw.get("meta_skills") or {}

    tier_timeouts = dict(_DEFAULT_TIER_TIMEOUTS)
    for tier in CycleTier:
        tier_config = (raw.get("tiers") or {}).get(tier.value.lower()) or {}
        if "timeout_seconds" in tier_config:
            tier_timeouts[tier] = float(tier_config["timeout_seconds"])

    return Settings(
        dispatcher=DispatcherSettings(**(raw.get("dispatcher") or {})),
        critique=CritiqueSettings(**(meta_skills.get("critique") or {})),
        checkpointing=CheckpointSettings(**(meta_skills.get("checkpointing") or {})),
        backtracking=BacktrackingSettings(**(meta_skills.get("backtracking") or {})),
        tier_timeouts=tier_timeouts,
        allow_simulated_adapters=bool((raw.get("adapters") or {}).get("allow_simulated", True)),
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return load_settings()


def reload_settings() -> Settings:
    get_settings.cache_clear()
    return get_settings()
