import { useState } from 'react';
import api from '../lib/axios';

export default function ContactComposeModal({ displayId, contact, onClose, onSent }) {
  const [role, setRole] = useState('notified');
  const [body, setBody] = useState('');
  const [sending, setSending] = useState(false);
  const [error, setError] = useState(null);

  async function handleSend() {
    if (!body.trim()) return;
    setSending(true);
    setError(null);
    try {
      await api.post(`/api/incidents/${displayId}/contact-messages/`, {
        contact_id: contact.contact_id,
        role,
        body,
      });
      onSent();
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to send message.');
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="w-full max-w-lg rounded-lg border border-border bg-card p-6 shadow-lg space-y-4">
        <h2 className="text-lg font-semibold text-foreground">Message {contact.name}</h2>
        <div className="flex flex-col gap-1">
          <label className="text-sm font-medium text-foreground">Role</label>
          <select
            value={role}
            onChange={e => setRole(e.target.value)}
            className="rounded-md border border-border bg-background px-2 py-1.5 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
          >
            <option value="notified">Notified</option>
            <option value="questioned">Questioned</option>
          </select>
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-sm font-medium text-foreground">Message</label>
          <textarea
            value={body}
            onChange={e => setBody(e.target.value)}
            rows={4}
            placeholder="Write your message…"
            className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
          />
        </div>
        {error && <p className="text-xs text-red-600">{error}</p>}
        <div className="flex justify-end gap-3">
          <button
            onClick={onClose}
            disabled={sending}
            className="rounded-md border border-border bg-background px-4 py-2 text-sm font-medium text-foreground hover:bg-accent disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            onClick={handleSend}
            disabled={!body.trim() || sending}
            className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
          >
            {sending ? 'Sending…' : 'Send'}
          </button>
        </div>
      </div>
    </div>
  );
}
