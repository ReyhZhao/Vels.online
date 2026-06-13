import { useState, useEffect, useCallback, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import api from '../lib/axios';
import { streamSSE } from '../lib/parseSSE';

// Hunt detail (ADR-0015/0016/0018): a hunt opens in a Scoping dialogue (the model
// grills the seed, committing no findings) until the human fires the "Begin hunt" gate
// that starts the evidence-committing search. Streamed transcript, the proposed plan
// card, findings grouped by org with per-org propose-and-confirm Incident buttons,
// cancel, and follow-up turns. The SSE tail is reconnectable (?after=<lastSeq>).

const TERMINAL = ['completed', 'cancelled', 'error'];
const IN_FLIGHT = ['running', 'scoping_running', 'created'];
const LOOKBACKS = [7, 30, 90, 180];

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
    await api.post(`/api/hunts/${huntId}/turn/`, { message: followUp });
    setFollowUp('');
    await refresh();
    startStream();
  }

  if (!hunt) return <div className="p-4 text-gray-500">Loading…</div>;

  const inFlight = IN_FLIGHT.includes(hunt.status);
  const isTerminal = TERMINAL.includes(hunt.status);
  const isScoping = hunt.status === 'scoping' || hunt.status === 'scoping_running';
  const canBegin = hunt.status === 'scoping' || hunt.status === 'created';
  const canReply = !inFlight && (hunt.status === 'scoping' || hunt.status === 'completed');
  const plan = hunt.plan?.refined_question ? hunt.plan : null;
  const resultEvent = [...events].reverse().find((e) => e.event === 'result');

  return (
    <div className="w-full min-w-0 p-6 space-y-5 overflow-x-hidden">
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

      {/* Streamed transcript */}
      <div className="border rounded-lg p-3 space-y-1 text-sm font-mono max-h-80 overflow-auto break-words dark:border-gray-700">
        {events.length === 0 && <div className="text-gray-400">No activity yet.</div>}
        {events.map((e, i) => (
          <div key={i} className="text-gray-700 dark:text-gray-300 break-words">
            {e.event === 'phase' && <span className="text-blue-500">▸ phase: {e.data.phase}</span>}
            {e.event === 'tool' && <span>🔧 {e.data.tool} {e.data.summary ? `— ${e.data.summary}` : ''}</span>}
            {e.event === 'action' && <span className="text-purple-500">⚡ {e.data.tool}</span>}
            {e.event === 'result' && <span className="text-green-600">✓ {e.data.narrative || 'done'}</span>}
            {e.event === 'error' && <span className="text-red-600">✗ {e.data.detail}</span>}
          </div>
        ))}
      </div>

      {/* Narrative summary — the model emits Markdown; render it as such. */}
      {resultEvent?.data?.narrative && (
        <div className="border rounded-lg p-3 dark:border-gray-700">
          <div className="prose prose-sm dark:prose-invert max-w-none break-words">
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={{
                // Wide tables shouldn't widen the page on mobile — let them scroll on their own.
                table: ({ node, ...props }) => (
                  <div className="overflow-x-auto">
                    <table {...props} />
                  </div>
                ),
              }}
            >
              {resultEvent.data.narrative}
            </ReactMarkdown>
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

      {/* Turn input: a Scoping reply (continue the dialogue) or a post-search follow-up. */}
      {canReply && (
        <form onSubmit={sendFollowUp} className="flex gap-2">
          <input value={followUp} onChange={(e) => setFollowUp(e.target.value)}
                 placeholder={isScoping ? 'Answer or refine the question…' : 'Ask a follow-up / dig deeper…'}
                 className="flex-1 border rounded p-2 text-sm dark:bg-gray-800 dark:border-gray-700" />
          <button type="submit" className="bg-gray-800 text-white rounded px-4">
            {isScoping ? 'Send' : 'Continue'}
          </button>
        </form>
      )}
    </div>
  );
}
