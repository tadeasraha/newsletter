"""
Modul pro správu stavu aplikace.
Ukládá a načítá state.json s informacemi o zpracovaných zprávách.
"""
import json
import os
from typing import Dict, Set

STATE_FILE = "state.json"


def load_state() -> Dict[str, Set[str]]:
    """
    Načte stav ze souboru state.json.
    
    Returns:
        Slovník s klíčem 'processed_messages' obsahující množinu zpracovaných message_id
    """
    if not os.path.exists(STATE_FILE):
        return {"processed_messages": set()}
    
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            # Převést list na set
            processed = set(data.get("processed_messages", []))
            return {"processed_messages": processed}
    except Exception as e:
        print(f"Chyba při načítání state.json: {e}")
        return {"processed_messages": set()}


def save_state(state: Dict[str, Set[str]]) -> None:
    """
    Uloží stav do souboru state.json.
    
    Args:
        state: Slovník se stavem aplikace
    """
    try:
        # Převést set na list pro JSON serializaci
        data = {
            "processed_messages": sorted(list(state["processed_messages"]))
        }
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"Stav uložen do {STATE_FILE}")
    except Exception as e:
        print(f"Chyba při ukládání state.json: {e}")
