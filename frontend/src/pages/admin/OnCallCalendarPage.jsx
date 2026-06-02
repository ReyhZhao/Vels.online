import { useState, useEffect } from 'react';
import { CalendarClock, Plus, Pencil, Trash2, X, Check } from 'lucide-react';
import api from '../../lib/axios';
import { useAuth } from '../../context/AuthContext';

function ShiftBlocksPanel() {
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

  async function fetchBlocks() {
    setLoading(true);
    setError(null);
    try {
      const res = await api.get('/api/oncall/blocks/');
      setBlocks(res.data);
    } catch (err) {
      setError('Failed to load shift blocks.');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { fetchBlocks(); }, []);

  function startEdit(block) {
    setEditingId(block.id);
    setForm({
      label: block.label,
      start_time: block.start_time,
      end_time: block.end_time,
      order: String(block.order),
    });
    setTilingError(null);
  }

  function cancelEdit() {
    setEditingId(null);
    setShowForm(false);
    setForm({ label: '', start_time: '', end_time: '', order: '' });
    setTilingError(null);
  }

  async function handleSave() {
    setSaving(true);
    setTilingError(null);
    const payload = { ...form, order: parseInt(form.order, 10) };
    try {
      if (editingId) {
        await api.patch(`/api/oncall/blocks/${editingId}/`, payload);
      } else {
        await api.post('/api/oncall/blocks/', payload);
      }
      cancelEdit();
      fetchBlocks();
    } catch (err) {
      const detail = err.response?.data?.detail || err.response?.data || 'Failed to save block.';
      setTilingError(typeof detail === 'string' ? detail : JSON.stringify(detail));
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(blockId) {
    if (!window.confirm('Delete this shift block? This will be validated against 24/7 coverage.')) return;
    setTilingError(null);
    try {
      await api.delete(`/api/oncall/blocks/${blockId}/`);
      fetchBlocks();
    } catch (err) {
      const detail = err.response?.data?.detail || 'Failed to delete block.';
      setTilingError(typeof detail === 'string' ? detail : JSON.stringify(detail));
    }
  }

  return (
    <div className="rounded-lg border border-border p-4 space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-base font-semibold text-foreground">Shift Blocks</h2>
        {isAdmin && !showForm && !editingId && (
          <button
            onClick={() => { setShowForm(true); setTilingError(null); }}
            className="flex items-center gap-1 rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
          >
            <Plus className="h-4 w-4" />
            Add block
          </button>
        )}
      </div>

      {tilingError && (
        <div className="rounded-md border border-destructive/50 bg-destructive/10 px-4 py-3 text-sm text-destructive">
          {tilingError}
        </div>
      )}

      {loading && <p className="text-sm text-muted-foreground">Loading…</p>}
      {error && <p className="text-sm text-destructive">{error}</p>}

      {!loading && blocks.length === 0 && (
        <p className="text-sm text-muted-foreground">No shift blocks configured.</p>
      )}

      <ul className="divide-y divide-border">
        {blocks.map((block) => (
          <li key={block.id} className="py-3">
            {editingId === block.id ? (
              <BlockForm
                form={form}
                setForm={setForm}
                onSave={handleSave}
                onCancel={cancelEdit}
                saving={saving}
              />
            ) : (
              <div className="flex items-center justify-between">
                <div>
                  <span className="text-sm font-medium text-foreground">{block.label}</span>
                  <span className="ml-2 text-xs text-muted-foreground">
                    {block.start_time} – {block.end_time} (order: {block.order})
                  </span>
                </div>
                {isAdmin && (
                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => startEdit(block)}
                      className="rounded-md p-1.5 text-muted-foreground hover:bg-accent hover:text-foreground transition-colors"
                      title="Edit"
                    >
                      <Pencil className="h-4 w-4" />
                    </button>
                    <button
                      onClick={() => handleDelete(block.id)}
                      className="rounded-md p-1.5 text-muted-foreground hover:bg-destructive/10 hover:text-destructive transition-colors"
                      title="Delete"
                    >
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
          <BlockForm
            form={form}
            setForm={setForm}
            onSave={handleSave}
            onCancel={cancelEdit}
            saving={saving}
          />
        </div>
      )}
    </div>
  );
}

function BlockForm({ form, setForm, onSave, onCancel, saving }) {
  return (
    <div className="grid grid-cols-2 gap-3">
      <div className="col-span-2">
        <label className="block text-xs font-medium text-muted-foreground mb-1">Label</label>
        <input
          type="text"
          value={form.label}
          onChange={(e) => setForm((f) => ({ ...f, label: e.target.value }))}
          className="w-full rounded-md border border-border bg-background px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
          placeholder="e.g. Morning"
        />
      </div>
      <div>
        <label className="block text-xs font-medium text-muted-foreground mb-1">Start time (UTC)</label>
        <input
          type="time"
          value={form.start_time}
          onChange={(e) => setForm((f) => ({ ...f, start_time: e.target.value }))}
          className="w-full rounded-md border border-border bg-background px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
        />
      </div>
      <div>
        <label className="block text-xs font-medium text-muted-foreground mb-1">End time (UTC, 00:00=midnight)</label>
        <input
          type="time"
          value={form.end_time}
          onChange={(e) => setForm((f) => ({ ...f, end_time: e.target.value }))}
          className="w-full rounded-md border border-border bg-background px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
        />
      </div>
      <div>
        <label className="block text-xs font-medium text-muted-foreground mb-1">Order</label>
        <input
          type="number"
          value={form.order}
          onChange={(e) => setForm((f) => ({ ...f, order: e.target.value }))}
          className="w-full rounded-md border border-border bg-background px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
          min="1"
        />
      </div>
      <div className="col-span-2 flex gap-2 justify-end mt-1">
        <button
          onClick={onCancel}
          className="flex items-center gap-1 rounded-md border border-border px-3 py-1.5 text-sm text-foreground hover:bg-accent transition-colors"
        >
          <X className="h-4 w-4" />
          Cancel
        </button>
        <button
          onClick={onSave}
          disabled={saving}
          className="flex items-center gap-1 rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-colors"
        >
          <Check className="h-4 w-4" />
          {saving ? 'Saving…' : 'Save'}
        </button>
      </div>
    </div>
  );
}

export default function OnCallCalendarPage() {
  const { user } = useAuth();
  const isStaff = user?.is_staff;

  return (
    <div className="mx-auto max-w-5xl px-4 py-8 space-y-8">
      <div className="flex items-center gap-3">
        <CalendarClock className="h-6 w-6 text-muted-foreground" />
        <h1 className="text-2xl font-semibold text-foreground">On-Call Calendar</h1>
      </div>

      <p className="text-sm text-muted-foreground">On-Call Calendar (coming soon)</p>

      {isStaff && <ShiftBlocksPanel />}
    </div>
  );
}
