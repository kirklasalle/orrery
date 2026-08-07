"""
Tests for the real filesystem adapter and the risk/approval gate.

These are the first tests in the suite that assert against the actual filesystem rather
than against the framework's own bookkeeping.
"""

import asyncio

from orrery.adapters.filesystem import FileSystemAdapter
from orrery.core import approval
from orrery.core.approval import ApprovalGate
from orrery.core.config import ApprovalSettings, LedgerSettings, Settings
from orrery.core.dispatcher import CycleDispatcher
from orrery.core.types import ActionPayload, ActionRisk, ApprovalToken, CycleTier, StateContext


def _adapter(tmp_path) -> FileSystemAdapter:
    return FileSystemAdapter(root=str(tmp_path / "sandbox"))


def _dispatcher(tmp_path, adapter, **approval_kwargs) -> CycleDispatcher:
    settings = Settings(
        ledger=LedgerSettings(storage_dir=str(tmp_path / "ledger")),
        approval=ApprovalSettings(**approval_kwargs),
    )
    dispatcher = CycleDispatcher(settings=settings)
    dispatcher.register_adapter(adapter, name="default")
    return dispatcher


async def _run(adapter, name, **params):
    action = ActionPayload(action_name=name, params=params, target_adapter=adapter.name)
    return await adapter.execute_action(action)


def _act(adapter, name, **params):
    return asyncio.run(_run(adapter, name, **params))


def test_write_then_read_touches_the_real_filesystem(tmp_path):
    adapter = _adapter(tmp_path)

    write = _act(adapter, "write_file", path="notes/hello.txt", content="real bytes")

    assert write.success, write.error
    on_disk = adapter.root / "notes" / "hello.txt"
    assert on_disk.read_text(encoding="utf-8") == "real bytes"

    read = _act(adapter, "read_file", path="notes/hello.txt")
    assert read.output["content"] == "real bytes"


def test_failure_is_reported_not_fabricated(tmp_path):
    adapter = _adapter(tmp_path)

    receipt = _act(adapter, "read_file", path="does_not_exist.txt")

    assert receipt.success is False
    assert "FileNotFoundError" in (receipt.error or "")


def test_unsupported_action_fails_without_raising(tmp_path):
    receipt = _act(_adapter(tmp_path), "launch_missiles")

    assert receipt.success is False
    assert "does not implement" in (receipt.error or "")


def test_directory_lifecycle_round_trips(tmp_path):
    adapter = _adapter(tmp_path)

    assert _act(adapter, "make_dir", path="a/b/c").success
    assert (adapter.root / "a" / "b" / "c").is_dir()

    _act(adapter, "write_file", path="a/b/c/f.txt", content="hi")
    listing = _act(adapter, "list_dir", path="a/b/c")
    assert [entry["name"] for entry in listing.output["entries"]] == ["f.txt"]

    stat = _act(adapter, "stat_path", path="a/b/c/f.txt")
    assert stat.output["exists"] is True
    assert stat.output["is_dir"] is False


def test_append_adds_without_replacing(tmp_path):
    adapter = _adapter(tmp_path)
    _act(adapter, "write_file", path="log.txt", content="one\n")

    assert _act(adapter, "append_file", path="log.txt", content="two\n").success

    assert (adapter.root / "log.txt").read_text(encoding="utf-8") == "one\ntwo\n"


def test_write_reports_whether_it_overwrote(tmp_path):
    adapter = _adapter(tmp_path)

    first = _act(adapter, "write_file", path="f.txt", content="a")
    second = _act(adapter, "write_file", path="f.txt", content="b")

    assert first.output["overwrote"] is False
    assert second.output["overwrote"] is True


def test_move_refuses_to_clobber_an_existing_destination(tmp_path):
    adapter = _adapter(tmp_path)
    _act(adapter, "write_file", path="src.txt", content="source")
    _act(adapter, "write_file", path="dst.txt", content="destination")

    receipt = _act(adapter, "move_path", source="src.txt", destination="dst.txt")

    assert receipt.success is False
    assert "FileExistsError" in (receipt.error or "")
    assert (adapter.root / "dst.txt").read_text(encoding="utf-8") == "destination"
    assert (adapter.root / "src.txt").exists()


def test_move_succeeds_to_a_free_destination(tmp_path):
    adapter = _adapter(tmp_path)
    _act(adapter, "write_file", path="src.txt", content="source")

    assert _act(adapter, "move_path", source="src.txt", destination="moved.txt").success

    assert not (adapter.root / "src.txt").exists()
    assert (adapter.root / "moved.txt").read_text(encoding="utf-8") == "source"


