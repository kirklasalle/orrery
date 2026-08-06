"""
Tests for Platform Adapters (OpenClaw, Hermes, Windows OS Agent).
"""

import asyncio
from orrery.core.types import StateContext, ActionPayload, CycleTier
from orrery.adapters.openclaw import OpenClawAdapter
from orrery.adapters.hermes import HermesAdapter
from orrery.adapters.windows_os import WindowsOSAdapter


def test_openclaw_adapter():
    async def run():
        adapter = OpenClawAdapter()
        context = StateContext(goal="OpenClaw perception test", tier=CycleTier.MACRO)
        
        perception = await adapter.perceive_environment(context)
        assert perception["platform"] == "OpenClaw"
        
        action = ActionPayload(action_name="route_task", tier=CycleTier.MACRO)
        receipt = await adapter.execute_action(action)
        assert receipt.success is True
        assert "OpenClaw" in str(receipt.output)

    asyncio.run(run())


def test_hermes_adapter():
    async def run():
        adapter = HermesAdapter()
        context = StateContext(goal="Hermes reasoning test", tier=CycleTier.META)
        
        perception = await adapter.perceive_environment(context)
        assert perception["platform"] == "Hermes/Console"
        
        action = ActionPayload(action_name="evaluate_gate", tier=CycleTier.META)
        receipt = await adapter.execute_action(action)
        assert receipt.success is True
        assert "Hermes" in str(receipt.output)

    asyncio.run(run())


def test_windows_os_adapter():
    async def run():
        adapter = WindowsOSAdapter()
        context = StateContext(goal="Windows OS UI test", tier=CycleTier.MICRO)
        
        perception = await adapter.perceive_environment(context)
        assert perception["platform"] == "Windows OS"
        
        action = ActionPayload(action_name="click_element", params={"target": "btn_submit"}, tier=CycleTier.MICRO)
        receipt = await adapter.execute_action(action)
        assert receipt.success is True
        assert "Windows OS Agent" in str(receipt.output)

    asyncio.run(run())
