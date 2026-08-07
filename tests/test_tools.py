"""
Tests for the operator CLIs.

Mostly about refusals. Overwriting a private key silently invalidates every approval it
ever signed, and that is not a thing a tool should do because a flag was forgotten.
"""

import json

import pytest

from orrery.core import signing
from orrery.tools import attest as attest_cli
from orrery.tools import keygen


def test_keygen_writes_a_private_key_and_registers_the_public_half(tmp_path, capsys):
    key_file = tmp_path / "alice.key"
    keyring = tmp_path / "operators.json"

    assert keygen.main(
        ["--operator", "alice", "--private-key", str(key_file), "--keyring", str(keyring)]
    ) == 0

    private_hex = key_file.read_text(encoding="utf-8").strip()
    operators = json.loads(keyring.read_text(encoding="utf-8"))["operators"]

    signer = signing.OperatorSigner("alice", bytes.fromhex(private_hex))
    assert operators["alice"] == signer.public_key_hex()
    assert private_hex not in capsys.readouterr().out, "a private key must never be printed"


def test_keygen_refuses_to_overwrite_an_existing_key(tmp_path):
    key_file = tmp_path / "alice.key"
    keyring = tmp_path / "operators.json"
    args = ["--operator", "alice", "--private-key", str(key_file), "--keyring", str(keyring)]

    assert keygen.main(args) == 0
    original = key_file.read_text(encoding="utf-8")

    assert keygen.main(args) == 2
    assert key_file.read_text(encoding="utf-8") == original

    assert keygen.main([*args, "--force"]) == 0
    assert key_file.read_text(encoding="utf-8") != original


def test_keygen_preserves_other_operators_in_the_keyring(tmp_path):
    keyring = tmp_path / "operators.json"
    for name in ("alice", "bob"):
        keygen.main(
            [
                "--operator",
                name,
                "--private-key",
                str(tmp_path / f"{name}.key"),
                "--keyring",
                str(keyring),
            ]
        )

    operators = json.loads(keyring.read_text(encoding="utf-8"))["operators"]
    assert sorted(operators) == ["alice", "bob"]
    assert operators["alice"] != operators["bob"]


@pytest.fixture
def operator_env(tmp_path, monkeypatch):
    keyring = tmp_path / "operators.json"
    key_file = tmp_path / "governance.key"
    keygen.main(
        [
            "--operator",
            "governance",
            "--private-key",
            str(key_file),
            "--keyring",
            str(keyring),
        ]
    )
    monkeypatch.setenv(signing.OPERATOR_ID_ENV, "governance")
    monkeypatch.setenv(signing.OPERATOR_PRIVATE_KEY_ENV, str(key_file))
    monkeypatch.setenv(signing.OPERATOR_KEYRING_ENV, str(keyring))
    signing._keyring_at.cache_clear()
    return tmp_path


def test_attest_signs_then_verifies_then_detects_a_change(operator_env, tmp_path, capsys):
    settings_file = tmp_path / "settings.yaml"
    settings_file.write_text("approval:\n  require_for_irreversible: true\n", encoding="utf-8")
    output = tmp_path / "attestation.json"
    args = ["--settings", str(settings_file), "--output", str(output)]

    assert attest_cli.main([*args, "--sign"]) == 0
    assert attest_cli.main(args) == 0
    assert "VALID" in capsys.readouterr().out

    settings_file.write_text("approval:\n  require_for_irreversible: false\n", encoding="utf-8")

    assert attest_cli.main(args) == 1
    assert "configuration has changed" in capsys.readouterr().out


def test_attest_without_an_attestation_reports_and_exits_nonzero(operator_env, tmp_path, capsys):
    result = attest_cli.main(["--output", str(tmp_path / "absent.json")])

    assert result == 1
    assert "No attestation" in capsys.readouterr().out


def test_attest_show_lists_exactly_what_is_covered(operator_env, capsys):
    assert attest_cli.main(["--show"]) == 0

    covered = json.loads(capsys.readouterr().out)
    assert set(covered) == {
        "approval",
        "integrity",
        "delegation",
        "critique",
        "interdiction",
        "quarantine",
        "envelope",
        "invariants",
        "allow_simulated_adapters",
        "charter",
        "policies",
    }
    assert "checkpointing" not in covered, "storage paths grant no authority and are excluded"


def test_attest_refuses_to_sign_without_an_operator_key(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv(signing.OPERATOR_ID_ENV, raising=False)
    monkeypatch.delenv(signing.OPERATOR_PRIVATE_KEY_ENV, raising=False)

    result = attest_cli.main(["--sign", "--output", str(tmp_path / "attestation.json")])

    assert result == 2
    assert "requires an operator identity" in capsys.readouterr().err


@pytest.fixture
def quarantine_settings(tmp_path, monkeypatch):
    settings = tmp_path / "settings.yaml"
    settings.write_text(
        "quarantine:\n"
        "  enabled: true\n"
        f"  store: {json.dumps(str(tmp_path / 'classifications.json'))}\n"
        f"  record_path: {json.dumps(str(tmp_path / 'held.jsonl'))}\n",
        encoding="utf-8",
    )
    return settings


def test_quarantine_lists_held_actions_and_exits_nonzero(quarantine_settings, tmp_path, capsys):
    from orrery.core.quarantine import QuarantineRecord
    from orrery.tools import quarantine as quarantine_cli

    (tmp_path / "held.jsonl").write_text(
        QuarantineRecord(
            adapter="notes",
            action_name="purge_notes",
            action_id="abc",
            reason="undeclared action",
            parameter_keys=["scope"],
        ).model_dump_json()
        + "\n",
        encoding="utf-8",
    )

    result = quarantine_cli.main(["--settings", str(quarantine_settings)])
    printed = capsys.readouterr().out

    assert result == 1, "a non-empty queue is not a clean state"
    assert "notes:purge_notes" in printed
    assert "under-declaring" in printed


def test_quarantine_classify_records_what_an_action_is(quarantine_settings, tmp_path, capsys):
    from orrery.core.quarantine import ClassificationStore
    from orrery.tools import quarantine as quarantine_cli

    result = quarantine_cli.main(
        [
            "--settings",
            str(quarantine_settings),
            "--classify",
            "notes:purge_notes",
            "--risk",
            "COMPENSABLE",
            "--note",
            "moves to trash",
            "--by",
            "kirk",
        ]
    )
    printed = capsys.readouterr().out

    assert result == 0
    assert "does not authorise it" in printed, "the CLI must not imply it granted permission"

    store = ClassificationStore.from_file(tmp_path / "classifications.json")
    found = store.lookup("notes", "purge_notes")
    assert found is not None and found.note == "moves to trash"


def test_quarantine_classify_requires_a_risk(quarantine_settings, capsys):
    from orrery.tools import quarantine as quarantine_cli

    assert quarantine_cli.main(
        ["--settings", str(quarantine_settings), "--classify", "notes:purge"]
    ) == 2
    assert "requires --risk" in capsys.readouterr().err


def test_quarantine_rejects_a_malformed_target(quarantine_settings, capsys):
    from orrery.tools import quarantine as quarantine_cli

    assert quarantine_cli.main(
        ["--settings", str(quarantine_settings), "--classify", "notes", "--risk", "READ_ONLY"]
    ) == 2
    assert "ADAPTER:ACTION" in capsys.readouterr().err