def test_delete_tree_removes_a_subtree(tmp_path):
    adapter = _adapter(tmp_path)
    _act(adapter, "write_file", path="junk/deep/f.txt", content="x")

    assert _act(adapter, "delete_tree", path="junk").success

    assert not (adapter.root / "junk").exists()
    assert adapter.root.exists()


def test_delete_file_refuses_a_directory(tmp_path):
    adapter = _adapter(tmp_path)
    _act(adapter, "make_dir", path="a_dir")

    receipt = _act(adapter, "delete_file", path="a_dir")

    assert receipt.success is False
    assert "IsADirectoryError" in (receipt.error or "")
    assert (adapter.root / "a_dir").is_dir()


def test_read_refuses_a_file_over_the_size_limit(tmp_path):
    adapter = FileSystemAdapter(root=str(tmp_path / "sandbox"), config={"max_read_bytes": 8})
    _act(adapter, "write_file", path="big.txt", content="x" * 64)

    receipt = _act(adapter, "read_file", path="big.txt")

    assert receipt.success is False
    assert "read limit" in (receipt.error or "")


def test_paths_cannot_escape_the_sandbox(tmp_path):
    adapter = _adapter(tmp_path)
    outside = tmp_path / "escaped.txt"

    for path in ("../escaped.txt", "notes/../../escaped.txt", "a/b/../../../escaped.txt"):
        receipt = _act(adapter, "write_file", path=path, content="pwned")
        assert receipt.success is False, f"{path} escaped the sandbox"
        assert "escapes the adapter sandbox" in (receipt.error or "")

    assert not outside.exists()


def test_absolute_paths_are_refused(tmp_path):
    receipt = _act(_adapter(tmp_path), "write_file", path=str(tmp_path / "abs.txt"), content="x")

    assert receipt.success is False
    assert "absolute paths are not permitted" in (receipt.error or "")


def test_delete_tree_refuses_the_sandbox_root(tmp_path):
    adapter = _adapter(tmp_path)

    receipt = _act(adapter, "delete_tree", path=".")

    assert receipt.success is False
    assert adapter.root.exists()


def test_perceive_reports_real_observations(tmp_path):
    adapter = _adapter(tmp_path)
    _act(adapter, "write_file", path="one.txt", content="a")
    _act(adapter, "write_file", path="two.txt", content="b")

    observed = asyncio.run(adapter.perceive_environment(StateContext(goal="look")))

    assert observed["entry_count"] == 2
    assert sorted(observed["entries"]) == ["one.txt", "two.txt"]
    assert observed["free_bytes"] > 0


def test_irreversible_action_is_refused_without_approval(tmp_path):
    async def scenario():
        adapter = _adapter(tmp_path)
        await _run(adapter, "write_file", path="doomed.txt", content="still here")
        dispatcher = _dispatcher(tmp_path, adapter)

        action = ActionPayload(
            action_name="delete_file", params={"path": "doomed.txt"}, target_adapter="default"
        )
        receipt = await dispatcher.execute_action(action)

        assert receipt.success is False
        assert "RISK-001" in (receipt.error or "")
        assert (adapter.root / "doomed.txt").exists(), "the file must survive a refused delete"

    asyncio.run(scenario())


def test_approved_irreversible_action_executes(tmp_path):
    async def scenario():
        adapter = _adapter(tmp_path)
        await _run(adapter, "write_file", path="doomed.txt", content="goodbye")
        dispatcher = _dispatcher(tmp_path, adapter)

        action = ActionPayload(
            action_name="delete_file", params={"path": "doomed.txt"}, target_adapter="default"
        )
        action.approval = approval.grant(action, approver="kirk", reason="cleanup")
        receipt = await dispatcher.execute_action(action)

        assert receipt.success, receipt.error
        assert not (adapter.root / "doomed.txt").exists()

    asyncio.run(scenario())


def test_a_planner_cannot_downgrade_an_irreversible_action(tmp_path):
    """
    The adapter's risk declaration wins over the planner's. Otherwise any component that
    can build an ActionPayload could relabel a delete as harmless and skip the gate.
    """

    async def scenario():
        adapter = _adapter(tmp_path)
        await _run(adapter, "write_file", path="doomed.txt", content="still here")
        dispatcher = _dispatcher(tmp_path, adapter)

        action = ActionPayload(
            action_name="delete_file",
            params={"path": "doomed.txt"},
            target_adapter="default",
            risk=ActionRisk.READ_ONLY,
        )
        receipt = await dispatcher.execute_action(action)

        assert receipt.success is False
        assert action.risk is ActionRisk.IRREVERSIBLE
        assert (adapter.root / "doomed.txt").exists()

    asyncio.run(scenario())


