import json
import os
from datetime import datetime, timezone
from threading import Lock

LOG_PATH = os.getenv("LOG_PATH","logs/commands.jsonl")
_lock = Lock()

def log_command(sandbox_name: str, command: str, decision: str, execution_target: str = "celesto_sandbox"):
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "sandbox_name": sandbox_name,
        "command": command,
        "decision": decision,
        "execution_target": execution_target,
    }
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    with _lock:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
