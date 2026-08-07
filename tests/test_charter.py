"""
Charter integrity tests.

The drift these guard against is not hypothetical. When the Fourth Law's "conforms to" was
corrected to "violates" — a wording that as written forbade compliance — the fix landed in
two of the three charter documents and not the third, and nothing noticed.
"""

import json
import shutil
from pathlib import Path

import pytest

from orrery.core import charter
from orrery.core.charter import (
    CANONICAL_DOCUMENT,
    CHARTER_DOCUMENTS,
    LAW_ORDINALS,
    build_manifest,
    charter_digest,
    extract_laws,
    normalize_law,
    save_manifest,
    verify_charter,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def charter_copy(tmp_path):
    """A throwaway charter, so tests can break it without touching the real one."""
    root = tmp_path / "repo"
    (root / "config").mkdir(parents=True)
    for name in CHARTER_DOCUMENTS:
        shutil.copy(REPO_ROOT / name, root / name)
    save_manifest(build_manifest(root), root)
    return root


def test_every_document_states_the_same_ten_laws():
    """
    LAW10-CHARTER, run against the real repository.
    """
    result = verify_charter(REPO_ROOT)

    assert result.laws_checked == len(LAW_ORDINALS)
    assert result.verified, result.summary


def test_the_fourth_law_forbids_violation_not_compliance():
    """
    The specific defect, pinned in every document. As written with "conforms to", the Fourth
    Law required systems to prevent each other from obeying the first three.
    """
    for name in CHARTER_DOCUMENTS:
        laws = extract_laws((REPO_ROOT / name).read_text(encoding="utf-8"))
        fourth = normalize_law(laws[4])
        assert "violates any of the previous three laws" in fourth, name
        assert "conforms to any of the previous three laws" not in fourth, name


def test_a_reworded_law_is_detected(charter_copy):
    target = charter_copy / "Permanent_Active_Directives.txt"
    target.write_text(
        target.read_text(encoding="utf-8").replace(
            "that violates any of the previous three laws",
            "that conforms to any of the previous three laws",
        ),
        encoding="utf-8",
    )
    save_manifest(build_manifest(charter_copy), charter_copy)

    result = verify_charter(charter_copy)

    assert not result.verified
    assert [item.law for item in result.drift] == [4]
    assert result.drift[0].document == "Permanent_Active_Directives.txt"
    assert "conforms to" in result.drift[0].document_text


def test_presentation_differences_are_not_drift(charter_copy):
    """
    Tolerant of how a Law is written, intolerant of what it says. "An intelligence System"
    and "An Intelligence System" are the same Law; a different verb is not.
    """
    target = charter_copy / "AGENTIC_SACRED_COVENANT.md"
    text = target.read_text(encoding="utf-8")
    target.write_text(text.replace("An Intelligence System must obey", "an intelligence  system  MUST obey"), encoding="utf-8")
    save_manifest(build_manifest(charter_copy), charter_copy)

    assert verify_charter(charter_copy).verified


def test_an_edit_without_re_pinning_fails(charter_copy):
    """
    The manifest is what makes editing a Law a deliberate act rather than a quiet one.
    """
    assert verify_charter(charter_copy).verified

    target = charter_copy / CANONICAL_DOCUMENT
    target.write_text(target.read_text(encoding="utf-8") + "\nAn appended line.\n", encoding="utf-8")

    result = verify_charter(charter_copy)
    assert not result.verified
    assert result.digest_mismatches == [CANONICAL_DOCUMENT]

    save_manifest(build_manifest(charter_copy), charter_copy)
    assert verify_charter(charter_copy).verified


def test_an_unpinned_document_is_a_failure(charter_copy):
    manifest = json.loads((charter_copy / "config/charter_manifest.json").read_text(encoding="utf-8"))
    del manifest["documents"]["AGENTIC_SACRED_COVENANT.md"]
    (charter_copy / "config/charter_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    result = verify_charter(charter_copy)
    assert not result.verified
    assert result.unpinned_documents == ["AGENTIC_SACRED_COVENANT.md"]


def test_a_missing_document_is_a_failure_not_a_pass(charter_copy):
    (charter_copy / "Permanent_Active_Directives.txt").unlink()

    result = verify_charter(charter_copy)
    assert not result.verified
    assert result.missing_documents == ["Permanent_Active_Directives.txt"]


def test_a_dropped_law_is_detected(charter_copy):
    target = charter_copy / "AGENTIC_SACRED_COVENANT.md"
    laws = extract_laws(target.read_text(encoding="utf-8"))
    target.write_text(
        target.read_text(encoding="utf-8").replace(f"10. **Tenth Law:** {laws[10]}", ""),
        encoding="utf-8",
    )
    save_manifest(build_manifest(charter_copy), charter_copy)

    result = verify_charter(charter_copy)
    assert not result.verified
    assert any("does not state Law 10" in entry for entry in result.missing_laws)


def test_charter_digest_changes_when_a_law_changes(charter_copy):
    before = charter_digest(charter_copy)

    target = charter_copy / CANONICAL_DOCUMENT
    target.write_text(
        target.read_text(encoding="utf-8").replace("Human preservation and safety is paramount.", "Whatever."),
        encoding="utf-8",
    )

    assert charter_digest(charter_copy) != before


def test_the_attestation_covers_the_charter(charter_copy, monkeypatch):
    """
    Approving a configuration approves the charter it runs under, so rewriting a Law
    invalidates the signature.
    """
    from orrery.core import attestation
    from orrery.core.config import Settings

    settings = Settings()
    monkeypatch.setattr(attestation, "charter_digest", lambda: charter_digest(charter_copy))
    before = attestation.configuration_digest(settings)

    target = charter_copy / CANONICAL_DOCUMENT
    target.write_text(
        target.read_text(encoding="utf-8").replace("Human preservation and safety is paramount.", "Whatever."),
        encoding="utf-8",
    )

    assert attestation.configuration_digest(settings) != before


def test_the_digest_does_not_depend_on_line_endings(tmp_path):
    """
    These documents are stored LF and check out CRLF on Windows. Hashing raw bytes made the
    manifest platform-specific, so a manifest pinned on Windows failed on a Linux runner and
    vice versa. A charter does not change meaning because a checkout added carriage returns.
    """
    lf = tmp_path / "lf.md"
    crlf = tmp_path / "crlf.md"
    body = "1. **First Law:** Something.\n2. **Second Law:** Something else.\n"
    lf.write_bytes(body.encode("utf-8"))
    crlf.write_bytes(body.replace("\n", "\r\n").encode("utf-8"))

    assert lf.read_bytes() != crlf.read_bytes()
    assert charter.document_digest(lf) == charter.document_digest(crlf)


def test_charter_cli_reports_and_repins(charter_copy, capsys):
    from orrery.tools import charter as charter_cli

    assert charter_cli.main(["--root", str(charter_copy)]) == 0
    assert "CONSISTENT" in capsys.readouterr().out

    target = charter_copy / CANONICAL_DOCUMENT
    target.write_text(target.read_text(encoding="utf-8") + "\ntrailing\n", encoding="utf-8")

    assert charter_cli.main(["--root", str(charter_copy)]) == 1
    assert "has changed since it was pinned" in capsys.readouterr().err

    assert charter_cli.main(["--root", str(charter_copy), "--update"]) == 0
    assert charter_cli.main(["--root", str(charter_copy)]) == 0


def test_charter_cli_can_print_the_canonical_laws(capsys):
    from orrery.tools import charter as charter_cli

    assert charter_cli.main(["--show"]) == 0
    printed = capsys.readouterr().out
    assert printed.count("Law") >= 0
    assert "Human preservation and safety is paramount" in printed


def test_governance_registry_law_count_matches_the_charter():
    """
    The registry claims to cover 10 Laws. The charter is where that number comes from.
    """
    from orrery.core.governance import coverage_by_law

    laws = extract_laws((REPO_ROOT / CANONICAL_DOCUMENT).read_text(encoding="utf-8"))
    assert set(coverage_by_law()) == set(laws)
