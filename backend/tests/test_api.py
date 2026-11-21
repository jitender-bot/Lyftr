import os
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

# Configure test environment
os.environ["DATABASE_URL"] = "sqlite:///./test_data/test_app.db"
os.environ["LLM_API_KEYS"] = "key_test_1,key_test_2"
os.environ["ENABLE_FAILURE_SIMULATION"] = "true"

from app.main import app
from app.database import init_db, get_db_file_path
import litellm

client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_test_db():
    init_db()
    # Clear cache before each test
    if litellm.cache and hasattr(litellm.cache, "cache"):
        litellm.cache.cache.flush_cache()
    yield
    # Cleanup DB file if exists
    db_path = get_db_file_path()
    if os.path.exists(db_path):
        try:
            os.remove(db_path)
        except Exception:
            pass

def fake_litellm_completion(model, messages, api_key, **kwargs):
    # Simulate litellm completion object
    mock_resp = MagicMock()
    mock_choice = MagicMock()
    last_msg = messages[-1]["content"] if messages else "empty"
    mock_choice.message = MagicMock()
    mock_choice.message.content = f"Response to {last_msg}"
    mock_resp.choices = [mock_choice]
    mock_resp.usage = MagicMock()
    mock_resp.usage.prompt_tokens = 35
    mock_resp.usage.completion_tokens = 12
    return mock_resp

def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["keys_configured"] == 2
    assert data["cache_enabled"] is True

@patch("litellm.completion", side_effect=fake_litellm_completion)
def test_chat_live_inference(mock_comp):
    payload = {
        "session_id": "test-sess-1",
        "message": "What is the capital of France?"
    }
    response = client.post("/chat", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["session_id"] == "test-sess-1"
    assert "France" in data["reply"]
    assert data["metadata"]["resolution_source"] == "LIVE_INFERENCE"
    assert data["metadata"]["key_id"] == "key_1"
    assert data["metadata"]["fallback_attempts"] == 0
    assert data["metadata"]["input_tokens"] == 35
    assert data["metadata"]["output_tokens"] == 12
    assert isinstance(data["metadata"]["latency_ms"], int)

@patch("litellm.completion", side_effect=fake_litellm_completion)
def test_response_caching(mock_comp):
    msg = "Explain quantum computing in one sentence."
    
    # First call in session A -> LIVE_INFERENCE
    res1 = client.post("/chat", json={"session_id": "sess-a", "message": msg})
    assert res1.status_code == 200
    data1 = res1.json()
    assert data1["metadata"]["resolution_source"] == "LIVE_INFERENCE"
    assert data1["metadata"]["key_id"] == "key_1"
    
    # Same first message in session B -> LLM_CACHE
    res2 = client.post("/chat", json={"session_id": "sess-b", "message": msg})
    assert res2.status_code == 200
    data2 = res2.json()
    assert data2["metadata"]["resolution_source"] == "LLM_CACHE"
    assert data2["metadata"]["key_id"] is None
    assert data2["metadata"]["fallback_attempts"] == 0
    assert data2["reply"] == data1["reply"]
    assert data2["metadata"]["input_tokens"] == data1["metadata"]["input_tokens"]
    assert data2["metadata"]["output_tokens"] == data1["metadata"]["output_tokens"]
    
    # A different message in session C -> LIVE_INFERENCE
    res3 = client.post("/chat", json={"session_id": "sess-c", "message": "Different question"})
    assert res3.status_code == 200
    data3 = res3.json()
    assert data3["metadata"]["resolution_source"] == "LIVE_INFERENCE"

@patch("litellm.completion", side_effect=fake_litellm_completion)
def test_failover_hook_key_1_fails(mock_comp):
    payload = {
        "session_id": "test-sess-failover-1",
        "message": "Testing failover"
    }
    # key_1=429 should failover to key_2
    response = client.post(
        "/chat",
        json=payload,
        headers={"X-Simulate-Failure": "key_1=429"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["metadata"]["key_id"] == "key_2"
    assert data["metadata"]["fallback_attempts"] == 1

@patch("litellm.completion", side_effect=fake_litellm_completion)
def test_failover_hook_key_1_500(mock_comp):
    payload = {
        "session_id": "test-sess-failover-2",
        "message": "Testing 500 failover"
    }
    # key_1=500 should failover to key_2
    response = client.post(
        "/chat",
        json=payload,
        headers={"X-Simulate-Failure": "key_1=500"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["metadata"]["key_id"] == "key_2"
    assert data["metadata"]["fallback_attempts"] == 1

@patch("litellm.completion", side_effect=fake_litellm_completion)
def test_failover_hook_all_fail_returns_503(mock_comp):
    session_id = "test-sess-all-fail"
    payload = {
        "session_id": session_id,
        "message": "Testing all providers failing"
    }
    # *=429 means every key fails -> 503 {"detail": "all providers unavailable"}
    response = client.post(
        "/chat",
        json=payload,
        headers={"X-Simulate-Failure": "*=429"}
    )
    assert response.status_code == 503
    assert response.json() == {"detail": "all providers unavailable"}
    
    # Requirement: failed request (503) must not be added to session history
    hist_res = client.get(f"/sessions/{session_id}/messages")
    assert hist_res.status_code == 404

def test_chat_validation_errors():
    # Empty message
    res1 = client.post("/chat", json={"session_id": "s1", "message": "   "})
    assert res1.status_code == 422
    assert "detail" in res1.json()

    # Empty session_id
    res2 = client.post("/chat", json={"session_id": "", "message": "hello"})
    assert res2.status_code == 422
    assert "detail" in res2.json()

    # Message > 4000 chars
    long_msg = "a" * 4001
    res3 = client.post("/chat", json={"session_id": "s1", "message": long_msg})
    assert res3.status_code == 422
    assert "detail" in res3.json()

@patch("litellm.completion", side_effect=fake_litellm_completion)
def test_multi_turn_history_and_session_endpoint(mock_comp):
    session_id = "multi-turn-sess-1"
    
    # Message 1
    res1 = client.post("/chat", json={"session_id": session_id, "message": "My name is Alice"})
    assert res1.status_code == 200
    
    # Message 2
    res2 = client.post("/chat", json={"session_id": session_id, "message": "What is my name?"})
    assert res2.status_code == 200
    
    # Check history endpoint
    hist_res = client.get(f"/sessions/{session_id}/messages")
    assert hist_res.status_code == 200
    data = hist_res.json()
    assert data["session_id"] == session_id
    assert len(data["messages"]) == 4  # 2 user messages + 2 assistant messages
    
    assert data["messages"][0]["role"] == "user"
    assert data["messages"][0]["content"] == "My name is Alice"
    assert "metadata" not in data["messages"][0] or data["messages"][0]["metadata"] is None
    
    assert data["messages"][1]["role"] == "assistant"
    assert "metadata" in data["messages"][1]
    assert data["messages"][1]["metadata"]["resolution_source"] == "LIVE_INFERENCE"

def test_unknown_session_returns_404():
    res = client.get("/sessions/unknown-session-9999/messages")
    assert res.status_code == 404
    assert res.json() == {"detail": "session not found"}
