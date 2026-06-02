import { useState, useEffect, useCallback } from 'react';
import {
  CalendarClock, Plus, Pencil, Trash2, X, Check,
  ChevronLeft, ChevronRight, AlertTriangle
} from 'lucide-react';
import api from '../../lib/axios';
import { useAuth } from '../../context/AuthContext';
import { OnCallWidgetFull } from '../../components/OnCallWidget';

// ─── Helpers ─────────────────────────────────────────────────────────────────

const DAY_NAMES = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
const MONTH_NAMES = ['January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December'];

function isoWeek(date) {
  const d = new Date(date);
  d.setHours(0, 0, 0, 0);
  d.setDate(d.getDate() + 3 - ((d.getDay() + 6) % 7));
  const week1 = new Date(d.getFullYear(), 0, 4);
  const wn = 1 + Math.round(((d.getTime() - week1.getTime()) / 86400000 - 3 + ((week1.getDay() + 6) % 7)) / 7);
  return `${d.getFullYear()}-W${String(wn).padStart(2, '0')}`;
}

function formatMonth(date) {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}`;
}

function formatShiftEnd(utcString, timezone) {
  if (!utcString) return '';
  try {
    return new Date(utcString).toLocaleTimeString('en-US', {
      timeZone: timezone || 'Europe/Amsterdam',
      hour: '2-digit', minute: '2-digit', hour12: false,
    });
  } catch { return utcString; }
}

function initials(name) {
  if (!name) return '?';
  return name.split(' ').slice(0, 2).map(p => p[0]?.toUpperCase() ?? '').join('');
}

function Avatar({ name, size = 'sm' }) {
  const sizeClass = size === 'lg' ? 'h-10 w-10 text-sm' : 'h-7 w-7 text-xs';
  return (
    <div className={`flex items-center justify-center rounded-full bg-primary text-primary-foreground font-semibold shrink-0 ${sizeClass}`}>
      {initials(name)}
    </div>
  );
}

function mondayOfIsoWeek(year, week) {
  const jan4 = new Date(year, 0, 4);
  const day = jan4.getDay() || 7;
  const monday = new Date(jan4);
  monday.setDate(jan4.getDate() - (day - 1) + (week - 1) * 7);
  return monday;
}

function isCurrentShiftBlock(block, now) {
  const h = now.getUTCHours();
  const m = now.getUTCMinutes();
  const currentMin = h * 60 + m;
  const [sh, sm] = block.start_time.split(':').map(Number);
  const [eh, em] = block.end_time.split(':').map(Number);
  const startMin = sh * 60 + sm;
  let endMin = eh * 60 + em;
  if (endMin === 0) endMin = 1440;
  if (endMin <= startMin) {
    return currentMin >= startMin || currentMin < (endMin % 1440);
  }
  return currentMin >= startMin && currentMin < endMin;
}

// ─── Override Modal ───────────────────────────────────────────────────────────

function OverrideModal({ prefill, blocks, onClose, onSubmitted }) {
  const [staffUsers, setStaffUsers] = useState([]);
  const [loadingStaff, setLoadingStaff] = useState(true);
  const [form, setForm] = useState({
    date: prefill?.date || '',
    shift_block_id: prefill?.shift_block_id ? String(prefill.shift_block_id) : '',
    override_analyst_id: '',
    original_analyst_id: prefill?.original_analyst_id ? String(prefill.original_analyst_id) : '',
    note: '',
    kind: prefill?.kind || 'swap',
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [confirmHandOff, setConfirmHandOff] = useState(prefill?.handOffNow ?? false);

  useEffect(() => {
    api.get('/api/incidents/staff-users/')
      .then(res => setStaffUsers(res.data))
      .catch(() => {})
      .finally(() => setLoadingStaff(false));
  }, []);

  async function handleSubmit() {
    setSaving(true); setError(null);
    const payload = {
      date: form.date,
      shift_block_id: parseInt(form.shift_block_id, 10),
      override_analyst_id: parseInt(form.override_analyst_id, 10),
      note: form.note,
      kind: form.kind,
    };
    if (form.original_analyst_id) {
      payload.original_analyst_id = parseInt(form.original_analyst_id, 10);
    }
    try {
      await api.post('/api/oncall/overrides/', payload);
      onSubmitted?.();
      onClose();
    } catch (err) {
      const d = err.response?.data?.detail || err.response?.data || 'Failed to submit override.';
      setError(typeof d === 'string' ? d : JSON.stringify(d));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="bg-card rounded-lg border border-border shadow-xl w-full max-w-md mx-4 p-6 space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold text-foreground">
            {form.kind === 'cover_offer' ? 'Offer to Cover' : 'Request Shift Swap'}
          </h2>
          <button onClick={onClose} className="rounded-md p-1.5 text-muted-foreground hover:bg-accent transition-colors">
            <X className="h-4 w-4" />
          </button>
        </div>

        {confirmHandOff && (
          <div className="rounded-md bg-amber-50 border border-amber-200 dark:bg-amber-900/20 dark:border-amber-800 px-4 py-3 text-sm text-amber-800 dark:text-amber-300">
            You are handing off your current shift. This will request a swap for today's active block.
          </div>
        )}

        {error && (
          <div className="rounded-md border border-destructive/50 bg-destructive/10 px-4 py-3 text-sm text-destructive">{error}</div>
        )}

        <div className="space-y-3">
          <div>
            <label className="block text-xs font-medium text-muted-foreground mb-1">Kind</label>
            <select value={form.kind} onChange={e => setForm(f => ({ ...f, kind: e.target.value }))}
              className="w-full rounded-md border border-border bg-background px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-ring">
              <option value="swap">Shift Swap</option>
              <option value="cover_offer">Cover Offer</option>
            </select>
          </div>

          <div>
            <label className="block text-xs font-medium text-muted-foreground mb-1">Date</label>
            <input type="date" value={form.date} onChange={e => setForm(f => ({ ...f, date: e.target.value }))}
              className="w-full rounded-md border border-border bg-background px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-ring" />
          </div>

          <div>
            <label className="block text-xs font-medium text-muted-foreground mb-1">Shift Block</label>
            <select value={form.shift_block_id} onChange={e => setForm(f => ({ ...f, shift_block_id: e.target.value }))}
              className="w-full rounded-md border border-border bg-background px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-ring">
              <option value="">Select block…</option>
              {blocks.map(b => (
                <option key={b.id} value={b.id}>{b.label} ({b.start_time}–{b.end_time})</option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-xs font-medium text-muted-foreground mb-1">
              {form.kind === 'cover_offer' ? 'Analyst to cover' : 'Analyst to swap with'}
            </label>
            <select value={form.override_analyst_id} onChange={e => setForm(f => ({ ...f, override_analyst_id: e.target.value }))}
              disabled={loadingStaff}
              className="w-full rounded-md border border-border bg-background px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-ring disabled:opacity-50">
              <option value="">Select analyst…</option>
              {staffUsers.map(u => (
                <option key={u.id} value={u.id}>{u.first_name} {u.last_name} ({u.username})</option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-xs font-medium text-muted-foreground mb-1">Note (optional)</label>
            <textarea value={form.note} onChange={e => setForm(f => ({ ...f, note: e.target.value }))}
              rows={2}
              className="w-full rounded-md border border-border bg-background px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-ring resize-none"
              placeholder="Add a note…" />
          </div>
        </div>

        <div className="flex gap-2 justify-end pt-2">
          <button onClick={onClose}
            className="rounded-md border border-border px-4 py-2 text-sm text-foreground hover:bg-accent transition-colors">
            Cancel
          </button>
          <button onClick={handleSubmit} disabled={saving || !form.date || !form.shift_block_id || !form.override_analyst_id}
            className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-colors">
            {saving ? 'Submitting…' : 'Submit request'}
          </button>
        </div>
      </div>
    </div>
  );
}

// ─── Pending Requests Panel ───────────────────────────────────────────────────

function PendingRequestsPanel({ onUpdate }) {
  const { user } = useAuth();
  const [overrides, setOverrides] = useState([]);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(null);
  const [error, setError] = useState(null);

  const fetchOverrides = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.get('/api/oncall/overrides/');
      setOverrides(res.data);
    } catch {
      setOverrides([]);
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { fetchOverrides(); }, [fetchOverrides]);

  async function handleAction(overrideId, action) {
    setActionLoading(`${overrideId}-${action}`);
    setError(null);
    try {
      await api.post(`/api/oncall/overrides/${overrideId}/${action}/`);
      fetchOverrides();
      onUpdate?.();
    } catch (err) {
      const d = err.response?.data?.detail || `Failed to ${action} override.`;
      setError(typeof d === 'string' ? d : JSON.stringify(d));
    } finally { setActionLoading(null); }
  }

  const incoming = overrides.filter(o => o.override_analyst === user?.id);
  const outgoing = overrides.filter(o => o.initiated_by === user?.id && o.override_analyst !== user?.id);

  if (!loading && overrides.length === 0) return null;

  return (
    <div className="rounded-lg border border-border p-4 space-y-4">
      <h2 className="text-base font-semibold text-foreground">Pending Swap Requests</h2>

      {error && (
        <div className="rounded-md border border-destructive/50 bg-destructive/10 px-4 py-3 text-sm text-destructive">{error}</div>
      )}

      {loading && <p className="text-sm text-muted-foreground">Loading…</p>}

      {!loading && incoming.length > 0 && (
        <div className="space-y-2">
          <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Incoming requests</p>
          {incoming.map(o => (
            <div key={o.id} className="flex items-start gap-3 rounded-md border border-border p-3">
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-foreground">
                  {o.initiated_by_name} → {o.kind === 'cover_offer' ? 'cover offer' : 'swap request'}
                </p>
                <p className="text-xs text-muted-foreground">
                  {o.shift_block_label} · {o.date}
                </p>
                {o.note && <p className="text-xs text-muted-foreground mt-1 italic">"{o.note}"</p>}
              </div>
              <div className="flex items-center gap-2 shrink-0">
                <button
                  onClick={() => handleAction(o.id, 'accept')}
                  disabled={!!actionLoading}
                  className="rounded-md bg-green-600 px-2.5 py-1.5 text-xs font-medium text-white hover:bg-green-700 disabled:opacity-50 transition-colors"
                >
                  {actionLoading === `${o.id}-accept` ? '…' : 'Accept'}
                </button>
                <button
                  onClick={() => handleAction(o.id, 'decline')}
                  disabled={!!actionLoading}
                  className="rounded-md border border-destructive/50 px-2.5 py-1.5 text-xs font-medium text-destructive hover:bg-destructive/10 disabled:opacity-50 transition-colors"
                >
                  {actionLoading === `${o.id}-decline` ? '…' : 'Decline'}
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {!loading && outgoing.length > 0 && (
        <div className="space-y-2">
          <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Sent requests</p>
          {outgoing.map(o => (
            <div key={o.id} className="flex items-center gap-3 rounded-md border border-border p-3">
              <div className="flex-1">
                <p className="text-sm text-foreground">
                  Waiting for <span className="font-medium">{o.override_analyst_name}</span>
                </p>
                <p className="text-xs text-muted-foreground">
                  {o.shift_block_label} · {o.date} · {o.kind === 'cover_offer' ? 'cover offer' : 'swap'}
                </p>
              </div>
              <span className="rounded-full bg-amber-100 dark:bg-amber-900/30 px-2 py-0.5 text-xs text-amber-800 dark:text-amber-400">Pending</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ─── Shift Blocks Panel ───────────────────────────────────────────────────────

function BlockForm({ form, setForm, onSave, onCancel, saving }) {
  return (
    <div className="grid grid-cols-2 gap-3">
      <div className="col-span-2">
        <label className="block text-xs font-medium text-muted-foreground mb-1">Label</label>
        <input type="text" value={form.label}
          onChange={(e) => setForm(f => ({ ...f, label: e.target.value }))}
          className="w-full rounded-md border border-border bg-background px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
          placeholder="e.g. Morning" />
      </div>
      <div>
        <label className="block text-xs font-medium text-muted-foreground mb-1">Start time (UTC)</label>
        <input type="time" value={form.start_time}
          onChange={(e) => setForm(f => ({ ...f, start_time: e.target.value }))}
          className="w-full rounded-md border border-border bg-background px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-ring" />
      </div>
      <div>
        <label className="block text-xs font-medium text-muted-foreground mb-1">End time (UTC, 00:00=midnight)</label>
        <input type="time" value={form.end_time}
          onChange={(e) => setForm(f => ({ ...f, end_time: e.target.value }))}
          className="w-full rounded-md border border-border bg-background px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-ring" />
      </div>
      <div>
        <label className="block text-xs font-medium text-muted-foreground mb-1">Order</label>
        <input type="number" value={form.order} min="1"
          onChange={(e) => setForm(f => ({ ...f, order: e.target.value }))}
          className="w-full rounded-md border border-border bg-background px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-ring" />
      </div>
      <div className="col-span-2 flex gap-2 justify-end mt-1">
        <button onClick={onCancel}
          className="flex items-center gap-1 rounded-md border border-border px-3 py-1.5 text-sm text-foreground hover:bg-accent transition-colors">
          <X className="h-4 w-4" /> Cancel
        </button>
        <button onClick={onSave} disabled={saving}
          className="flex items-center gap-1 rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-colors">
          <Check className="h-4 w-4" /> {saving ? 'Saving…' : 'Save'}
        </button>
      </div>
    </div>
  );
}

function ShiftBlocksPanel({ onBlocksChanged }) {
  const { user } = useAuth();
  const isAdmin = user?.is_superuser;
  const [blocks, setBlocks] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [tilingError, setTilingError] = useState(null);
  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [form, setForm] = useState({ label: '', start_time: '', end_time: '', order: '' });
  const [saving, setSaving] = useState(false);

  const fetchBlocks = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const res = await api.get('/api/oncall/blocks/');
      setBlocks(res.data);
      onBlocksChanged?.();
    } catch { setError('Failed to load shift blocks.'); }
    finally { setLoading(false); }
  }, [onBlocksChanged]);

  useEffect(() => { fetchBlocks(); }, [fetchBlocks]);

  function startEdit(block) {
    setEditingId(block.id);
    setForm({ label: block.label, start_time: block.start_time, end_time: block.end_time, order: String(block.order) });
    setTilingError(null);
  }

  function cancelEdit() {
    setEditingId(null); setShowForm(false);
    setForm({ label: '', start_time: '', end_time: '', order: '' });
    setTilingError(null);
  }

  async function handleSave() {
    setSaving(true); setTilingError(null);
    const payload = { ...form, order: parseInt(form.order, 10) };
    try {
      if (editingId) await api.patch(`/api/oncall/blocks/${editingId}/`, payload);
      else await api.post('/api/oncall/blocks/', payload);
      cancelEdit(); fetchBlocks();
    } catch (err) {
      const d = err.response?.data?.detail || err.response?.data || 'Failed to save block.';
      setTilingError(typeof d === 'string' ? d : JSON.stringify(d));
    } finally { setSaving(false); }
  }

  async function handleDelete(blockId) {
    if (!window.confirm('Delete this shift block?')) return;
    setTilingError(null);
    try {
      await api.delete(`/api/oncall/blocks/${blockId}/`);
      fetchBlocks();
    } catch (err) {
      const d = err.response?.data?.detail || 'Failed to delete block.';
      setTilingError(typeof d === 'string' ? d : JSON.stringify(d));
    }
  }

  return (
    <div className="rounded-lg border border-border p-4 space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-base font-semibold text-foreground">Configure Shift Blocks</h2>
        {isAdmin && !showForm && !editingId && (
          <button onClick={() => { setShowForm(true); setTilingError(null); }}
            className="flex items-center gap-1 rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors">
            <Plus className="h-4 w-4" /> Add block
          </button>
        )}
      </div>
      {tilingError && (
        <div className="rounded-md border border-destructive/50 bg-destructive/10 px-4 py-3 text-sm text-destructive">{tilingError}</div>
      )}
      {loading && <p className="text-sm text-muted-foreground">Loading…</p>}
      {error && <p className="text-sm text-destructive">{error}</p>}
      {!loading && blocks.length === 0 && <p className="text-sm text-muted-foreground">No shift blocks configured.</p>}
      <ul className="divide-y divide-border">
        {blocks.map(block => (
          <li key={block.id} className="py-3">
            {editingId === block.id ? (
              <BlockForm form={form} setForm={setForm} onSave={handleSave} onCancel={cancelEdit} saving={saving} />
            ) : (
              <div className="flex items-center justify-between">
                <div>
                  <span className="text-sm font-medium text-foreground">{block.label}</span>
                  <span className="ml-2 text-xs text-muted-foreground">{block.start_time} – {block.end_time} (order: {block.order})</span>
                </div>
                {isAdmin && (
                  <div className="flex items-center gap-2">
                    <button onClick={() => startEdit(block)} className="rounded-md p-1.5 text-muted-foreground hover:bg-accent hover:text-foreground transition-colors" title="Edit">
                      <Pencil className="h-4 w-4" />
                    </button>
                    <button onClick={() => handleDelete(block.id)} className="rounded-md p-1.5 text-muted-foreground hover:bg-destructive/10 hover:text-destructive transition-colors" title="Delete">
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </div>
                )}
              </div>
            )}
          </li>
        ))}
      </ul>
      {showForm && !editingId && (
        <div className="border-t border-border pt-4">
          <p className="text-sm font-medium text-foreground mb-3">New shift block</p>
          <BlockForm form={form} setForm={setForm} onSave={handleSave} onCancel={cancelEdit} saving={saving} />
        </div>
      )}
    </div>
  );
}

// ─── Week View ────────────────────────────────────────────────────────────────

function WeekView({ blocks, weekParam, onWeekChange, onOverrideRequest, scheduleKey }) {
  const { user, staffProfile } = useAuth();
  const tz = staffProfile?.timezone || 'Europe/Amsterdam';
  const [schedule, setSchedule] = useState([]);
  const [loading, setLoading] = useState(true);

  const fetchSchedule = useCallback(async () => {
    setLoading(true);
    api.get('/api/oncall/schedule/', { params: { week: weekParam } })
      .then(res => setSchedule(res.data))
      .catch(() => setSchedule([]))
      .finally(() => setLoading(false));
  }, [weekParam]);

  useEffect(() => { fetchSchedule(); }, [fetchSchedule, scheduleKey]);

  const [yearStr, weekStr] = weekParam.split('-W');
  const year = parseInt(yearStr, 10);
  const weekNum = parseInt(weekStr, 10);
  const monday = mondayOfIsoWeek(year, weekNum);

  const now = new Date();
  const todayStr = now.toISOString().split('T')[0];

  const scheduleByDateBlock = {};
  schedule.forEach(cell => {
    scheduleByDateBlock[`${cell.date}__${cell.shift_block_id}`] = cell;
  });

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="text-base font-semibold text-foreground">Week {weekNum}, {year}</h2>
        <div className="flex items-center gap-2">
          <button onClick={() => onWeekChange(-1)} className="rounded-md p-1.5 border border-border text-muted-foreground hover:bg-accent transition-colors">
            <ChevronLeft className="h-4 w-4" />
          </button>
          <button onClick={() => onWeekChange(0)} className="rounded-md px-3 py-1.5 border border-border text-sm text-muted-foreground hover:bg-accent transition-colors">
            Today
          </button>
          <button onClick={() => onWeekChange(1)} className="rounded-md p-1.5 border border-border text-muted-foreground hover:bg-accent transition-colors">
            <ChevronRight className="h-4 w-4" />
          </button>
        </div>
      </div>

      {loading ? (
        <p className="text-sm text-muted-foreground">Loading schedule…</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-sm">
            <thead>
              <tr>
                <th className="border border-border bg-muted/50 px-2 py-2 text-left text-xs font-medium text-muted-foreground w-28">Block</th>
                {DAY_NAMES.map((day, i) => {
                  const d = new Date(monday);
                  d.setDate(d.getDate() + i);
                  const dateStr = d.toISOString().split('T')[0];
                  const isToday = dateStr === todayStr;
                  return (
                    <th key={day} className={`border border-border px-2 py-2 text-center text-xs font-medium min-w-[110px] ${isToday ? 'bg-primary/10 text-primary' : 'bg-muted/50 text-muted-foreground'}`}>
                      <div>{day}</div>
                      <div className="font-normal">{d.getDate()}/{d.getMonth() + 1}</div>
                    </th>
                  );
                })}
              </tr>
            </thead>
            <tbody>
              {blocks.map(block => (
                <tr key={block.id}>
                  <td className="border border-border bg-muted/30 px-2 py-2 text-xs font-medium text-muted-foreground">{block.label}</td>
                  {DAY_NAMES.map((_, i) => {
                    const d = new Date(monday);
                    d.setDate(d.getDate() + i);
                    const dateStr = d.toISOString().split('T')[0];
                    const isPast = dateStr < todayStr;
                    const isToday = dateStr === todayStr;
                    const isFuture = dateStr > todayStr;
                    const cell = scheduleByDateBlock[`${dateStr}__${block.id}`];
                    const isCurrentBlock = isToday && isCurrentShiftBlock(block, now);
                    const isOwnCell = cell?.analyst?.id === user?.id;

                    return (
                      <td key={i} className={`border border-border px-2 py-2 ${isPast ? 'opacity-50' : ''} ${isCurrentBlock ? 'ring-2 ring-inset ring-primary/50 bg-primary/5' : ''}`}>
                        {cell?.analyst ? (
                          <div className="flex flex-col items-center gap-1">
                            <Avatar name={cell.analyst.name} />
                            <span className="text-xs text-foreground text-center leading-tight">{cell.analyst.name}</span>
                            {cell.has_pending_override && (
                              <span className="text-xs bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-400 rounded px-1 text-center">
                                ⚠ Pending swap
                              </span>
                            )}
                            {(isFuture || isToday) && (
                              <div className="flex gap-1 mt-1">
                                {isOwnCell && (
                                  <button
                                    onClick={() => onOverrideRequest({ date: dateStr, shift_block_id: block.id, original_analyst_id: user?.id, kind: 'swap' })}
                                    className="rounded px-1.5 py-0.5 text-xs bg-primary/10 text-primary hover:bg-primary/20 transition-colors"
                                  >
                                    Override
                                  </button>
                                )}
                                {!isOwnCell && (
                                  <button
                                    onClick={() => onOverrideRequest({ date: dateStr, shift_block_id: block.id, original_analyst_id: cell.analyst.id, kind: 'cover_offer' })}
                                    className="rounded px-1.5 py-0.5 text-xs bg-muted text-muted-foreground hover:bg-accent transition-colors"
                                  >
                                    Cover
                                  </button>
                                )}
                              </div>
                            )}
                          </div>
                        ) : (
                          <div className="flex flex-col items-center gap-1">
                            <span className="text-xs text-destructive font-medium">GAP</span>
                            {(isFuture || isToday) && (
                              <button
                                onClick={() => onOverrideRequest({ date: dateStr, shift_block_id: block.id, kind: 'cover_offer' })}
                                className="rounded px-1.5 py-0.5 text-xs bg-muted text-muted-foreground hover:bg-accent transition-colors"
                              >
                                Cover
                              </button>
                            )}
                          </div>
                        )}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ─── Month View ───────────────────────────────────────────────────────────────

function MonthView({ monthParam, onMonthChange, scheduleKey }) {
  const [schedule, setSchedule] = useState([]);
  const [loading, setLoading] = useState(true);

  const fetchSchedule = useCallback(async () => {
    setLoading(true);
    api.get('/api/oncall/schedule/month/', { params: { month: monthParam } })
      .then(res => setSchedule(res.data))
      .catch(() => setSchedule([]))
      .finally(() => setLoading(false));
  }, [monthParam]);

  useEffect(() => { fetchSchedule(); }, [fetchSchedule, scheduleKey]);

  const [yearStr, monthStr] = monthParam.split('-');
  const year = parseInt(yearStr, 10);
  const month = parseInt(monthStr, 10) - 1;

  const todayStr = new Date().toISOString().split('T')[0];

  const firstDay = new Date(year, month, 1);
  const startDow = (firstDay.getDay() + 6) % 7;
  const schedByDate = Object.fromEntries(schedule.map(d => [d.date, d]));

  const cells = [];
  for (let i = 0; i < startDow; i++) cells.push(null);
  const daysInMonth = new Date(year, month + 1, 0).getDate();
  for (let d = 1; d <= daysInMonth; d++) {
    const dateStr = `${year}-${String(month + 1).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
    cells.push({ dateStr, day: d, data: schedByDate[dateStr] });
  }
  while (cells.length % 7 !== 0) cells.push(null);

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="text-base font-semibold text-foreground">{MONTH_NAMES[month]} {year}</h2>
        <div className="flex items-center gap-2">
          <button onClick={() => onMonthChange(-1)} className="rounded-md p-1.5 border border-border text-muted-foreground hover:bg-accent transition-colors">
            <ChevronLeft className="h-4 w-4" />
          </button>
          <button onClick={() => onMonthChange(0)} className="rounded-md px-3 py-1.5 border border-border text-sm text-muted-foreground hover:bg-accent transition-colors">
            Today
          </button>
          <button onClick={() => onMonthChange(1)} className="rounded-md p-1.5 border border-border text-muted-foreground hover:bg-accent transition-colors">
            <ChevronRight className="h-4 w-4" />
          </button>
        </div>
      </div>

      {loading ? (
        <p className="text-sm text-muted-foreground">Loading…</p>
      ) : (
        <div className="grid grid-cols-7 gap-px bg-border rounded-lg overflow-hidden">
          {DAY_NAMES.map(d => (
            <div key={d} className="bg-muted/50 px-2 py-2 text-center text-xs font-medium text-muted-foreground">{d}</div>
          ))}
          {cells.map((cell, i) => {
            if (!cell) return <div key={`empty-${i}`} className="bg-background min-h-[80px]" />;
            const { dateStr, day, data } = cell;
            const isToday = dateStr === todayStr;
            const hasGap = data?.has_gap ?? false;

            return (
              <div key={dateStr} className={`bg-background min-h-[80px] p-1.5 ${isToday ? 'ring-2 ring-inset ring-primary' : ''} ${hasGap ? 'bg-destructive/5' : ''}`}>
                <div className="flex items-start justify-between mb-1">
                  <span className={`text-xs font-medium ${isToday ? 'text-primary' : 'text-foreground'}`}>{day}</span>
                  {hasGap && <span className="rounded bg-destructive/20 px-1 text-xs font-bold text-destructive">GAP</span>}
                </div>
                <div className="space-y-0.5">
                  {data?.slots?.map(slot => {
                    const hasPendingOverride = slot.has_pending_override;
                    return slot.analyst ? (
                      <div key={slot.shift_block_id} className="flex items-center gap-1">
                        <div className="h-4 w-4 flex items-center justify-center rounded-full bg-primary/80 text-primary-foreground text-xs font-bold">
                          {slot.analyst.initials}
                        </div>
                        <span className="text-xs text-muted-foreground truncate">{slot.shift_block_label?.slice(0, 3)}</span>
                        {hasPendingOverride && <span className="h-1.5 w-1.5 rounded-full bg-amber-500 shrink-0" title="Pending swap" />}
                      </div>
                    ) : (
                      <div key={slot.shift_block_id} className="text-xs text-destructive">— {slot.shift_block_label?.slice(0, 3)}</div>
                    );
                  })}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ─── Main Page ────────────────────────────────────────────────────────────────

export default function OnCallCalendarPage() {
  const { user } = useAuth();
  const isStaff = user?.is_staff;

  const [view, setView] = useState('week');
  const [blocks, setBlocks] = useState([]);
  const [blocksKey, setBlocksKey] = useState(0);
  const [scheduleKey, setScheduleKey] = useState(0);
  const [overrideModal, setOverrideModal] = useState(null);

  const now = new Date();
  const [weekParam, setWeekParam] = useState(() => isoWeek(now));
  const [monthParam, setMonthParam] = useState(() => formatMonth(now));

  useEffect(() => {
    api.get('/api/oncall/blocks/')
      .then(res => setBlocks(res.data))
      .catch(() => setBlocks([]));
  }, [blocksKey]);

  function handleWeekChange(direction) {
    if (direction === 0) { setWeekParam(isoWeek(new Date())); return; }
    const [y, w] = weekParam.split('-W').map(Number);
    const d = mondayOfIsoWeek(y, w);
    d.setDate(d.getDate() + direction * 7);
    setWeekParam(isoWeek(d));
  }

  function handleMonthChange(direction) {
    if (direction === 0) { setMonthParam(formatMonth(new Date())); return; }
    const [y, m] = monthParam.split('-').map(Number);
    const d = new Date(y, m - 1 + direction, 1);
    setMonthParam(formatMonth(d));
  }

  function handleOverrideSubmitted() {
    setScheduleKey(k => k + 1);
  }

  function handleHandOffNow() {
    // Pre-fill with today + current active block
    const todayStr = new Date().toISOString().split('T')[0];
    const currentBlock = blocks.find(b => isCurrentShiftBlock(b, new Date()));
    setOverrideModal({
      date: todayStr,
      shift_block_id: currentBlock?.id,
      original_analyst_id: user?.id,
      kind: 'swap',
      handOffNow: true,
    });
  }

  return (
    <div className="mx-auto max-w-6xl px-4 py-8 space-y-8">
      <div className="flex items-center gap-3">
        <CalendarClock className="h-6 w-6 text-muted-foreground" />
        <h1 className="text-2xl font-semibold text-foreground">On-Call Calendar</h1>
      </div>

      {isStaff && <OnCallWidgetFull onHandOffNow={handleHandOffNow} />}

      {isStaff && (
        <PendingRequestsPanel onUpdate={() => setScheduleKey(k => k + 1)} />
      )}

      <div className="flex items-center gap-2">
        <button
          onClick={() => setView('week')}
          className={`rounded-md px-4 py-2 text-sm font-medium transition-colors ${view === 'week' ? 'bg-primary text-primary-foreground' : 'border border-border text-muted-foreground hover:bg-accent'}`}
        >
          Week
        </button>
        <button
          onClick={() => setView('month')}
          className={`rounded-md px-4 py-2 text-sm font-medium transition-colors ${view === 'month' ? 'bg-primary text-primary-foreground' : 'border border-border text-muted-foreground hover:bg-accent'}`}
        >
          Month
        </button>
      </div>

      {view === 'week' ? (
        <WeekView
          blocks={blocks}
          weekParam={weekParam}
          onWeekChange={handleWeekChange}
          onOverrideRequest={prefill => setOverrideModal(prefill)}
          scheduleKey={scheduleKey}
        />
      ) : (
        <MonthView
          monthParam={monthParam}
          onMonthChange={handleMonthChange}
          scheduleKey={scheduleKey}
        />
      )}

      {isStaff && (
        <ShiftBlocksPanel onBlocksChanged={() => setBlocksKey(k => k + 1)} />
      )}

      {overrideModal && (
        <OverrideModal
          prefill={overrideModal}
          blocks={blocks}
          onClose={() => setOverrideModal(null)}
          onSubmitted={handleOverrideSubmitted}
        />
      )}
    </div>
  );
}
