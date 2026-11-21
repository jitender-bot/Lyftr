# Lyftr AI Full-Stack Assignment: Resilient LLM Chatbot

A production-grade, full-stack LLM chatbot system featuring **automatic API key failover**, **response caching with LiteLLM**, **per-request token tracking**, and **multi-turn session memory** persisted in SQLite under Docker volumes.

---

## 1. Live URLs
- **Frontend URL**: `https://lyftr.vercel.app` *(or your custom Vercel deployment link)*
- **Backend API URL**: `https://lyftr-69oe.onrender.com`
- **Health Check**: `https://lyftr-69oe.onrender.com/health`
- **API Documentation (Swagger)**: `https://lyftr-69oe.onrender.com/docs`
- **GitHub Repository**: `https://github.com/jitender-bot/Lyftr`
- **Demo Video (2–3 mins)**: `https://<link-to-loom-or-youtube-demo>`

---

## 2. Run locally: with Docker and without

### Option A: Running with Docker (Mandatory)

The entire stack (backend on port 8000, frontend on port 3000) starts with a single command via the included Makefile:

1. Copy `.env.example` to `.env` and supply your API keys:
   ```bash
   cp .env.example .env
   ```
2. Start all services using Docker Compose:

   ```bash
   make up
   ```

   _(Or alternatively: `docker compose up --build -d`)_