def test_approval_cannot_be_replayed_against_another_action(tmp_path):
    async def scenario():
        adapter = _adapter(tmp_path)
        await _run(adapter, "write_file", path="a.txt", content="a")
        await _run(adapter, "write_file", path="b.txt", content="b")
        dispatcher = _dispatcher(tmp_path, adapter)

        approved = ActionPayload(
            action_name="delete_file", params={"path": "a.txt"}, target_adapter="default"
        )
        token = approval.grant(approved, approver="kirk")

        other = ActionPayload(
            action_name="delete_file", params={"path": "b.txt"}, target_adapter="default"
        )
        other.approval = token
        receipt = await dispatcher.execute_action(other)

        assert receipt.success is False
        assert "RISK-002" in (receipt.error or "")
        assert (adapter.root / "b.txt").exists()

    asyncio.run(scenario())


def test_unsigned_approval_is_refused_when_signing_is_required(tmp_path, monkeypatch):
    monkeypatch.delenv(approval.APPROVAL_KEY_ENV, raising=False)
    action = ActionPayload(action_name="delete_file", risk=ActionRisk.IRREVERSIBLE)
    action.approval = approval.grant(action, approver="kirk")

    decision = ApprovalGate(require_signed_approval=True).evaluate(action)

    assert not decision.allowed
    assert decision.policy_id == "RISK-003"


def test_signed_approval_passes_and_a_forged_one_does_not(tmp_path, monkeypatch):
    monkeypatch.setenv(approval.APPROVAL_KEY_ENV, "operator-secret")
    gate = ApprovalGate(require_signed_approval=True)

    action = ActionPayload(action_name="delete_file", risk=ActionRisk.IRREVERSIBLE)
    action.approval = approval.grant(action, approver="kirk")
    assert gate.evaluate(action).allowed

    forged = ActionPayload(action_name="delete_file", risk=ActionRisk.IRREVERSIBLE)
    forged.approval = ApprovalToken(
        action_id=forged.action_id, approver="kirk", signature="deadbeef" * 8
    )
    decision = gate.evaluate(forged)
    assert not decision.allowed
    assert decision.policy_id == "RISK-003"


def test_expired_approval_is_refused():
    action = ActionPayload(action_name="delete_file", risk=ActionRisk.IRREVERSIBLE)
    action.approval = ApprovalToken(
        action_id=action.action_id, approver="kirk", granted_at="2020-01-01T00:00:00+00:00"
    )

    decision = ApprovalGate(approval_ttl_seconds=60).evaluate(action)

    assert not decision.allowed
    assert decision.policy_id == "RISK-004"


def test_read_only_actions_need_no_approval(tmp_path):
    async def scenario():
        adapter = _adapter(tmp_path)
        await _run(adapter, "write_file", path="safe.txt", content="hello")
        dispatcher = _dispatcher(tmp_path, adapter)

        receipt = await dispatcher.execute_action(
            ActionPayload(action_name="read_file", params={"path": "safe.txt"}, target_adapter="default")
        )

        assert receipt.success, receipt.error

    asyncio.run(scenario())


def test_refused_action_is_recorded_in_the_ledger(tmp_path):
    async def scenario():
        adapter = _adapter(tmp_path)
        await _run(adapter, "write_file", path="doomed.txt", content="x")
        dispatcher = _dispatcher(tmp_path, adapter)

        context = StateContext(goal="delete it", tier=CycleTier.MICRO)
        context.planned_actions.append(
            ActionPayload(
                action_name="delete_file", params={"path": "doomed.txt"}, target_adapter="default"
            )
        )
        await dispatcher.dispatch_actions(context)

        refusals = [e for e in dispatcher.ledger.events if e.event_type == "action.refused"]
        assert len(refusals) == 1
        assert refusals[0].policy_id == "RISK-001"
        assert refusals[0].data["risk"] == "IRREVERSIBLE"

        failures = [e for e in dispatcher.ledger.events if e.event_type == "action.failed"]
        assert len(failures) == 1
        assert failures[0].data["risk"] == "IRREVERSIBLE"
        assert failures[0].data["approved_by"] is None

    asyncio.run(scenario())


def test_real_adapter_output_is_not_tagged_as_simulated(tmp_path):
    async def scenario():
        adapter = _adapter(tmp_path)
        dispatcher = _dispatcher(tmp_path, adapter)

        receipt = await dispatcher.execute_action(
            ActionPayload(
                action_name="write_file",
                params={"path": "real.txt", "content": "x"},
                target_adapter="default",
            )
        )

        assert receipt.success, receipt.error
        assert "simulated" not in receipt.output

    asyncio.run(scenario())
