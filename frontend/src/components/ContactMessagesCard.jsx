import { useState, useEffect } from 'react';
import api from '../lib/axios';
import ContactComposeModal from './ContactComposeModal';

const ROLE_CLASSES = {
  notified:   'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400',
  questioned: 'bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-400',
};

export default function ContactMessagesCard({ displayId }) {
  const [groups, setGroups] = useState([]);
  const [contacts, setContacts] = useState([]);  // all linked contacts (with or without messages)
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState({});
  const [composingFor, setComposingFor] = useState(null);

  async function reload() {
    const [msgRes, contactRes] = await Promise.all([
      api.get(`/api/incidents/${displayId}/contact-messages/`),
      api.get(`/api/incidents/${displayId}/contacts/`),
    ]);
    setGroups(msgRes.data);
    setContacts(contactRes.data);
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

  // Merge: contacts with existing message groups take the group data;
  // contacts without messages are shown with an empty messages list.
  const groupsByContactId = Object.fromEntries(groups.map(g => [g.contact_id, g]));
  const mergedGroups = contacts.map(c => groupsByContactId[c.contact_id] ?? {
    contact_id: c.contact_id,
    name: c.name,
    email: c.email,
    department: c.department ?? '',
    messages: [],
  });

  // Also include any groups whose contact was removed from the incident (orphans)
  const linkedContactIds = new Set(contacts.map(c => c.contact_id));
  groups.forEach(g => {
    if (!linkedContactIds.has(g.contact_id)) mergedGroups.push(g);
  });

  if (mergedGroups.length === 0) return null;

  return (
    <div className="rounded-lg border border-border bg-card p-4 space-y-3">
      <h3 className="text-sm font-semibold text-foreground">Contact Messages</h3>
      <div className="divide-y divide-border">
        {mergedGroups.map(g => {
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
            <div key={g.contact_id} className="py-2">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => g.messages.length > 0 && handleToggle(g.contact_id)}
                    disabled={g.messages.length === 0}
                    className={`text-sm font-medium text-foreground flex items-center gap-1 transition-colors ${g.messages.length > 0 ? 'hover:text-primary' : 'cursor-default'}`}
                  >
                    {g.messages.length > 0 && (
                      <span className="text-xs">{isExpanded ? '▾' : '▸'}</span>
                    )}
                    <span>{g.name}</span>
                  </button>
                  {g.department && (
                    <span className="text-xs text-muted-foreground">{g.department}</span>
                  )}
                  {g.messages.length > 0 && (
                    <span className="text-xs text-muted-foreground">({g.messages.filter(m => m.direction === 'outbound').length} sent)</span>
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
                <div className="mt-2 space-y-2 pl-3 border-l border-border">
                  {outbound.length === 0 && Object.values(inboundByParent).flat().length === 0 && (
                    <p className="text-xs text-muted-foreground italic">No messages yet.</p>
                  )}
                  {outbound.map(msg => (
                    <div key={msg.id} className="space-y-1">
                      <div className="rounded-md bg-muted/50 p-2.5">
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
                        <div key={reply.id} className="ml-4 rounded-md bg-background border border-border p-2.5">
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
                    <div key={reply.id} className="rounded-md bg-background border border-border p-2.5">
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
