import { useState, useEffect, useCallback, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import api from '../lib/axios';
import { streamSSE } from '../lib/parseSSE';

// Hunt detail (ADR-0015/0016): streamed transcript, findings grouped by org with
// per-org propose-and-confirm Incident buttons, cancel, and follow-up turns. The SSE
// tail is reconnectable — we pass ?after=<lastSeq> so a dropped socket catches up.

export default function HuntDetail() {
  const { huntId } = useParams();
  const navigate = useNavigate();
  const [hunt, setHunt] = useState(null);
  const [events, setEvents] = useState([]);
  const [followUp, setFollowUp] = useState('');
  const [error, setError] = useState(null);
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
      if (h.status === 'running' || h.status === 'created') startStream();
    });
    return () => abortRef.current?.abort();
  }, [refresh, startStream]);

  async function cancel() {
    await api.post(`/api/hunts/${huntId}/cancel/`);
    refresh();
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

  const running = hunt.status === 'running' || hunt.status === 'created';
  const resultEvent = [...events].reverse().find((e) => e.event === 'result');

  return (
    <div className="w-full min-w-0 p-6 space-y-5 overflow-x-hidden">
      <div className="flex items-center gap-3">
        <button onClick={() => navigate('/hunting')} className="text-sm text-blue-600">← Hunts</button>
        <h1 className="text-xl font-semibold flex-1 truncate">{hunt.title}</h1>
        <span className="text-xs px-2 py-0.5 rounded bg-gray-100 dark:bg-gray-800">{hunt.status}</span>
        {running && (
          <button onClick={cancel} className="text-sm border rounded px-3 py-1 text-red-600 dark:border-gray-700">
            Cancel
          </button>
        )}
      </div>

      <div className="text-xs text-gray-500">
        Scope: {hunt.scope_all_orgs ? 'All organisations' : 'Selected organisations'} · Lookback {hunt.lookback_days}d
      </div>

      {error && <div className="text-sm text-red-600">{error}</div>}

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

      {/* Findings grouped by org → propose-and-confirm Incident per org */}
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

      {/* Follow-up turn (resume) */}
      {!running && (
        <form onSubmit={sendFollowUp} className="flex gap-2">
          <input value={followUp} onChange={(e) => setFollowUp(e.target.value)}
                 placeholder="Ask a follow-up / dig deeper…"
                 className="flex-1 border rounded p-2 text-sm dark:bg-gray-800 dark:border-gray-700" />
          <button type="submit" className="bg-gray-800 text-white rounded px-4">Continue</button>
        </form>
      )}
    </div>
  );
}
