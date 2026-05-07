import { useState, useEffect } from 'react';
import api from '@/lib/axios';

function SubjectRow({ subject, onArchiveToggle }) {
  const [toggling, setToggling] = useState(false);

  async function handleToggle() {
    setToggling(true);
    try {
      await onArchiveToggle(subject);
    } finally {
      setToggling(false);
    }
  }

  return (
    <tr className="border-b border-border last:border-0">
      <td className="px-4 py-3 font-medium text-foreground">{subject.name}</td>
      <td className="px-4 py-3 font-mono text-xs text-muted-foreground">{subject.slug}</td>
      <td className="px-4 py-3 text-sm text-muted-foreground max-w-xs truncate">{subject.description || '—'}</td>
      <td className="px-4 py-3">
        <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${subject.archived ? 'bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400' : 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400'}`}>
          {subject.archived ? 'Archived' : 'Active'}
        </span>
      </td>
      <td className="px-4 py-3">
        <button
          onClick={handleToggle}
          disabled={toggling}
          className="rounded-md px-2 py-1 text-xs font-medium text-muted-foreground hover:bg-accent disabled:opacity-50 transition-colors"
        >
          {subject.archived ? 'Unarchive' : 'Archive'}
        </button>
      </td>
    </tr>
  );
}

export default function SubjectsAdmin() {
  const [subjects, setSubjects] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState(null);

  useEffect(() => {
    api.get('/api/subjects/')
      .then(res => setSubjects(res.data))
      .catch(() => setError('Failed to load subjects.'))
      .finally(() => setLoading(false));
  }, []);

  async function handleCreate(e) {
    e.preventDefault();
    if (!name.trim()) return;
    setSubmitting(true);
    setFormError(null);
    try {
      const res = await api.post('/api/subjects/', { name: name.trim(), description: description.trim() });
      setSubjects(prev => [...prev, res.data].sort((a, b) => a.name.localeCompare(b.name)));
      setName('');
      setDescription('');
    } catch (err) {
      setFormError(err.response?.data?.detail || 'Failed to create subject.');
    } finally {
      setSubmitting(false);
    }
  }

  async function handleArchiveToggle(subject) {
    try {
      const res = await api.patch(`/api/subjects/${subject.id}/`, { archived: !subject.archived });
      setSubjects(prev => prev.map(s => s.id === subject.id ? res.data : s));
    } catch {
      setError('Failed to update subject.');
    }
  }

  return (
    <div className="space-y-6 p-6">
      <h1 className="text-2xl font-semibold text-foreground">Incident Subjects</h1>

      <div className="rounded-lg border border-border bg-card p-6 space-y-4">
        <h2 className="text-base font-semibold text-foreground">Add Subject</h2>
        <form onSubmit={handleCreate} className="space-y-3">
          <div className="flex gap-3">
            <input
              type="text"
              placeholder="Subject name"
              value={name}
              onChange={e => setName(e.target.value)}
              disabled={submitting}
              className="flex-1 rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring disabled:opacity-50"
            />
            <input
              type="text"
              placeholder="Description (optional)"
              value={description}
              onChange={e => setDescription(e.target.value)}
              disabled={submitting}
              className="flex-1 rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring disabled:opacity-50"
            />
            <button
              type="submit"
              disabled={submitting || !name.trim()}
              className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-colors"
            >
              {submitting ? 'Creating…' : 'Create'}
            </button>
          </div>
          {formError && <p className="text-sm text-red-600">{formError}</p>}
        </form>
      </div>

      {error && <p className="text-sm text-red-600">{error}</p>}

      <div className="overflow-hidden rounded-lg border border-border bg-card">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border">
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">Name</th>
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">Slug</th>
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">Description</th>
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">Status</th>
              <th className="px-4 py-3" />
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={5} className="px-4 py-8 text-center text-muted-foreground">Loading…</td>
              </tr>
            ) : subjects.length === 0 ? (
              <tr>
                <td colSpan={5} className="px-4 py-8 text-center text-muted-foreground">No subjects.</td>
              </tr>
            ) : (
              subjects.map(s => (
                <SubjectRow key={s.id} subject={s} onArchiveToggle={handleArchiveToggle} />
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
