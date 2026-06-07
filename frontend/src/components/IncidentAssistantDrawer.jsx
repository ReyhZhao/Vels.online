import { useState, useRef, useEffect } from 'react';
import api from '../lib/axios';

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
      // Record audit event (best-effort; don't block on failure)
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
 * Conversational incident assistant drawer.
 * Stateless: replays message history each turn; grounding is recomputed server-side.
 * Proposed actions are presented as confirm/dismiss cards.
 */
export default function IncidentAssistantDrawer({ displayId, onClose, onActionConfirmed }) {
  const [messages, setMessages] = useState([]);
  const [pendingActions, setPendingActions] = useState([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const threadRef = useRef(null);

  useEffect(() => {
    if (threadRef.current) {
      threadRef.current.scrollTop = threadRef.current.scrollHeight;
    }
  }, [messages, loading, pendingActions]);

  async function handleSend() {
    const content = input.trim();
    if (!content || loading) return;
    const userMsg = { role: 'user', content };
    const nextMessages = [...messages, userMsg];
    setMessages(nextMessages);
    setInput('');
    setLoading(true);
    setError(null);

    try {
      const res = await api.post(`/api/incidents/${displayId}/assistant/`, {
        messages: nextMessages,
      });
      const { assistant_reply, proposed_actions, warnings } = res.data;
      setMessages(prev => [...prev, { role: 'assistant', content: assistant_reply }]);
      if (proposed_actions?.length) {
        setPendingActions(prev => [...prev, ...proposed_actions]);
      }
      if (warnings?.length) {
        setError(warnings.join(' '));
      }
    } catch (err) {
      const d = err.response?.data;
      if (err.response?.status === 503) {
        setError('The incident assistant is unavailable. Check the LLM provider configuration.');
      } else {
        setError(d?.detail || d?.reason || 'Failed to get a response.');
      }
    } finally {
      setLoading(false);
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
      <div className="absolute inset-0 bg-black/40" onClick={onClose} />
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
            onClick={onClose}
            aria-label="Close assistant"
            className="text-lg text-muted-foreground hover:text-foreground transition-colors"
          >
            ✕
          </button>
        </div>

        {/* Message thread */}
        <div ref={threadRef} className="flex-1 overflow-y-auto thin-scrollbar px-4 py-3 space-y-3 min-h-0">
          {messages.length === 0 && !loading && (
            <p className="text-xs text-muted-foreground text-center mt-8">
              Ask about this incident — severity, linked alerts, suggested next steps.
            </p>
          )}
          {messages.map((msg, i) => (
            <div key={i} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
              <div
                className={`rounded-lg px-3 py-2 text-xs max-w-[85%] whitespace-pre-wrap ${
                  msg.role === 'user'
                    ? 'bg-primary text-primary-foreground'
                    : 'bg-muted text-foreground'
                }`}
              >
                {msg.content}
              </div>
            </div>
          ))}
          {loading && (
            <div className="flex justify-start">
              <div className="rounded-lg px-3 py-2 text-xs bg-muted text-muted-foreground animate-pulse">
                Thinking…
              </div>
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
              disabled={loading}
              className="flex-1 rounded-md border border-border bg-background px-2 py-1.5 text-xs focus:outline-none focus:ring-1 focus:ring-ring resize-none disabled:opacity-50"
            />
            <button
              type="button"
              onClick={handleSend}
              disabled={!input.trim() || loading}
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