3. Access the applications:
   - **Frontend UI**: [http://localhost:3000](http://localhost:3000)
   - **Backend API**: [http://localhost:8000](http://localhost:8000)
   - **API Health**: [http://localhost:8000/health](http://localhost:8000/health)
   - **Interactive OpenAPI Docs**: [http://localhost:8000/docs](http://localhost:8000/docs)

4. Stop the stack:
   ```bash
   make down
   ```

---

### Option B: Running without Docker (Local Development)

#### Backend (FastAPI + SQLite):

1. Navigate to the backend directory and activate a Python 3.12 environment:
   ```bash
   cd backend
   python -m venv venv
   # On Windows:
   .\venv\Scripts\activate
   # On Linux / macOS:
   source venv/bin/activate
   ```
2. Install requirements:
   ```bash
   pip install -r requirements.txt
   ```
3. Set your environment variables (or export them):
   ```bash
   export LLM_API_KEYS="your_key_1,your_key_2"
   export DATABASE_URL="sqlite:///./data/app.db"
   export ENABLE_FAILURE_SIMULATION="true"
   ```
4. Start the FastAPI development server:
   ```bash
   uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
   ```

#### Frontend (React + Vite):

1. Navigate to the frontend directory:
   ```bash
   cd frontend
   npm install
   ```
2. Start the Vite development server:
   ```bash
   npm run dev
   ```
3. Open [http://localhost:3000](http://localhost:3000) in your browser.

#### Running Backend Tests:

To run the automated test suite with full coverage of all endpoints, caching, and failover:

```bash
python -m pytest backend/tests -v
```

---

## 3. Design decisions: key fallback, caching, SQLite session storage

### Key Pool & Automatic Failover

- **Ordered Key Pool**: Configured via `LLM_API_KEYS` as an ordered comma-separated list (`key_1`, `key_2`, ...).
- **Graceful Fallback Loop**: When an API key encounters HTTP 429 (rate-limit), quota exhaustion, or 5xx provider errors, the gateway records the failure attempt, increments `fallback_attempts`, and immediately routes the request to the subsequent key in the pool.
- **Fail-Safe Exhaustion**: If all keys fail, the backend returns a clean HTTP 503 response `{"detail": "all providers unavailable"}`. The user never encounters unhandled 500 exceptions, stack traces, or broken UI screens.
- **Transactional History Integrity**: In compliance with the specification, requests that fail (422 or 503) are never written to the SQLite session history.

### Response Caching

- **Deterministic Cache Key**: Formed by `model + full conversation context` (`system prompt + history + new user message`).
- **Zero-Latency In-Memory Cache**: Uses LiteLLM's local caching mechanism. Before initiating network requests or dispatching to the key pool, the gateway checks the cache:
  - **Cache Hit**: Instantly returns the stored reply text and token counts with `resolution_source = "LLM_CACHE"`, `key_id = null`, and `fallback_attempts = 0`. Cache hit latency is measured in milliseconds and is substantially faster than live calls.
  - **Cache Miss**: Dispatches to the active key pool, records `resolution_source = "LIVE_INFERENCE"`, reports the responding `key_id` (e.g. `key_1`), and stores the result in the cache for subsequent identical requests.
- Identical first messages across different sessions hit `LLM_CACHE`. Different messages or differing conversation context never produce false cache hits.

### SQLite Session Storage

- **Isolated SQLite Storage**: Session state is persisted strictly in SQLite without reliance on external services like Redis or PostgreSQL.
- **Volume Persistence**: In Docker, the database path is mounted to a named Docker volume (`/data/app.db`), ensuring conversation state survives container restarts and upgrades.
- **Auto-Migrating Schema**: Schema is automatically created on startup with indexing on `(session_id, id)` for efficient multi-turn message retrieval.
- **Clean API Contract**:
  - `GET /sessions/{session_id}/messages` retrieves the stored history (user messages and assistant messages with metadata) in chronological order. Unknown sessions return HTTP 404 `{"detail": "session not found"}`.

---

## 4. Verification: how to see failover, cache hits and per-message token usage

### 1. Verifying Response Caching

1. In the UI or via curl, send a message:
   ```bash
   curl -X POST http://localhost:8000/chat \
     -H "Content-Type: application/json" \
     -d '{"session_id": "sess-test-1", "message": "What is the capital of France?"}'
   ```
   **Result**: Returns 200 with `"resolution_source": "LIVE_INFERENCE"`, `"key_id": "key_1"`, and response latency (e.g., `800 ms`).
2. Refresh the browser (or use a new session ID) and send the exact same message:
   ```bash
   curl -X POST http://localhost:8000/chat \
     -H "Content-Type: application/json" \
     -d '{"session_id": "sess-test-2", "message": "What is the capital of France?"}'
   ```
   **Result**: Returns 200 with `"resolution_source": "LLM_CACHE"`, `"key_id": null`, `"fallback_attempts": 0`, and near-instant latency (`< 5 ms`).

### 2. Verifying Key Failover with `X-Simulate-Failure`

The backend supports the test hook header `X-Simulate-Failure` (active when `ENABLE_FAILURE_SIMULATION=true`):

- **Simulate Key 1 Rate Limit (429)**:

  ```bash
  curl -X POST http://localhost:8000/chat \
    -H "Content-Type: application/json" \
    -H "X-Simulate-Failure: key_1=429" \
    -d '{"session_id": "sess-fail-1", "message": "Hello from failover test"}'
  ```

  **Response**: HTTP 200, `"key_id": "key_2"`, `"fallback_attempts": 1`.

- **Simulate Key 1 Server Error (500)**:

  ```bash
  curl -X POST http://localhost:8000/chat \
    -H "Content-Type: application/json" \
    -H "X-Simulate-Failure: key_1=500" \
    -d '{"session_id": "sess-fail-2", "message": "Testing 500 error failover"}'
  ```

  **Response**: HTTP 200, `"key_id": "key_2"`, `"fallback_attempts": 1`.

- **Simulate All Keys Exhausted (\*=429)**:
  ```bash
  curl -X POST http://localhost:8000/chat \
    -H "Content-Type: application/json" \
    -H "X-Simulate-Failure: *=429" \
    -d '{"session_id": "sess-fail-3", "message": "All keys down"}'
  ```
  **Response**: HTTP 503 `{"detail": "all providers unavailable"}`. Verified: no messages added to history.

### 3. Verifying Per-Request Token Usage

- In the UI, inspect the metadata badge beneath each assistant response:
  - `Prompt: <input_tokens>`: Accurately reflects prompt tokens for that specific request (system prompt + history + current message).
  - `Output: <output_tokens>`: Tokens generated by the assistant reply.
  - Two equal-length first messages in two separate sessions report the same `input_tokens` (never an accumulating global total).

---

## 5. Setup Used: your editor and AI tools

- **Editor / IDE**: Visual Studio Code / Antigravity IDE
- **Operating Environment**: Windows / Linux Docker Engine
- **Runtimes & Frameworks**:
  - Python 3.12 (FastAPI, LiteLLM, Pydantic v2, Pytest, Uvicorn)
  - Node.js v22 (React 18, Vite, Lucide Icons)
  - Docker & Docker Compose v29
- **AI Coding Assistance**: Google Antigravity Agentic Assistant

---

## 6. Bonus features (if any): what you added beyond the requirements and why

1. **Interactive Failover Dropdown in UI**:
   - Added a failover selector directly inside the UI header (`Simulate key_1 = 429`, `Simulate key_1 = 500`, `Simulate * = 429`, or custom rules). This allows demonstrating key failover live during video demos without needing Postman or terminal commands.
2. **System Prompt Collapsible Inspector**:
   - Implemented an interactive toggle with `data-testid="system-prompt-input"` allowing dynamic personality customization per session.
3. **Database Health & Live Gateway Status Tag**:
   - The UI polls `/health` on startup and displays real-time connection state, count of loaded API keys, and cache operational status.
4. **Resilient Error Banners**:
   - 422 and 503 errors render as non-blocking warning cards inside the chat stream with exact status codes and details, keeping the interface usable and clear.
