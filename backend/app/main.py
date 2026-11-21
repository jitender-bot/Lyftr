import os
from contextlib import asynccontextmanager
from typing import Optional
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import litellm

from app.config import settings
from app.database import (
    init_db,
    is_db_reachable,
    session_exists,
    get_session_messages,
    add_message
)
from app.schemas import (
    ChatRequest,
    ChatResponse,
    ChatMetadata,
    HealthResponse,
    SessionHistoryResponse,
    SessionMessage,
    SessionMessageMetadata
)
from app.llm_service import generate_chat_response

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: ensure SQLite database schema is initialized
    init_db()
    yield

app = FastAPI(
    title="LLM Chatbot Gateway",
    lifespan=lifespan
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    if isinstance(exc, HTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail}
        )
    return JSONResponse(
        status_code=500,
        content={"detail": "internal server error"}
    )

@app.get("/health", response_model=HealthResponse)
def get_health():
    """
    Returns 200 once the app is running, the database is reachable and the key pool is loaded.
    { "status": "ok", "keys_configured": 2, "cache_enabled": true }
    """
    if not is_db_reachable():
        raise HTTPException(status_code=500, detail="Database unreachable")
    
    return HealthResponse(
        status="ok",
        keys_configured=len(settings.LLM_API_KEYS),
        cache_enabled=litellm.cache is not None
    )

@app.post("/chat", response_model=ChatResponse)
def post_chat(
    req: ChatRequest,
    x_simulate_failure: Optional[str] = Header(None, alias="X-Simulate-Failure")
):
    """
    Sends message to LLM gateway with session history and failover.
    """
    session_id = req.session_id
    user_message = req.message.strip()

    # Retrieve existing messages for session (oldest first)
    history = get_session_messages(session_id)

    # Build messages array for LLM
    llm_messages = []
    
    # 1. System prompt
    system_content = req.system_prompt if req.system_prompt else settings.DEFAULT_SYSTEM_PROMPT
    llm_messages.append({"role": "system", "content": system_content})

    # 2. Historical messages
    for msg in history:
        llm_messages.append({"role": msg["role"], "content": msg["content"]})

    # 3. New user message
    llm_messages.append({"role": "user", "content": user_message})

    # Generate response via LLM service (with cache and failover)
    reply_text, metadata = generate_chat_response(
        messages=llm_messages,
        model=settings.LLM_MODEL,
        simulation_header=x_simulate_failure
    )

    # Save to SQLite on success only
    add_message(session_id, "user", user_message, None)
    add_message(
        session_id,
        "assistant",
        reply_text,
        {
            "resolution_source": metadata["resolution_source"],
            "input_tokens": metadata["input_tokens"],
            "output_tokens": metadata["output_tokens"]
        }
    )

    return ChatResponse(
        session_id=session_id,
        reply=reply_text,
        metadata=ChatMetadata(**metadata)
    )

@app.get("/sessions/{session_id}/messages", response_model=SessionHistoryResponse, response_model_exclude_none=True)
def get_session_history(session_id: str):
    """
    Returns stored history of one session from SQLite, oldest first, without the system prompt.
    """
    if not session_exists(session_id):
        raise HTTPException(status_code=404, detail="session not found")

    raw_messages = get_session_messages(session_id)
    formatted = []
    for m in raw_messages:
        meta = None
        if m.get("metadata"):
            meta = SessionMessageMetadata(
                resolution_source=m["metadata"].get("resolution_source", "LIVE_INFERENCE"),
                input_tokens=m["metadata"].get("input_tokens", 0),
                output_tokens=m["metadata"].get("output_tokens", 0)
            )
        formatted.append(
            SessionMessage(
                role=m["role"],
                content=m["content"],
                metadata=meta
            )
        )

    return SessionHistoryResponse(
        session_id=session_id,
        messages=formatted
    )
