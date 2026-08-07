"""
Runtime settings loaded from config/settings.yaml.
"""

from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional
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
    max_checkpoints_on_disk_per_cycle: int = 50
    storage_dir: str = ".checkpoints"


class IntegritySettings(BaseModel):
    verify_on_load: bool = True
    require_signature: bool = False
    require_asymmetric: bool = False


class DelegationSettings(BaseModel):
    max_depth: int = 4
    max_children_per_cycle: int = 8
    max_total_cycles: int = 32
    enforce_tier_descent: bool = True


class LedgerSettings(BaseModel):
    persist: bool = True
    storage_dir: str = ".ledger"


class ApprovalSettings(BaseModel):
    require_for_irreversible: bool = True
    require_for_compensable: bool = False
    require_signed: bool = False
    require_asymmetric: bool = False
    ttl_seconds: float = 900.0


class GovernanceSettings(BaseModel):
    require_attestation: bool = False
    attestation_path: str = "config/attestation.json"


class ProhibitionSettings(BaseModel):
    reason: str
    adapters: List[str] = Field(default_factory=list)
    actions: List[str] = Field(default_factory=list)
    paths: List[str] = Field(default_factory=list)


class InterdictionSettings(BaseModel):
    halt_file: str = ".halt"
    protect_runtime_paths: bool = True
    prohibitions: List[ProhibitionSettings] = Field(default_factory=list)


class QuarantineSettings(BaseModel):
    enabled: bool = False
    store: str = "config/classifications.json"
    record_path: str = ".quarantine/held.jsonl"
    require_signed: bool = False


class EnvelopeSettings(BaseModel):
    enforce: bool = False
    paths: List[str] = Field(default_factory=list)


class InvariantSettings(BaseModel):
    on_breach: str = "record"
    rules: List[Dict[str, Any]] = Field(default_factory=list)


class BacktrackingSettings(BaseModel):
    max_retries_per_step: int = 3


class Settings(BaseModel):
    dispatcher: DispatcherSettings = Field(default_factory=DispatcherSettings)
    critique: CritiqueSettings = Field(default_factory=CritiqueSettings)
    checkpointing: CheckpointSettings = Field(default_factory=CheckpointSettings)
    integrity: IntegritySettings = Field(default_factory=IntegritySettings)
    delegation: DelegationSettings = Field(default_factory=DelegationSettings)
    ledger: LedgerSettings = Field(default_factory=LedgerSettings)
    approval: ApprovalSettings = Field(default_factory=ApprovalSettings)
    governance: GovernanceSettings = Field(default_factory=GovernanceSettings)
    interdiction: InterdictionSettings = Field(default_factory=InterdictionSettings)
    quarantine: QuarantineSettings = Field(default_factory=QuarantineSettings)
    envelope: EnvelopeSettings = Field(default_factory=EnvelopeSettings)
    invariants: InvariantSettings = Field(default_factory=InvariantSettings)
    backtracking: BacktrackingSettings = Field(default_factory=BacktrackingSettings)
    tier_timeouts: Dict[CycleTier, float] = Field(default_factory=lambda: dict(_DEFAULT_TIER_TIMEOUTS))
    # A fresh install should not accept fabricated receipts without being asked.
    allow_simulated_adapters: bool = False

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
        integrity=IntegritySettings(**(meta_skills.get("integrity") or {})),
        delegation=DelegationSettings(**(raw.get("delegation") or {})),
        ledger=LedgerSettings(**(raw.get("ledger") or {})),
        approval=ApprovalSettings(**(raw.get("approval") or {})),
        governance=GovernanceSettings(**(raw.get("governance") or {})),
        interdiction=InterdictionSettings(**(raw.get("interdiction") or {})),
        quarantine=QuarantineSettings(**(raw.get("quarantine") or {})),
        envelope=EnvelopeSettings(**(raw.get("envelope") or {})),
        invariants=InvariantSettings(**(raw.get("invariants") or {})),
        backtracking=BacktrackingSettings(**(meta_skills.get("backtracking") or {})),
        tier_timeouts=tier_timeouts,
        allow_simulated_adapters=bool((raw.get("adapters") or {}).get("allow_simulated", False)),
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return load_settings()


def reload_settings() -> Settings:
    get_settings.cache_clear()
    return get_settings()
