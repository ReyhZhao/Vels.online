import { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import api from '../lib/axios';
import { streamSSE } from '../lib/parseSSE';

// Hunt detail (ADR-0015/0016/0018): a chat-style view of the hunt conversation. A hunt
// opens in a Scoping dialogue (the model grills the seed, committing no findings) until
// the human fires the "Begin hunt" gate that starts the evidence-committing search. The
// thread is rendered from the persisted transcript so every reply and answer persists
// as a bubble (issue #501); live tool activity streams as a "working" indicator and the
// raw event feed lives behind a collapsible Activity log. SSE is reconnectable.

const TERMINAL = ['completed', 'cancelled', 'error'];
const IN_FLIGHT = ['running', 'scoping_running', 'created'];
const LOOKBACKS = [7, 30, 90, 180];
// The system-injected directive that starts the search (hunts.views.HuntBeginView).
// We render it as a thread divider rather than a user bubble.
const BEGIN_PREFIX = 'The scope is agreed. Begin the authoritative hunt';

// Turn the persisted transcript into ordered chat items. User + assistant text become
// bubbles; tool messages and tool-call-only assistant turns are internal (Activity log).
function conversationFrom(transcript) {
  const out = [];
  (transcript || []).forEach((m, i) => {
    const content = (m.content || '').trim();
    if (m.role === 'user') {
      if (!content) return;
      if (content.startsWith(BEGIN_PREFIX)) { out.push({ id: i, kind: 'divider', text: 'Hunt started' }); return; }
      out.push({ id: i, kind: 'user', content });
    } else if (m.role === 'assistant' && content) {
      out.push({ id: i, kind: 'assistant', content });
    }
  });
  return out;
}

function Markdown({ children }) {
  return (
    <div className="prose prose-sm dark:prose-invert max-w-none break-words">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          // Wide tables shouldn't widen the page — let them scroll on their own.
          table: ({ node, ...props }) => (
            <div className="overflow-x-auto"><table {...props} /></div>
          ),
        }}
      >
        {children}
      </ReactMarkdown>
    </div>
  );
}

