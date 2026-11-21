"""
Live end-to-end integration test.
Set LLM_API_KEYS and LLM_MODELS in your .env before running:
    python test_live.py
"""
import sys, os
sys.path.insert(0, 'backend')

# Load from .env file - never hardcode keys here
from dotenv import load_dotenv
load_dotenv('.env')

if not os.getenv('LLM_API_KEYS'):
    print("ERROR: LLM_API_KEYS not set. Add it to your .env file.")
    sys.exit(1)

from app.llm_service import generate_chat_response

print("=== Test 1: Normal call (key_1) ===")
msgs = [{'role': 'user', 'content': 'What is 2+2? Answer in one word.'}]
reply, meta = generate_chat_response(msgs)
print("Reply:", reply.strip())
print("Key:", meta["key_id"], "| Model:", meta["model"], "| Source:", meta["resolution_source"])
print("Tokens in:", meta["input_tokens"], "out:", meta["output_tokens"], "| Latency:", meta["latency_ms"], "ms")

print()
print("=== Test 2: Failover (key_1=429 -> key_2) ===")
msgs2 = [{'role': 'user', 'content': 'Name one colour. Answer in one word.'}]
reply2, meta2 = generate_chat_response(msgs2, simulation_header='key_1=429')
print("Reply:", reply2.strip())
print("Key:", meta2["key_id"], "| Model:", meta2["model"], "| Fallbacks:", meta2["fallback_attempts"])

print()
print("=== Test 3: Cache hit (same as Test 1) ===")
reply3, meta3 = generate_chat_response(msgs)
print("Reply:", reply3.strip())
print("Source:", meta3["resolution_source"], "| Latency:", meta3["latency_ms"], "ms | key_id:", meta3["key_id"])

print()
if meta3["resolution_source"] == "LLM_CACHE":
    print("=== ALL PASSED ===")
else:
    print("=== WARNING: Cache did not hit ===")
