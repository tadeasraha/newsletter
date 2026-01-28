import json
from pathlib import Path

STATE_PATH = Path("data/state.json")

def load_state():
    if not STATE_PATH.exists():
        return {"processed_message_ids": [], "fetched_urls": {}}
    return json.loads(STATE_PATH.read_text(encoding="utf-8"))

def save_state(state):
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