export default function HuntDetail() {
  const { huntId } = useParams();
  const navigate = useNavigate();
  const [hunt, setHunt] = useState(null);
  const [events, setEvents] = useState([]);
  const [followUp, setFollowUp] = useState('');
  const [error, setError] = useState(null);
  // Begin-hunt gate scope/lookback edits (pre-filled from the plan once it loads).
  const [scopeAll, setScopeAll] = useState(true);
  const [lookback, setLookback] = useState(30);
  const [beginning, setBeginning] = useState(false);
  const lastSeq = useRef(-1);
  const abortRef = useRef(null);
  const endRef = useRef(null);

  const refresh = useCallback(async () => {
    const { data } = await api.get(`/api/hunts/${huntId}/`);
    setHunt(data);
    return data;
  }, [huntId]);

  const startStream = useCallback(() => {
    const controller = new AbortController();
    abortRef.current = controller;
    streamSSE(
      `/api/hunts/${huntId}/stream/?after=${lastSeq.current}`,
      { credentials: 'include', signal: controller.signal },
      (evt) => {
        if (evt.data?.seq != null) lastSeq.current = Math.max(lastSeq.current, evt.data.seq);
        setEvents((prev) => [...prev, evt]);
        if (evt.event === 'done') refresh();
      },
    ).catch(() => {});
  }, [huntId, refresh]);

  useEffect(() => {
    refresh().then((h) => {
      // Replay existing events first, then tail for live ones.
      (h.events || []).forEach((e) => {
        lastSeq.current = Math.max(lastSeq.current, e.seq);
      });
      setEvents((h.events || []).map((e) => ({ event: e.type, data: { ...e.data, seq: e.seq } })));
      // Pre-fill the gate's scope/lookback from the proposed plan, else the hunt's.
      const sug = h.plan?.suggested_scope;
      setScopeAll(sug ? !!sug.all_orgs : h.scope_all_orgs);
      setLookback(sug?.lookback_days || h.lookback_days);
      if (IN_FLIGHT.includes(h.status)) startStream();
    });
    return () => abortRef.current?.abort();
  }, [refresh, startStream]);

  const conversation = useMemo(() => conversationFrom(hunt?.transcript), [hunt?.transcript]);

  // Keep the thread pinned to the newest message / live activity, like a chat.
  useEffect(() => {
    endRef.current?.scrollIntoView({ block: 'end' });
  }, [conversation.length, events.length]);

  async function cancel() {
    await api.post(`/api/hunts/${huntId}/cancel/`);
    refresh();
  }

  async function begin() {
    setBeginning(true);
    setError(null);
    try {
      await api.post(`/api/hunts/${huntId}/begin/`, {
        scope_all_orgs: scopeAll,
        lookback_days: lookback,
      });
      await refresh();
      startStream();
    } catch (e) {
      setError(e.response?.data?.detail || 'Could not begin the hunt.');
    } finally {
      setBeginning(false);
    }
  }

  async function confirmIncident(orgId) {
    try {
      const { data } = await api.post(`/api/hunts/${huntId}/confirm-incident/`, { organization_id: orgId });
      navigate(`/incidents/${data.incident_display_id}`);
    } catch (e) {
      setError(e.response?.data?.detail || 'Could not create incident.');
    }
  }

  async function sendFollowUp(e) {
    e.preventDefault();
    if (!followUp.trim()) return;
    // Optimistically show the user's message immediately as a bubble, then stream.
    const message = followUp.trim();
    setHunt((h) => (h ? { ...h, transcript: [...(h.transcript || []), { role: 'user', content: message }] } : h));
    setFollowUp('');
    await api.post(`/api/hunts/${huntId}/turn/`, { message });
    await refresh();
    startStream();
  }

  if (!hunt) return <div className="p-4 text-gray-500">Loading…</div>;

  const inFlight = IN_FLIGHT.includes(hunt.status);
  const isTerminal = TERMINAL.includes(hunt.status);
  const isScoping = hunt.status === 'scoping' || hunt.status === 'scoping_running';
  const canBegin = hunt.status === 'scoping' || hunt.status === 'created';
  const canReply = !inFlight && (hunt.status === 'scoping' || hunt.status === 'completed');
  // The docked chat input is hidden only once the hunt is closed (cancelled/error);
  // otherwise it stays visible and is disabled while a turn is in flight.
  const chatClosed = hunt.status === 'cancelled' || hunt.status === 'error';
  const plan = hunt.plan?.refined_question ? hunt.plan : null;
  // The most recent live activity line, shown under the "working" indicator.
  const liveActivity = [...events].reverse().find((e) => ['tool', 'action', 'phase'].includes(e.event));
  const liveLabel = liveActivity
    ? (liveActivity.event === 'phase'
        ? `phase: ${liveActivity.data.phase}`
        : `${liveActivity.data.tool || ''}${liveActivity.data.summary ? ` — ${liveActivity.data.summary}` : ''}`)
    : 'Thinking…';

  return (
    <div className="w-full min-w-0 p-6 space-y-4 overflow-x-hidden">
      <div className="flex items-center gap-3">
        <button onClick={() => navigate('/hunting')} className="text-sm text-blue-600">← Hunts</button>
        <h1 className="text-xl font-semibold flex-1 truncate">{hunt.title}</h1>
        <span className="text-xs px-2 py-0.5 rounded bg-gray-100 dark:bg-gray-800">{hunt.status}</span>
        {!isTerminal && (
          <button onClick={cancel} className="text-sm border rounded px-3 py-1 text-red-600 dark:border-gray-700">
            Cancel
          </button>
        )}
      </div>

      <div className="text-xs text-gray-500">
        Scope: {hunt.scope_all_orgs ? 'All organisations' : 'Selected organisations'} · Lookback {hunt.lookback_days}d
      </div>

      {error && <div className="text-sm text-red-600">{error}</div>}

      {/* Chat thread — the persisted conversation as bubbles, with the input docked at
          the bottom of the panel like a chat app (issue #501). */}
      <div className="border rounded-lg dark:border-gray-700 flex flex-col max-h-[70vh]">
        <div className="p-4 overflow-y-auto flex flex-col gap-3 flex-1">
        {conversation.length === 0 && !inFlight && (
          <div className="text-sm text-gray-400">No messages yet.</div>
        )}
        {conversation.map((m) => {
          if (m.kind === 'divider') {
            return (
              <div key={m.id} className="flex items-center gap-3 text-xs text-gray-400 my-1">
                <span className="flex-1 border-t dark:border-gray-700" />
                {m.text}
                <span className="flex-1 border-t dark:border-gray-700" />
              </div>
            );
          }
          if (m.kind === 'user') {
            return (
              <div key={m.id} className="self-end max-w-[85%]">
                <div className="bg-blue-600 text-white rounded-2xl rounded-br-sm px-3 py-2 text-sm whitespace-pre-wrap break-words max-h-72 overflow-y-auto">
                  {m.content}
                </div>
              </div>
            );
          }
          return (
            <div key={m.id} className="self-start max-w-[90%]">
              <div className="bg-gray-100 dark:bg-gray-800 rounded-2xl rounded-bl-sm px-3 py-2 text-sm break-words">
                <Markdown>{m.content}</Markdown>
              </div>
            </div>
          );
        })}

        {/* Live "assistant is working" indicator while a turn is in flight. */}
        {inFlight && (
          <div className="self-start max-w-[90%]">
            <div className="bg-gray-100 dark:bg-gray-800 rounded-2xl rounded-bl-sm px-3 py-2 text-sm text-gray-500 flex items-center gap-2">
              <span className="inline-flex gap-1">
                <span className="w-1.5 h-1.5 rounded-full bg-gray-400 animate-pulse" />
                <span className="w-1.5 h-1.5 rounded-full bg-gray-400 animate-pulse [animation-delay:150ms]" />
                <span className="w-1.5 h-1.5 rounded-full bg-gray-400 animate-pulse [animation-delay:300ms]" />
              </span>
              <span className="truncate">{liveLabel}</span>
            </div>
          </div>
        )}
        <div ref={endRef} />
        </div>

        {/* Docked chat input — inline with the thread, like a chat app. Stays visible
            (disabled) while a turn is in flight, hidden only once the hunt is closed. */}
        {!chatClosed && (
          <form onSubmit={sendFollowUp} className="flex gap-2 p-3 border-t dark:border-gray-700 shrink-0">
            <input value={followUp} onChange={(e) => setFollowUp(e.target.value)}
                   disabled={!canReply}
                   placeholder={inFlight
                     ? 'Assistant is working…'
                     : (isScoping ? 'Answer or refine the question…' : 'Ask a follow-up / dig deeper…')}
                   className="flex-1 border rounded p-2 text-sm dark:bg-gray-800 dark:border-gray-700 disabled:opacity-60" />
            <button type="submit" disabled={!canReply || !followUp.trim()}
                    className="bg-gray-800 text-white rounded px-4 disabled:opacity-50">
              {isScoping ? 'Send' : 'Continue'}
            </button>
          </form>
        )}
      </div>

      {/* Scoping gate (ADR-0018): during Scoping the model refines the question and
          commits nothing; the human starts the search here. The plan card shows what
          the model proposes; scope/lookback are editable before committing. */}
      {isScoping && (
        <div className="border border-blue-200 dark:border-blue-900/50 rounded-lg p-3 space-y-3 bg-blue-50/40 dark:bg-blue-900/10">
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium">Scoping</span>
            <span className="text-xs text-gray-500">
              {hunt.status === 'scoping_running'
                ? 'The model is refining the question…'
                : 'Refine the question together, then begin the hunt.'}
            </span>
          </div>

          {plan && (
            <div className="text-sm space-y-1">
              <div><span className="font-medium">Proposed question:</span> {plan.refined_question}</div>
              {plan.hypotheses?.length > 0 && (
                <div>
                  <span className="font-medium">Hypotheses:</span>
                  <ul className="list-disc ml-5">
                    {plan.hypotheses.map((h, i) => <li key={i}>{h}</li>)}
                  </ul>
                </div>
              )}
              {plan.planned_lenses?.length > 0 && (
                <div><span className="font-medium">Planned lenses:</span> {plan.planned_lenses.join(', ')}</div>
              )}
            </div>
          )}

          <div className="flex flex-wrap items-center gap-4 text-sm">
            <label className="flex items-center gap-1">
              <input type="checkbox" checked={scopeAll} onChange={(e) => setScopeAll(e.target.checked)} />
              All organisations
            </label>
            <label className="flex items-center gap-1">
              Lookback
              <select value={lookback} onChange={(e) => setLookback(Number(e.target.value))}
                      className="border rounded p-1 dark:bg-gray-800 dark:border-gray-700">
                {LOOKBACKS.map((d) => <option key={d} value={d}>{d} days</option>)}
              </select>
            </label>
            <button onClick={begin} disabled={!canBegin || beginning}
                    className="ml-auto bg-blue-600 text-white rounded px-4 py-1.5 disabled:opacity-50">
              {beginning ? 'Starting…' : 'Begin hunt'}
            </button>
          </div>
        </div>
      )}

      {/* Findings grouped by org → propose-and-confirm Incident per org. Hidden during
          Scoping: no findings are committed until the search runs (ADR-0018). */}
      {!isScoping && (
      <div>
        <h2 className="font-medium mb-2">Findings by organisation</h2>
        {(hunt.proposed_incidents || []).length === 0 ? (
          <div className="text-sm text-gray-500">No findings to promote.</div>
        ) : (
          <div className="space-y-2">
            {hunt.proposed_incidents.map((p) => (
              <div key={p.organization_id}
                   className="flex items-center gap-3 border rounded p-2 text-sm dark:border-gray-700">
                <span className="font-medium">{p.organization_name}</span>
                <span className="text-gray-500">{p.finding_count} finding(s)</span>
                <button onClick={() => confirmIncident(p.organization_id)}
                        className="ml-auto bg-blue-600 text-white rounded px-3 py-1">
                  Create incident
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
      )}

      {/* Raw activity feed — the tool/phase event log, de-emphasised behind a toggle. */}
      {events.length > 0 && (
        <details className="text-sm">
          <summary className="cursor-pointer text-gray-500">Activity log ({events.length})</summary>
          <div className="border rounded-lg p-3 mt-2 space-y-1 font-mono max-h-72 overflow-auto break-words dark:border-gray-700">
            {events.map((e, i) => (
              <div key={i} className="text-gray-700 dark:text-gray-300 break-words">
                {e.event === 'phase' && <span className="text-blue-500">▸ phase: {e.data.phase}</span>}
                {e.event === 'tool' && <span>🔧 {e.data.tool} {e.data.summary ? `— ${e.data.summary}` : ''}</span>}
                {e.event === 'action' && <span className="text-purple-500">⚡ {e.data.tool}</span>}
                {e.event === 'result' && <span className="text-green-600">✓ result</span>}
                {e.event === 'error' && <span className="text-red-600">✗ {e.data.detail}</span>}
              </div>
            ))}
          </div>
        </details>
      )}

    </div>
  );
}
