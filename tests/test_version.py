"""
One version, stated in five places, checked in one.

`pyproject.toml`, `orrery.__version__`, both settings profiles, and the CHANGELOG each
carry the version independently. They drifted once already — the config files sat at 0.1.0
while the package said 0.2.0 — and a version that disagrees with itself is the same class
of defect as a governance document that outruns its code.
"""

import re
from pathlib import Path

import yaml

import orrery

REPO_ROOT = Path(__file__).resolve().parents[1]
_SEMVER = re.compile(r"^\d+\.\d+\.\d+$")


def _pyproject_version() -> str:
    # Regex rather than tomllib: the declared floor is Python 3.10, where tomllib is absent.
    text = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    assert match, "pyproject.toml declares no version"
    return match.group(1)


def _settings_version(name: str) -> str:
    raw = yaml.safe_load((REPO_ROOT / "config" / name).read_text(encoding="utf-8"))
    return str((raw.get("app") or {}).get("version", ""))


def _changelog_version() -> str:
    text = (REPO_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    match = re.search(r"^## \[(\d+\.\d+\.\d+)\]", text, re.MULTILINE)
    assert match, "CHANGELOG.md records no released version"
    return match.group(1)


def test_the_version_is_a_semantic_version():
    assert _SEMVER.match(orrery.__version__), orrery.__version__


def test_every_place_that_states_the_version_agrees():
    stated = {
        "orrery.__version__": orrery.__version__,
        "pyproject.toml": _pyproject_version(),
        "config/settings.yaml": _settings_version("settings.yaml"),
        "config/hardened.yaml": _settings_version("hardened.yaml"),
        "CHANGELOG.md": _changelog_version(),
    }

    assert len(set(stated.values())) == 1, f"version disagreement: {stated}"


def test_the_released_version_is_described_in_the_changelog():
    """
    A version with no changelog entry is a release nobody can read.
    """
    text = (REPO_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")

    assert f"## [{orrery.__version__}]" in text
    heading = re.search(rf"^## \[{re.escape(orrery.__version__)}\] - (\d{{4}}-\d{{2}}-\d{{2}})", text, re.MULTILINE)
    assert heading, "the released version must carry a date"
