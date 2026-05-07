import { useState } from 'react';
import api from '../lib/axios';

function DelegateDialog({ staffUsers, onConfirm, onCancel, delegating }) {
  const [selectedId, setSelectedId] = useState('');
  const [note, setNote] = useState('');
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="w-full max-w-sm rounded-lg border border-border bg-card p-6 shadow-lg space-y-4">
        <h2 className="text-lg font-semibold text-foreground">Delegate incident</h2>
        <div className="flex flex-col gap-1">
          <label className="text-sm font-medium text-foreground" htmlFor="delegate-user">
            Delegate to
          </label>
          <select
            id="delegate-user"
            value={selectedId}
            onChange={e => setSelectedId(e.target.value)}
            className="rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
          >
            <option value="">Select a staff user…</option>
            {staffUsers.map(u => (
              <option key={u.id} value={u.id}>{u.username}</option>
            ))}
          </select>
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-sm font-medium text-foreground" htmlFor="delegate-note">
            Note <span className="text-muted-foreground font-normal">(optional)</span>
          </label>
          <textarea
            id="delegate-note"
            value={note}
            onChange={e => setNote(e.target.value)}
            rows={2}
            placeholder="Add context for the delegate…"
            className="rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring resize-none"
          />
        </div>
        <div className="flex justify-end gap-3">
          <button
            onClick={onCancel}
            disabled={delegating}
            className="rounded-md border border-border bg-background px-4 py-2 text-sm font-medium text-foreground hover:bg-accent disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            onClick={() => selectedId && onConfirm(Number(selectedId), note)}
            disabled={!selectedId || delegating}
            className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
          >
            {delegating ? 'Delegating…' : 'Confirm delegation'}
          </button>
        </div>
      </div>
    </div>
  );
}

export default function DelegationPanel({ incidentId, activeDelegations, isStaff, onIncidentUpdate }) {
  const [showDialog, setShowDialog] = useState(false);
  const [staffUsers, setStaffUsers] = useState([]);
  const [delegating, setDelegating] = useState(false);
  const [returning, setReturning] = useState(null);
  const [error, setError] = useState(null);

  async function handleOpenDelegate() {
    if (staffUsers.length === 0) {
      try {
        const res = await api.get('/api/incidents/staff-users/');
        setStaffUsers(res.data);
      } catch {
        setError('Failed to load staff users.');
        return;
      }
    }
    setError(null);
    setShowDialog(true);
  }

  async function handleDelegate(userId, note) {
    setDelegating(true);
    setError(null);
    try {
      const res = await api.post(`/api/incidents/${incidentId}/delegate/`, { user_id: userId, note });
      onIncidentUpdate(res.data);
      setShowDialog(false);
    } catch (err) {
      setError(err.response?.data?.detail || 'Delegation failed.');
    } finally {
      setDelegating(false);
    }
  }

  async function handleReturn(delegationId) {
    setReturning(delegationId);
    setError(null);
    try {
      const res = await api.post(`/api/incidents/${incidentId}/delegations/${delegationId}/return/`);
      onIncidentUpdate(res.data);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to return delegation.');
    } finally {
      setReturning(null);
    }
  }

  return (
    <div className="space-y-3">
      {showDialog && (
        <DelegateDialog
          staffUsers={staffUsers}
          delegating={delegating}
          onConfirm={handleDelegate}
          onCancel={() => setShowDialog(false)}
        />
      )}

      <div className="flex items-center justify-between">
        <h2 className="text-base font-semibold text-foreground">Delegations</h2>
        {isStaff && (
          <button
            onClick={handleOpenDelegate}
            disabled={delegating}
            className="rounded-md border border-border bg-background px-3 py-1.5 text-sm font-medium text-foreground hover:bg-accent disabled:opacity-50 transition-colors"
          >
            Delegate
          </button>
        )}
      </div>

      {error && <p className="text-sm text-red-600">{error}</p>}

      {activeDelegations.length === 0 ? (
        <p className="text-sm text-muted-foreground">No active delegations.</p>
      ) : (
        <div className="flex flex-wrap gap-2">
          {activeDelegations.map(d => (
            <div
              key={d.id}
              className="flex items-center gap-2 rounded-full border border-border bg-accent px-3 py-1 text-sm"
            >
              <span className="font-medium text-foreground">{d.delegate_username}</span>
              {d.note && (
                <span className="text-muted-foreground truncate max-w-[12rem]" title={d.note}>
                  — {d.note}
                </span>
              )}
              <button
                onClick={() => handleReturn(d.id)}
                disabled={returning === d.id}
                aria-label={`Return delegation from ${d.delegate_username}`}
                className="ml-1 rounded-full text-muted-foreground hover:text-foreground disabled:opacity-50 transition-colors"
              >
                ✕
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
