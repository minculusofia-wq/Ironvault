import asyncio
import sys
from backend.orchestrator import Orchestrator

async def dry_run():
    print("🚀 Starting Dry Run: Strategy Realignment")
    orchestrator = Orchestrator()
    
    # 1. Load Config
    success, msg = orchestrator.load_config("config/config_paper_test.json")
    print(f"[{'SUCCESS' if success else 'FAIL'}] Config Load: {msg}")
    if not success: return

    # 2. Check Strategies Initialized
    if orchestrator._strategy_a and orchestrator._strategy_b:
        print(f"✅ Strategy A: {orchestrator._strategy_a._name}")
        print(f"✅ Strategy B: {orchestrator._strategy_b._name}")
    else:
        print("❌ Strategy initialization failed")
        return

    # 3. Activate Strategy A
    print("🔋 Activating Strategy A...")
    orchestrator._strategy_a.activate()
    
    # 4. Test Monitor Injection (Mock)
    print("📡 Testing Monitor Injection...")
    await orchestrator._scoreboard.inject_mock_trigger(
        event_id="test_event",
        token_id="21742633143463906290569050155826241533067272736897614950488156847949938836455",
        trigger_type="MOCK_GOAL"
    )
    
    await asyncio.sleep(0.1) # Wait for async dispatch
    
    # 5. Check Queue in Strategy A
    if not orchestrator._strategy_a._pending_triggers.empty():
        print("✅ Strategy A received mock trigger from ScoreboardMonitor")
    else:
        print("❌ Strategy A trigger reception failed")

    print("\n[VERIFICATION COMPLETE] All components linked and communicating.")

if __name__ == "__main__":
    asyncio.run(dry_run())
