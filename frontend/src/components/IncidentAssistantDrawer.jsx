import { useState, useRef, useEffect, useCallback } from 'react';
import api from '../lib/axios';
import { parseSSEChunk } from '../lib/parseSSE';

function getCookie(name) {
  const match = document.cookie.match(new RegExp('(^|;\\s*)' + name + '=([^;]*)'));
  return match ? decodeURIComponent(match[2]) : null;
}

// Live activity chip shown while a turn streams.
function ActivityChip({ kind, text, isError }) {
  if (kind === 'phase') {
    return (
      <p className="text-[11px] text-muted-foreground italic">{text}</p>
    );
  }
  if (kind === 'action') {
    return (
      <p className="text-[11px] text-emerald-600 dark:text-emerald-400">✓ {text}</p>
    );
  }
  if (isError) {
    return <p className="text-[11px] text-amber-600 dark:text-amber-400">{text}</p>;
  }
  return <p className="text-[11px] text-muted-foreground">{text}</p>;
}

// Compact, collapsible trace of what the assistant looked up / searched this turn.
function ToolTrace({ trace }) {
  const [open, setOpen] = useState(false);
  const reads = trace.filter(t => !t.is_write);
  if (reads.length === 0) return null;
  return (
    <div className="mt-1 max-w-[85%] text-[11px] text-muted-foreground">
      <button
        onClick={() => setOpen(o => !o)}
        className="hover:text-foreground transition-colors"
      >
        {open ? '▾' : '▸'} {reads.length} lookup{reads.length === 1 ? '' : 's'}
      </button>
      {open && (
        <ul className="mt-0.5 space-y-0.5 pl-3">
          {reads.map((t, i) => (
            <li key={i} className={t.error ? 'text-amber-600 dark:text-amber-400' : ''}>
              {t.error ? `${t.tool}: ${t.error}` : (t.summary || t.tool)}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function ProposedActionCard({ action, displayId, onConfirmed, onDismiss }) {
  const [confirming, setConfirming] = useState(false);
  const [error, setError] = useState(null);

  async function handleConfirm() {
    setConfirming(true);
    setError(null);
    try {
      if (action.type === 'update_field') {
        await api.patch(`/api/incidents/${displayId}/`, {
          [action.payload.field]: action.payload.value,
        });
      } else if (action.type === 'transition_state') {
        await api.post(`/api/incidents/${displayId}/transition/`, {
          state: action.payload.state,
          ...(action.payload.closure_reason ? { closure_reason: action.payload.closure_reason } : {}),
          ...(action.payload.duplicate_of ? { duplicate_of: action.payload.duplicate_of } : {}),
        });
      } else if (action.type === 'apply_task_template') {
        await api.post(`/api/incidents/${displayId}/apply-template/`, {
          template_id: action.payload.template_id,
        });
      } else if (action.type === 'create_comment') {
        await api.post(`/api/incidents/${displayId}/comments/`, {
          body: action.payload.text,
          is_internal: action.payload.internal !== false,
        });
      } else if (action.type === 'send_contact_message') {
        await api.post(`/api/incidents/${displayId}/contact-messages/`, {
          contact_id: action.payload.contact_id,
          role: 'notified',
          body: action.payload.message,
        });
      }
      api.post(`/api/incidents/${displayId}/assistant-confirm/`, {
        action_type: action.type,
        action_label: action.label,
      }).catch(() => {});
      onConfirmed(action);
    } catch (err) {
      const d = err.response?.data;
      setError(d?.detail || 'Action failed.');
    } finally {
      setConfirming(false);
    }
  }

  const typeLabel = {
    update_field: 'Update field',
    transition_state: 'State transition',
    apply_task_template: 'Apply template',
    create_comment: 'Add comment',
    send_contact_message: 'Send contact message',
  }[action.type] ?? action.type;

  return (
    <div className="rounded-md border border-border bg-background p-3 space-y-2">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">{typeLabel}</p>
          <p className="text-sm text-foreground mt-0.5">{action.label}</p>
        </div>
        <button
          type="button"
          onClick={() => onDismiss(action)}
          aria-label="Dismiss action"
          className="shrink-0 text-xs text-muted-foreground hover:text-foreground"
        >
          ✕
        </button>
      </div>
      {action.type === 'create_comment' && (
        <div className="rounded bg-muted px-2 py-1.5 text-xs text-foreground whitespace-pre-wrap">
          {action.payload.text}
          <span className="ml-1 text-muted-foreground">({action.payload.internal !== false ? 'internal' : 'org-visible'})</span>
        </div>
      )}
      {action.type === 'send_contact_message' && (
        <div className="space-y-1">
          <p className="text-xs text-muted-foreground">To: <span className="text-foreground font-medium">{action.payload.contact_name}</span></p>
          <div className="rounded bg-muted px-2 py-1.5 text-xs text-foreground whitespace-pre-wrap">{action.payload.message}</div>
        </div>
      )}
      {error && <p className="text-xs text-destructive">{error}</p>}
      <button
        type="button"
        onClick={handleConfirm}
        disabled={confirming}
        className="w-full rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-colors"
      >
        {confirming ? 'Applying…' : 'Confirm'}
      </button>
    </div>
  );
}

/**
 * Conversational incident assistant drawer — streaming variant (ADR-0014).
 *
 * Uses fetch + ReadableStream (not axios, not EventSource) so we can POST the
 * messages[] body. Auth uses session cookies + manual X-CSRFToken header.
 * Closing the drawer mid-turn aborts the request via AbortController.
 * The incident is refetched once on 'done' to reflect auto-actions.
 */
export default function IncidentAssistantDrawer({ displayId, onClose, onActionConfirmed }) {
  const [messages, setMessages] = useState([]);
  const [pendingActions, setPendingActions] = useState([]);
  const [input, setInput] = useState('');
  const [streaming, setStreaming] = useState(false);
  const [liveActivity, setLiveActivity] = useState([]); // chips shown while streaming
  const [error, setError] = useState(null);
  const threadRef = useRef(null);
  const abortRef = useRef(null);

  useEffect(() => {
    if (threadRef.current) {
      threadRef.current.scrollTop = threadRef.current.scrollHeight;
    }
  }, [messages, streaming, pendingActions, liveActivity]);

  // Abort in-flight request when drawer is closed.
  const handleClose = useCallback(() => {
    abortRef.current?.abort();
    onClose();
  }, [onClose]);

  async function handleSend() {
    const content = input.trim();
    if (!content || streaming) return;
    const userMsg = { role: 'user', content };
    const nextMessages = [...messages, userMsg];
    setMessages(nextMessages);
    setInput('');
    setStreaming(true);
    setLiveActivity([]);
    setError(null);

    const controller = new AbortController();
    abortRef.current = controller;

    // Collect per-turn trace for the completed assistant message.
    const turnTrace = [];
    const turnActions = [];

    try {
      const response = await fetch(`/api/incidents/${displayId}/assistant/`, {
        method: 'POST',
        credentials: 'include',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': getCookie('csrftoken') || '',
        },
        body: JSON.stringify({ messages: nextMessages }),
        signal: controller.signal,
      });

      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        if (response.status === 503) {
          setError('The incident assistant is unavailable. Check the LLM provider configuration.');
        } else {
          setError(body?.detail || `Error ${response.status}`);
        }
        return;
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      const buf = { remainder: '' };

      let assistantReply = '';
      let proposedActions = [];
      let warnings = [];
      let streamDone = false;

      while (!streamDone) {
        const { done, value } = await reader.read();
        if (done) break;
        const chunk = decoder.decode(value, { stream: true });
        const events = parseSSEChunk(chunk, buf);

        for (const ev of events) {
          if (ev.event === 'phase') {
            const label = ev.data.phase === 'research' ? 'Researching…' : 'Synthesising…';
            setLiveActivity(prev => [...prev, { kind: 'phase', text: label }]);
          } else if (ev.event === 'tool') {
            turnTrace.push(ev.data);
            if (!ev.data.is_write) {
              const label = ev.data.error ? `${ev.data.tool}: ${ev.data.error}` : (ev.data.summary || ev.data.tool);
              setLiveActivity(prev => [...prev, { kind: 'tool', text: label, isError: !!ev.data.error }]);
            }
          } else if (ev.event === 'action') {
            turnActions.push(ev.data);
            setLiveActivity(prev => [...prev, { kind: 'action', text: ev.data.summary || ev.data.tool }]);
          } else if (ev.event === 'result') {
            assistantReply = ev.data.assistant_reply || '';
            proposedActions = ev.data.proposed_actions || [];
            warnings = ev.data.warnings || [];
          } else if (ev.event === 'error') {
            setError(ev.data.detail || 'The assistant encountered an error.');
          } else if (ev.event === 'done') {
            streamDone = true;
            break;
          }
        }
      }

      reader.releaseLock();

      if (assistantReply) {
        setMessages(prev => [...prev, {
          role: 'assistant',
          content: assistantReply,
          tool_trace: turnTrace,
          auto_actions: turnActions,
        }]);
      }
      if (proposedActions.length) {
        setPendingActions(prev => [...prev, ...proposedActions]);
      }
      if (warnings.length) {
        setError(warnings.join(' '));
      }
      // Refetch incident once to reflect auto-actions without mid-stream thrash.
      if (streamDone) {
        onActionConfirmed?.();
      }
    } catch (err) {
      if (err.name !== 'AbortError') {
        setError('Failed to get a response.');
      }
    } finally {
      setStreaming(false);
      setLiveActivity([]);
      abortRef.current = null;
    }
  }

  function handleDismiss(dismissed) {
    setPendingActions(prev => prev.filter(a => a !== dismissed));
  }

  function handleConfirmed(confirmed) {
    setPendingActions(prev => prev.filter(a => a !== confirmed));
    onActionConfirmed?.();
  }

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <div className="absolute inset-0 bg-black/40" onClick={handleClose} />
      <div className="relative flex h-full w-full max-w-lg flex-col border-l border-border bg-card shadow-2xl">

        {/* Header */}
        <div className="flex shrink-0 items-center justify-between border-b border-border px-5 py-4">
          <div>
            <h2 className="text-base font-semibold text-foreground">Incident Assistant</h2>
            <p className="mt-0.5 text-xs text-muted-foreground">
              Ask about this incident or request proposed actions
            </p>
          </div>
          <button
            onClick={handleClose}
            aria-label="Close assistant"
            className="text-lg text-muted-foreground hover:text-foreground transition-colors"
          >
            ✕
          </button>
        </div>

        {/* Message thread */}
        <div ref={threadRef} className="flex-1 overflow-y-auto thin-scrollbar px-4 py-3 space-y-3 min-h-0">
          {messages.length === 0 && !streaming && (
            <p className="text-xs text-muted-foreground text-center mt-8">
              Ask about this incident — severity, linked alerts, suggested next steps.
            </p>
          )}
          {messages.map((msg, i) => (
            <div key={i} className={`flex flex-col ${msg.role === 'user' ? 'items-end' : 'items-start'}`}>
              <div
                className={`rounded-lg px-3 py-2 text-xs max-w-[85%] whitespace-pre-wrap ${
                  msg.role === 'user'
                    ? 'bg-primary text-primary-foreground'
                    : 'bg-muted text-foreground'
                }`}
              >
                {msg.content}
              </div>
              {msg.role === 'assistant' && msg.auto_actions?.length > 0 && (
                <div className="mt-1 max-w-[85%] space-y-0.5">
                  {msg.auto_actions.map((a, j) => (
                    <p key={j} className="text-[11px] text-emerald-600 dark:text-emerald-400">
                      ✓ {a.summary || a.tool}
                    </p>
                  ))}
                </div>
              )}
              {msg.role === 'assistant' && msg.tool_trace?.length > 0 && (
                <ToolTrace trace={msg.tool_trace} />
              )}
            </div>
          ))}

          {/* Live activity stream while streaming */}
          {streaming && (
            <div className="flex flex-col items-start space-y-0.5">
              {liveActivity.length === 0 ? (
                <div className="rounded-lg px-3 py-2 text-xs bg-muted text-muted-foreground animate-pulse">
                  Connecting…
                </div>
              ) : (
                <div className="space-y-0.5 pl-1">
                  {liveActivity.map((chip, i) => (
                    <ActivityChip key={i} {...chip} />
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Proposed actions */}
          {pendingActions.length > 0 && (
            <div className="space-y-2 pt-1">
              <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                Proposed actions
              </p>
              {pendingActions.map((action, i) => (
                <ProposedActionCard
                  key={i}
                  action={action}
                  displayId={displayId}
                  onConfirmed={handleConfirmed}
                  onDismiss={handleDismiss}
                />
              ))}
            </div>
          )}
        </div>

        {/* Error */}
        {error && (
          <div className="shrink-0 border-t border-yellow-200 bg-yellow-50 dark:border-yellow-700 dark:bg-yellow-900/20 px-4 py-2">
            <p className="text-xs text-yellow-800 dark:text-yellow-300">{error}</p>
          </div>
        )}

        {/* Input */}
        <div className="shrink-0 border-t border-border px-4 py-3">
          <div className="flex gap-2">
            <textarea
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={e => {
                if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) handleSend();
              }}
              placeholder="Ask about the incident… (⌘Enter to send)"
              rows={2}
              disabled={streaming}
              className="flex-1 rounded-md border border-border bg-background px-2 py-1.5 text-xs focus:outline-none focus:ring-1 focus:ring-ring resize-none disabled:opacity-50"
            />
            <button
              type="button"
              onClick={handleSend}
              disabled={!input.trim() || streaming}
              aria-label="Send message"
              className="self-end rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-colors"
            >
              Send
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
