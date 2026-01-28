#!/usr/bin/env python3
"""
Minimal OpenAI connectivity test.
- Reads OPENAI_API_KEY from env.
- Performs a minimal ChatCompletion call (max_tokens=1).
- Prints only success or exception type/message (truncated) — never prints the key.
"""
import os
import sys

def main():
    key = os.getenv("OPENAI_API_KEY")
    model = os.getenv("OPENAI_MODEL", "gpt-3.5-turbo")
    if not key:
        print("PYTHON: No OPENAI_API_KEY in environment.")
        return

    try:
        import openai
    except Exception as e:
        print("PYTHON: import openai failed:", type(e).__name__, str(e)[:300])
        return

    openai.api_key = key
    try:
        resp = openai.ChatCompletion.create(
            model=model,
            messages=[{"role":"system","content":"You are a short test."},{"role":"user","content":"Hello"}],
            max_tokens=1,
            temperature=0.0,
        )
        # if succeeded:
        print("OPENAI TEST: success; model:", model)
    except Exception as e:
        ex_type = type(e).__name__
        # truncate message to avoid accidental long output
        ex_msg = str(e).replace("\n", " ")[:500]
        print(f"OPENAI TEST: failed -> {ex_type}: {ex_msg}")

if __name__ == "__main__":
    main()
