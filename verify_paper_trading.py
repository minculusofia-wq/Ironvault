from backend.orchestrator import Orchestrator
import time
import os

def test_paper_trading():
    print("Initializing Orchestrator...")
    orc = Orchestrator()
    
    config_path = os.path.abspath("config/config_paper_test.json")
    print(f"Loading config: {config_path}")
    
    success, msg = orc.load_config(config_path)
    if not success:
        print(f"Config Load Failed: {msg}")
        return

    print("Config Loaded. Paper Trading:", orc._config.market.paper_trading)
    
    print("Launching Bot...")
    success, msg = orc.launch()
    if not success:
        print(f"Launch Failed: {msg}")
        return
        
    print("Bot Launched! Waiting 10s for heartbeats...")
    time.sleep(10)
    
    print("Stopping Bot...")
    orc.shutdown()
    
    print("Check logs for 'HEARTBEAT_TICK' and 'STRATEGY_A_DUTCHING'")

if __name__ == "__main__":
    test_paper_trading()
