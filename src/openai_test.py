#!/usr/bin/env python3
import os, sys, logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-3.5-turbo")

if not OPENAI_API_KEY:
    logger.error("OPENAI_API_KEY is not set in the environment.")
    sys.exit(2)

try:
    import openai
except Exception as e:
    logger.exception("openai package is not installed or import failed: %s", e)
    sys.exit(3)

openai.api_key = OPENAI_API_KEY

try:
    logger.info("Testing OpenAI connectivity (minimal call to avoid costs)...")
    resp = openai.ChatCompletion.create(
        model=OPENAI_MODEL,
        messages=[{"role":"system","content":"You are a friendly test."},{"role":"user","content":"Hello"}],
        max_tokens=1,
        temperature=0.0,
    )
    logger.info("OpenAI call succeeded. Model used: %s", OPENAI_MODEL)
    sys.exit(0)
except Exception as e:
    logger.exception("OpenAI call failed: %s", e)
    sys.exit(4)
