import React, { useState, useEffect, useRef, useCallback } from 'react';
import './App.css';

const genSessionId = () => `s-${Math.random().toString(36).substring(2, 10)}`;

const SIM_OPTIONS = [
  { value: 'none', label: 'No failure simulation' },
  { value: 'key_1=429', label: 'key_1 → 429 (Rate Limit)' },
  { value: 'key_1=500', label: 'key_1 → 500 (Server Error)' },
  { value: '*=429', label: '* → 429 (All keys fail)' },
  { value: 'custom', label: 'Custom rule…' },
];

export default function App() {
  const [sessionId] = useState(genSessionId);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [systemPrompt, setSystemPrompt] = useState('');
  const [showSys, setShowSys] = useState(false);
  const [sim, setSim] = useState('none');
  const [customSim, setCustomSim] = useState('');
  const [loading, setLoading] = useState(false);
  const [health, setHealth] = useState(null);

  const endRef = useRef(null);
  const inputRef = useRef(null);
  const backendUrl = import.meta.env.VITE_BACKEND_URL || 'http://localhost:8000';

  useEffect(() => {
    fetch(`${backendUrl}/health`)
      .then(r => r.ok ? r.json() : null)
      .then(d => setHealth(d))
      .catch(() => setHealth({ status: 'offline' }));
  }, [backendUrl]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading]);

  const send = useCallback(async () => {
    const text = input.trim();
    if (!text || loading) return;

    const userMsg = { id: Date.now(), role: 'user', content: text };
    setMessages(prev => [...prev, userMsg]);
    setInput('');
    setLoading(true);

    const headers = { 'Content-Type': 'application/json' };
    const failureHeader = sim === 'custom' ? customSim.trim() : sim !== 'none' ? sim : null;
    if (failureHeader) headers['X-Simulate-Failure'] = failureHeader;

    const payload = { session_id: sessionId, message: text };
    if (systemPrompt.trim()) payload.system_prompt = systemPrompt.trim();

    try {
      const res = await fetch(`${backendUrl}/chat`, {
        method: 'POST', headers, body: JSON.stringify(payload),
      });
      const data = await res.json();

      if (!res.ok) {
        const detail = data?.detail;
        const msg = typeof detail === 'string' ? detail
          : Array.isArray(detail) ? detail.map(d => d.msg).join(', ')
          : JSON.stringify(detail);
        setMessages(prev => [...prev, {
          id: Date.now() + 1, role: 'error',
          status: res.status, content: msg,
        }]);
      } else {
        setMessages(prev => [...prev, {
          id: Date.now() + 1, role: 'assistant',
          content: data.reply, metadata: data.metadata,
        }]);
      }
    } catch {
      setMessages(prev => [...prev, {
        id: Date.now() + 1, role: 'error',
        content: `Cannot reach backend at ${backendUrl}.`,
      }]);
    } finally {
      setLoading(false);
      inputRef.current?.focus();
    }
  }, [input, loading, sim, customSim, sessionId, systemPrompt, backendUrl]);

  const onKeyDown = e => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); }
  };

  const isOnline = health?.status === 'ok';

  return (
    <div className="app">
      {/* Topbar */}
      <header className="topbar">
        <div className="topbar-left">
          <div className="vercel-logo">
            <div className="vercel-triangle" />
            <span className="topbar-title">Lyftr AI</span>
          </div>
          <span className="topbar-divider">/</span>
          <span className="topbar-subtitle">LLM Gateway</span>
        </div>

        <div className="topbar-right">
          <div className="session-badge">
            {sessionId}
          </div>
          <div className="session-badge" style={{ gap: 6 }}>
            <span className={`health-dot ${isOnline ? 'online' : 'offline'}`} />
            <span className="health-label">
              {isOnline ? `${health.keys_configured} keys · cache on` : 'Connecting…'}
            </span>
          </div>
        </div>
      </header>

      <div className="main-layout">
        {/* Sidebar */}
        <aside className="sidebar">
          {/* Failure Simulation */}
          <div className="sidebar-section">
            <div className="sidebar-label">Failover Test Hook</div>
            <select
              className="sim-select"
              value={sim}
              onChange={e => setSim(e.target.value)}
            >
              {SIM_OPTIONS.map(o => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
            {sim === 'custom' && (
              <input
                className="custom-input"
                type="text"
                placeholder="e.g. key_1=429,key_2=500"
                value={customSim}
                onChange={e => setCustomSim(e.target.value)}
              />
            )}
          </div>

          {/* System Prompt */}
          <div className="sidebar-section">
            <div className="sidebar-label">System Prompt</div>
            <button className="sys-toggle" onClick={() => setShowSys(!showSys)}>
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="12" cy="12" r="3"/><path d="M19.07 4.93a10 10 0 0 1 0 14.14M4.93 4.93a10 10 0 0 0 0 14.14"/>
              </svg>
              {showSys ? 'Hide prompt' : 'Set custom prompt'}
            </button>
            {showSys && (
              <textarea
                data-testid="system-prompt-input"
                className="sys-textarea"
                rows={4}
                placeholder="You are a helpful assistant…"
                value={systemPrompt}
                onChange={e => setSystemPrompt(e.target.value)}
              />
            )}
          </div>

          {/* Info */}
          <div className="sidebar-info">
            <div className="sidebar-label" style={{ marginBottom: 8 }}>Session Info</div>
            <div className="info-row">
              <span className="info-key">Status</span>
              <span className={`info-val ${isOnline ? 'green' : ''}`}>
                {isOnline ? 'Ready' : 'Offline'}
              </span>
            </div>
            <div className="info-row">
              <span className="info-key">Keys</span>
              <span className="info-val">{health?.keys_configured ?? '—'}</span>
            </div>
            <div className="info-row">
              <span className="info-key">Cache</span>
              <span className="info-val green">{health?.cache_enabled ? 'On' : 'Off'}</span>
            </div>
            <div className="info-row">
              <span className="info-key">Msgs</span>
              <span className="info-val">{messages.filter(m => m.role !== 'error').length}</span>
            </div>
          </div>
        </aside>

        {/* Chat panel */}
        <div className="chat-panel">
          <div className="messages">
            {messages.length === 0 && (
              <div className="empty-state">
                <div className="empty-icon">
                  <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                    <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
                  </svg>
                </div>
                <h3>Start a conversation</h3>
                <p>
                  Send a message to the LLM gateway. Identical prompts in a new session will return <code>LLM_CACHE</code> instantly.
                  Use the sidebar to simulate key failover.
                </p>
              </div>
            )}

            {messages.map(msg => {
              if (msg.role === 'user') {
                return (
                  <div key={msg.id} className="msg-row user">
                    <div className="msg-role-label">You</div>
                    <div className="user-bubble">{msg.content}</div>
                  </div>
                );
              }

              if (msg.role === 'error') {
                return (
                  <div key={msg.id} className="msg-row error-row">
                    <div className="error-card">
                      <div className="error-title">
                        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                          <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
                        </svg>
                        Error {msg.status ? `${msg.status}` : ''}
                      </div>
                      <div className="error-body">{msg.content}</div>
                    </div>
                  </div>
                );
              }

              const { metadata: m } = msg;
              const isCache = m?.resolution_source === 'LLM_CACHE';

              return (
                <div key={msg.id} className="msg-row assistant" data-testid="assistant-message">
                  <div className="msg-role-label">Assistant</div>
                  <div className="assistant-bubble">{msg.content}</div>

                  {m && (
                    <div className="meta-strip">
                      <span data-testid="meta-source" className={`meta-tag ${isCache ? 'source-cache' : 'source-live'}`}>
                        {isCache ? '⚡ CACHE' : '→ LIVE'}
                        &nbsp;{m.resolution_source}
                      </span>

                      <span data-testid="meta-model" className="meta-tag neutral">
                        {m.model}
                      </span>

                      <span data-testid="meta-latency" className="meta-tag neutral">
                        {m.latency_ms} ms
                      </span>

                      <span className="meta-tag neutral">
                        ↑ <span data-testid="meta-input-tokens">{m.input_tokens}</span>
                        &nbsp;↓ <span data-testid="meta-output-tokens">{m.output_tokens}</span> tok
                      </span>

                      {m.key_id && (
                        <span className="meta-tag neutral">{m.key_id}</span>
                      )}

                      {m.fallback_attempts > 0 && (
                        <span className="meta-tag warn">
                          {m.fallback_attempts} retry
                        </span>
                      )}
                    </div>
                  )}
                </div>
              );
            })}

            {loading && (
              <div className="msg-row assistant">
                <div className="typing"><span/><span/><span/></div>
              </div>
            )}

            <div ref={endRef} />
          </div>

          {/* Input */}
          <div className="input-area">
            <div className="input-wrap">
              <textarea
                data-testid="chat-input"
                ref={inputRef}
                className="chat-input"
                rows={1}
                placeholder="Message Lyftr AI…"
                value={input}
                disabled={loading}
                onChange={e => setInput(e.target.value)}
                onKeyDown={onKeyDown}
              />
              <button
                data-testid="send-button"
                className="send-btn"
                disabled={!input.trim() || loading}
                onClick={send}
              >
                {loading ? (
                  <>
                    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" style={{animation:'spin 1s linear infinite'}}>
                      <path d="M21 12a9 9 0 1 1-6.219-8.56"/>
                    </svg>
                    Sending
                  </>
                ) : (
                  <>
                    Send
                    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/>
                    </svg>
                  </>
                )}
              </button>
            </div>
            <div className="input-hint">Press Enter to send · Shift+Enter for new line</div>
          </div>
        </div>
      </div>

      <style>{`@keyframes spin{from{transform:rotate(0deg)}to{transform:rotate(360deg)}}`}</style>
    </div>
  );
}
