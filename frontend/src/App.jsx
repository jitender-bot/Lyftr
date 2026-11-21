import React, { useState, useEffect, useRef } from 'react';
import './App.css';

// Generate random session id on each page load (s-xxxxxx)
const generateSessionId = () => {
  const rand = Math.random().toString(36).substring(2, 10);
  return `s-${rand}`;
};

export default function App() {
  const [sessionId] = useState(generateSessionId);
  const [messages, setMessages] = useState([]);
  const [inputMessage, setInputMessage] = useState('');
  const [systemPrompt, setSystemPrompt] = useState('');
  const [showSystemPrompt, setShowSystemPrompt] = useState(false);
  const [simulateFailure, setSimulateFailure] = useState('none');
  const [customFailure, setCustomFailure] = useState('');
  const [loading, setLoading] = useState(false);
  const [healthStatus, setHealthStatus] = useState(null);

  const messagesEndRef = useRef(null);
  const inputRef = useRef(null);

  const backendUrl = import.meta.env.VITE_BACKEND_URL || 'http://localhost:8000';

  // Check health on mount
  useEffect(() => {
    fetch(`${backendUrl}/health`)
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (data) setHealthStatus(data);
      })
      .catch(() => {
        setHealthStatus({ status: 'offline', keys_configured: 0, cache_enabled: false });
      });
  }, [backendUrl]);

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading]);

  const handleSendMessage = async (e) => {
    if (e) e.preventDefault();
    const textToSend = inputMessage.trim();
    if (!textToSend || loading) return;

    // 1. Immediately append user message to local state
    const userMsg = {
      role: 'user',
      content: textToSend,
      id: Date.now(),
    };
    setMessages((prev) => [...prev, userMsg]);

    // 2. Clear input immediately (per contract: "Empty after sending")
    setInputMessage('');

    // 3. Prepare payload and headers
    setLoading(true);
    const payload = {
      session_id: sessionId,
      message: textToSend,
    };
    if (systemPrompt.trim()) {
      payload.system_prompt = systemPrompt.trim();
    }

    const headers = {
      'Content-Type': 'application/json',
    };

    let failureHeader = null;
    if (simulateFailure === 'key_1=429') failureHeader = 'key_1=429';
    else if (simulateFailure === 'key_1=500') failureHeader = 'key_1=500';
    else if (simulateFailure === '*=429') failureHeader = '*=429';
    else if (simulateFailure === 'custom' && customFailure.trim()) {
      failureHeader = customFailure.trim();
    }

    if (failureHeader) {
      headers['X-Simulate-Failure'] = failureHeader;
    }

    try {
      const response = await fetch(`${backendUrl}/chat`, {
        method: 'POST',
        headers,
        body: JSON.stringify(payload),
      });

      const data = await response.json();

      if (!response.ok) {
        // Readable error message in chat (never blank screen)
        const errMsg = data?.detail || `Server error (${response.status})`;
        setMessages((prev) => [
          ...prev,
          {
            role: 'error',
            content: `Error: ${typeof errMsg === 'object' ? JSON.stringify(errMsg) : errMsg}`,
            id: Date.now() + 1,
            status: response.status,
          },
        ]);
      } else {
        // Successful assistant reply
        setMessages((prev) => [
          ...prev,
          {
            role: 'assistant',
            content: data.reply,
            metadata: data.metadata,
            id: Date.now() + 1,
          },
        ]);
      }
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        {
          role: 'error',
          content: `Network Error: Unable to reach backend at ${backendUrl}. Check server status.`,
          id: Date.now() + 1,
        },
      ]);
    } finally {
      setLoading(false);
      inputRef.current?.focus();
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  };

  return (
    <div className="chat-container">
      {/* Header */}
      <header className="chat-header">
        <div className="header-brand">
          <div className="logo-badge">⚡</div>
          <div>
            <h1>Lyftr AI Gateway</h1>
            <p className="subtitle">Failover & Response Caching Chatbot</p>
          </div>
        </div>

        <div className="header-meta">
          <div className="session-tag" title="Client-generated Session ID">
            <span className="meta-label">SESSION:</span>
            <span className="session-id">{sessionId}</span>
          </div>

          <div className="health-tag">
            <span
              className={`status-dot ${
                healthStatus?.status === 'ok' ? 'status-online' : 'status-offline'
              }`}
            />
            <span>
              {healthStatus?.status === 'ok'
                ? `Ready (${healthStatus.keys_configured} keys | Cache: ON)`
                : 'Connecting...'}
            </span>
          </div>
        </div>
      </header>

      {/* Control Bar (System Prompt & Failover Simulation) */}
      <div className="control-bar">
        <div className="system-prompt-toggle">
          <button
            type="button"
            className="btn-toggle"
            onClick={() => setShowSystemPrompt(!showSystemPrompt)}
          >
            {showSystemPrompt ? '▼ Hide System Prompt' : '▶ Set System Prompt'}
          </button>
        </div>

        <div className="simulation-control">
          <label htmlFor="sim-select" className="sim-label">
            Failover Test Hook:
          </label>
          <select
            id="sim-select"
            value={simulateFailure}
            onChange={(e) => setSimulateFailure(e.target.value)}
            className="sim-dropdown"
          >
            <option value="none">Normal (No failure simulation)</option>
            <option value="key_1=429">Simulate key_1 = 429 (Rate Limit Failover)</option>
            <option value="key_1=500">Simulate key_1 = 500 (Server Error Failover)</option>
            <option value="*=429">Simulate * = 429 (All Providers Fail - 503)</option>
            <option value="custom">Custom Header Rule</option>
          </select>

          {simulateFailure === 'custom' && (
            <input
              type="text"
              placeholder="e.g. key_1=429,key_2=500"
              value={customFailure}
              onChange={(e) => setCustomFailure(e.target.value)}
              className="custom-sim-input"
            />
          )}
        </div>
      </div>

      {showSystemPrompt && (
        <div className="system-prompt-panel">
          <input
            data-testid="system-prompt-input"
            type="text"
            className="system-prompt-input"
            placeholder="Set optional system prompt for this session (e.g. You are a pirate...)"
            value={systemPrompt}
            onChange={(e) => setSystemPrompt(e.target.value)}
          />
        </div>
      )}

      {/* Messages Scroll Area */}
      <main className="messages-area">
        {messages.length === 0 && (
          <div className="empty-state">
            <div className="empty-icon">💬</div>
            <h2>Start a Conversation</h2>
            <p>
              Send any message. Repeated identical prompts in a new session will hit{' '}
              <code>LLM_CACHE</code> with near-zero latency.
            </p>
            <p>
              Use the failover hook to test automatic key switching on 429 or 5xx errors.
            </p>
          </div>
        )}

        {messages.map((msg) => {
          if (msg.role === 'user') {
            return (
              <div key={msg.id} className="message-wrapper user-wrapper">
                <div className="message-bubble user-bubble">
                  <div className="message-sender">You</div>
                  <div className="message-text">{msg.content}</div>
                </div>
              </div>
            );
          }

          if (msg.role === 'error') {
            return (
              <div key={msg.id} className="message-wrapper error-wrapper">
                <div className="error-card">
                  <div className="error-title">⚠️ Error {msg.status ? `(${msg.status})` : ''}</div>
                  <div className="error-detail">{msg.content}</div>
                </div>
              </div>
            );
          }

          // Assistant message container (data-testid="assistant-message")
          const { metadata } = msg;
          const isCache = metadata?.resolution_source === 'LLM_CACHE';

          return (
            <div key={msg.id} className="message-wrapper assistant-wrapper">
              <div data-testid="assistant-message" className="assistant-message-container">
                <div className="assistant-bubble">
                  <div className="message-sender">Assistant</div>
                  <div className="message-text">{msg.content}</div>
                </div>

                {/* Metadata Row */}
                {metadata && (
                  <div className="metadata-bar">
                    <span
                      data-testid="meta-source"
                      className={`meta-badge ${isCache ? 'badge-cache' : 'badge-live'}`}
                    >
                      {metadata.resolution_source}
                    </span>

                    <span className="meta-item">
                      <span className="meta-icon">🤖</span>
                      <span data-testid="meta-model" className="meta-value">
                        {metadata.model}
                      </span>
                    </span>

                    <span className="meta-item">
                      <span className="meta-icon">⚡</span>
                      <span data-testid="meta-latency" className="meta-value">
                        {metadata.latency_ms} ms
                      </span>
                    </span>

                    <span className="meta-item">
                      <span className="meta-label">Prompt:</span>
                      <span data-testid="meta-input-tokens" className="meta-value">
                        {metadata.input_tokens}
                      </span>
                    </span>

                    <span className="meta-item">
                      <span className="meta-label">Output:</span>
                      <span data-testid="meta-output-tokens" className="meta-value">
                        {metadata.output_tokens}
                      </span>
                    </span>

                    {metadata.key_id && (
                      <span className="meta-item key-tag">
                        <span className="meta-label">Key:</span>
                        <span className="meta-value">{metadata.key_id}</span>
                      </span>
                    )}

                    {metadata.fallback_attempts > 0 && (
                      <span className="meta-item fallback-tag">
                        <span>Retries: {metadata.fallback_attempts}</span>
                      </span>
                    )}
                  </div>
                )}
              </div>
            </div>
          );
        })}

        {loading && (
          <div className="message-wrapper assistant-wrapper">
            <div className="typing-indicator">
              <span></span>
              <span></span>
              <span></span>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </main>

      {/* Input Area */}
      <footer className="input-area">
        <form onSubmit={handleSendMessage} className="input-form">
          <textarea
            data-testid="chat-input"
            ref={inputRef}
            rows={1}
            value={inputMessage}
            onChange={(e) => setInputMessage(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Type your message here... (Press Enter to send)"
            disabled={loading}
            className="chat-textarea"
          />
          <button
            data-testid="send-button"
            type="submit"
            disabled={!inputMessage.trim() || loading}
            className="send-btn"
          >
            {loading ? 'Sending...' : 'Send'}
          </button>
        </form>
      </footer>
    </div>
  );
}
