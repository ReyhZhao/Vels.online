import { useState, useEffect } from 'react';
import api from '../lib/axios';
import ContactComposeModal from './ContactComposeModal';

const ROLE_CLASSES = {
  notified:   'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400',
  questioned: 'bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-400',
};

export default function ContactMessagesCard({ displayId }) {
  const [groups, setGroups] = useState([]);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState({});
  const [composingFor, setComposingFor] = useState(null);

  async function reload() {
    const r = await api.get(`/api/incidents/${displayId}/contact-messages/`);
    setGroups(r.data);
  }

  useEffect(() => {
    reload().finally(() => setLoading(false));
  }, [displayId]); // eslint-disable-line react-hooks/exhaustive-deps

  async function handleToggle(contactId) {
    const isOpening = !expanded[contactId];
    setExpanded(prev => ({ ...prev, [contactId]: isOpening }));
    if (isOpening) {
      try {
        await api.post(`/api/incidents/${displayId}/contact-messages/mark-read/`, { contact_id: contactId });
        setGroups(prev => prev.map(g =>
          g.contact_id === contactId
            ? { ...g, messages: g.messages.map(m => m.direction === 'inbound' && !m.read_at ? { ...m, read_at: new Date().toISOString() } : m) }
            : g
        ));
      } catch {
        // best-effort
      }
    }
  }

  if (loading) return null;
  if (groups.length === 0) return null;

  return (
    <div className="rounded-lg border border-border bg-card p-6 space-y-3">
      <h2 className="text-base font-semibold text-foreground">Contact Messages</h2>
      <div className="divide-y divide-border">
        {groups.map(g => {
          const hasUnread = g.messages.some(m => m.direction === 'inbound' && !m.read_at);
          const isExpanded = !!expanded[g.contact_id];

          const outbound = g.messages.filter(m => m.direction === 'outbound');
          const inboundByParent = {};
          g.messages.filter(m => m.direction === 'inbound').forEach(m => {
            const key = m.parent_id ?? 'orphan';
            if (!inboundByParent[key]) inboundByParent[key] = [];
            inboundByParent[key].push(m);
          });

          return (
            <div key={g.contact_id} className="py-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => handleToggle(g.contact_id)}
                    className="text-sm font-medium text-foreground flex items-center gap-1 hover:text-primary transition-colors"
                  >
                    <span className="text-xs">{isExpanded ? '▾' : '▸'}</span>
                    <span>{g.name}</span>
                  </button>
                  {g.department && (
                    <span className="text-xs text-muted-foreground">{g.department}</span>
                  )}
                  {hasUnread && (
                    <span
                      className="inline-flex items-center justify-center w-2 h-2 rounded-full bg-blue-500"
                      title="Unread reply"
                    />
                  )}
                </div>
                <button
                  onClick={() => setComposingFor(g)}
                  className="text-xs text-blue-500 hover:text-blue-700 transition-colors"
                >
                  Message
                </button>
              </div>

              {isExpanded && (
                <div className="mt-3 space-y-3 pl-4 border-l border-border">
                  {outbound.length === 0 && Object.values(inboundByParent).flat().length === 0 && (
                    <p className="text-xs text-muted-foreground italic">No messages yet.</p>
                  )}
                  {outbound.map(msg => (
                    <div key={msg.id} className="space-y-2">
                      <div className="rounded-md bg-muted/50 p-3">
                        <div className="flex items-center gap-2 mb-1">
                          <span className="text-xs font-medium text-foreground">Outbound</span>
                          {msg.role && (
                            <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium capitalize ${ROLE_CLASSES[msg.role] ?? ''}`}>
                              {msg.role}
                            </span>
                          )}
                          <span className="text-xs text-muted-foreground">
                            {new Date(msg.created_at).toLocaleString()}
                          </span>
                        </div>
                        <p className="text-sm text-foreground whitespace-pre-wrap">{msg.body}</p>
                      </div>
                      {(inboundByParent[msg.id] ?? []).map(reply => (
                        <div key={reply.id} className="ml-6 rounded-md bg-background border border-border p-3">
                          <div className="flex items-center gap-2 mb-1">
                            <span className="text-xs font-medium text-foreground">{g.name}</span>
                            <span className="text-xs text-muted-foreground">
                              {new Date(reply.created_at).toLocaleString()}
                            </span>
                          </div>
                          <p className="text-sm text-foreground whitespace-pre-wrap">{reply.body}</p>
                        </div>
                      ))}
                    </div>
                  ))}
                  {(inboundByParent['orphan'] ?? []).map(reply => (
                    <div key={reply.id} className="rounded-md bg-background border border-border p-3">
                      <div className="flex items-center gap-2 mb-1">
                        <span className="text-xs font-medium text-foreground">{g.name}</span>
                        <span className="text-xs text-muted-foreground">
                          {new Date(reply.created_at).toLocaleString()}
                        </span>
                      </div>
                      <p className="text-sm text-foreground whitespace-pre-wrap">{reply.body}</p>
                    </div>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {composingFor && (
        <ContactComposeModal
          displayId={displayId}
          contact={composingFor}
          onClose={() => setComposingFor(null)}
          onSent={() => { setComposingFor(null); reload(); }}
        />
      )}
    </div>
  );
}
