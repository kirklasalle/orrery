"""
Orrery End-to-End Demonstration Script.

Demonstrates:
1. Multi-tier nested cycle delegation (Meta -> Macro -> Meso -> Micro)
2. Disk-backed state checkpointing
3. Platform adapter interactions
4. Simulated reflection failover and automated backtracking recovery
"""

import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncio
import logging
from orrery.core.types import StateContext, CycleTier, CyclePhase, CycleStatus, ExecutionReceipt
from orrery.cycles.meta import MetaCycle
from orrery.adapters.hermes import HermesAdapter
from orrery.adapters.windows_os import WindowsOSAdapter

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("demo_cycle")


async def run_success_demo():
    logger.info("=== STARTING SUCCESSFUL NESTED COGNITION CYCLE DEMO ===")
    
    initial_context = StateContext(
        goal="Automate enterprise data ingestion and UI verification",
        tier=CycleTier.META,
    )

    meta_cycle = MetaCycle(context=initial_context)
    final_context = await meta_cycle.run_cycle()

    logger.info(f"Cycle completed with final status: {final_context.status}")
    logger.info(f"Total steps executed: {final_context.step_count}")
    logger.info(f"Checkpoints created: {len(meta_cycle.dispatcher.checkpoint_manager._checkpoints)}")
    logger.info(f"Hypotheses generated across tiers: {len(final_context.hypotheses)}")
    for h in final_context.hypotheses:
        logger.info(f"  - {h}")

    logger.info(f"Execution receipts collected: {len(final_context.execution_receipts)}")
    for r in final_context.execution_receipts:
        logger.info(f"  - [{r.action_name}] Success: {r.success} | Output: {r.output}")

    logger.info("=== SUCCESS DEMO COMPLETED CLEANLY ===\n")


async def run_backtracking_demo():
    logger.info("=== STARTING SIMULATED FAILOVER & BACKTRACKING DEMO ===")

    context = StateContext(
        goal="Perform unstable external tool invocation",
        tier=CycleTier.MICRO,
    )
    
    dispatcher = MetaCycle(context=context).dispatcher

    # Inject a failing execution handler to simulate tool error
    attempts = 0
    async def simulated_unstable_execution(ctx: StateContext) -> StateContext:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            logger.warning("[Simulated Tool Failure] Action failed during execution step 1!")
            ctx.execution_receipts.append(
                ExecutionReceipt(
                    action_id="fail_1",
                    action_name="unstable_api_call",
                    success=False,
                    error="503 Service Unavailable",
                )
            )
        else:
            logger.info("[Simulated Tool Retry] Action succeeded during execution step 2 after backtrack!")
            ctx.execution_receipts.append(
                ExecutionReceipt(
                    action_id="success_2",
                    action_name="unstable_api_call",
                    success=True,
                    output="200 OK - Recovered",
                )
            )
        return ctx

    dispatcher.register_handler(CyclePhase.EXECUTION, simulated_unstable_execution)

    # Step 1: Perception
    context = await dispatcher.step(context)
    # Step 2: Planning
    context = await dispatcher.step(context)
    # Step 3: Execution (Fails)
    context = await dispatcher.step(context)
    # Step 4: Reflection (Fails score=0.0 -> Triggers Backtrack rewind to Planning)
    context = await dispatcher.step(context)
    
    logger.info(f"Context status after reflection failure: {context.status} (Backtrack Count: {context.backtrack_count})")
    
    # Step 5: Planning (re-route after backtrack)
    context = await dispatcher.step(context)
    # Step 6: Execution (Retry succeeds!)
    context = await dispatcher.step(context)
    # Step 7: Reflection (Passes!)
    context = await dispatcher.step(context)

    logger.info(f"Final context status after recovery: {context.status}")
    logger.info("=== BACKTRACKING DEMO COMPLETED CLEANLY ===")


async def main():
    await run_success_demo()
    await run_backtracking_demo()


if __name__ == "__main__":
    asyncio.run(main())
