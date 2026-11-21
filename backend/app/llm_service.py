import os
import time
import json
import logging
from typing import List, Dict, Any, Optional, Tuple
from fastapi import HTTPException
import litellm
from litellm.caching.caching import Cache

from app.config import settings

logger = logging.getLogger(__name__)

# Initialize LiteLLM cache
try:
    litellm.enable_cache(type="local")
except Exception as e:
    logger.warning(f"Failed to enable LiteLLM local cache: {e}")
    litellm.cache = Cache(type="local")

def get_cache_key(model: str, messages: List[Dict[str, str]]) -> str:
    """Generate deterministic cache key using litellm helper or canonical json."""
    try:
        if litellm.cache:
            return litellm.cache.get_cache_key(model=model, messages=messages)
    except Exception:
        pass
    import hashlib
    raw = f"{model}:{json.dumps(messages, sort_keys=True)}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

def parse_simulation_header(header: Optional[str]) -> Dict[str, int]:
    if not header:
        return {}
    sim = {}
    for part in header.split(","):
        part = part.strip()
        if "=" in part:
            k, v = part.split("=", 1)
            try:
                sim[k.strip().lower()] = int(v.strip())
            except ValueError:
                pass
    return sim

def generate_chat_response(
    messages: List[Dict[str, str]],
    model: str = settings.LLM_MODEL,
    simulation_header: Optional[str] = None
) -> Tuple[str, Dict[str, Any]]:
    """
    Executes chat completion with caching and key failover.
    Returns: (reply_text, metadata_dict)
    Raises: HTTPException 503 if all providers fail.
    """
    start_time = time.perf_counter()
    
    # Check cache first
    cache_key = get_cache_key(model, messages)
    if litellm.cache and hasattr(litellm.cache, "cache"):
        cached = litellm.cache.cache.get_cache(cache_key)
        if cached and isinstance(cached, dict):
            latency_ms = max(1, int((time.perf_counter() - start_time) * 1000))
            metadata = {
                "resolution_source": "LLM_CACHE",
                "model": cached.get("model", model),
                "latency_ms": latency_ms,
                "input_tokens": cached.get("input_tokens", 0),
                "output_tokens": cached.get("output_tokens", 0),
                "key_id": None,
                "fallback_attempts": 0
            }
            return cached.get("reply", ""), metadata

    # Parse simulation header
    sim_rules = {}
    if settings.ENABLE_FAILURE_SIMULATION and simulation_header:
        sim_rules = parse_simulation_header(simulation_header)

    keys = settings.LLM_API_KEYS
    fallback_attempts = 0
    reply_text = None
    successful_key_id = None
    input_tokens = 0
    output_tokens = 0

    for idx, api_key in enumerate(keys):
        key_id = f"key_{idx + 1}"
        
        # Check if failure is simulated for this key or '*'
        simulated_status = sim_rules.get("*") or sim_rules.get(key_id.lower())
        if simulated_status in (429, 500, 502, 503):
            logger.info(f"Simulating failure {simulated_status} for {key_id}")
            fallback_attempts += 1
            continue

        try:
            # Call litellm completion
            response = litellm.completion(
                model=model,
                messages=messages,
                api_key=api_key
            )
            
            # Extract content and token counts
            choices = getattr(response, "choices", [])
            if choices and len(choices) > 0:
                choice = choices[0]
                if hasattr(choice, "message"):
                    reply_text = getattr(choice.message, "content", "")
                elif isinstance(choice, dict):
                    reply_text = choice.get("message", {}).get("content", "")
            
            if not reply_text:
                reply_text = "I'm here to help!"

            usage = getattr(response, "usage", None)
            if usage:
                input_tokens = getattr(usage, "prompt_tokens", 0) or 0
                output_tokens = getattr(usage, "completion_tokens", 0) or 0
            else:
                # Estimate tokens if usage not returned
                try:
                    input_tokens = litellm.token_counter(model=model, messages=messages)
                    output_tokens = litellm.token_counter(model=model, text=reply_text)
                except Exception:
                    input_tokens = sum(len(m.get("content", "").split()) for m in messages)
                    output_tokens = len(reply_text.split())

            successful_key_id = key_id
            break

        except Exception as e:
            logger.warning(f"Key {key_id} failed with error: {e}")
            fallback_attempts += 1
            continue

    if reply_text is None or successful_key_id is None:
        raise HTTPException(
            status_code=503,
            detail="all providers unavailable"
        )

    latency_ms = max(1, int((time.perf_counter() - start_time) * 1000))

    # Save to cache
    if litellm.cache and hasattr(litellm.cache, "cache"):
        litellm.cache.cache.set_cache(
            cache_key,
            {
                "reply": reply_text,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "model": model
            }
        )

    metadata = {
        "resolution_source": "LIVE_INFERENCE",
        "model": model,
        "latency_ms": latency_ms,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "key_id": successful_key_id,
        "fallback_attempts": fallback_attempts
    }

    return reply_text, metadata
