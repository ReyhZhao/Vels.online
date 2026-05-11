import { useState } from 'react';
import { useLocation } from 'react-router-dom';
import api from '../lib/axios';

export default function ReportIssueModal({ open, onClose }) {
  const location = useLocation();
  const [type, setType] = useState('bug');
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);
  const [issueUrl, setIssueUrl] = useState(null);

  function reset() {
    setType('bug');
    setTitle('');
    setDescription('');
    setSubmitting(false);
    setError(null);
    setIssueUrl(null);
  }

  function handleClose() {
    reset();
    onClose();
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const res = await api.post('/api/feedback/issue/', {
        type,
        title,
        description,
        path: location.pathname,
      });
      setIssueUrl(res.data.issue_url);
    } catch (err) {
      const data = err.response?.data;
      if (data && typeof data === 'object' && !data.detail) {
        const msgs = Object.entries(data).map(([k, v]) => `${k}: ${v}`).join(' ');
        setError(msgs);
      } else {
        setError(data?.detail || 'Failed to submit issue.');
      }
    } finally {
      setSubmitting(false);
    }
  }

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="w-full max-w-lg rounded-lg border border-border bg-card shadow-xl">
        <div className="flex items-center justify-between px-6 py-4 border-b border-border">
          <h2 className="text-base font-semibold text-foreground">Report an issue</h2>
          <button
            onClick={handleClose}
            aria-label="Close"
            className="rounded-md p-1 text-muted-foreground hover:text-foreground hover:bg-accent transition-colors"
          >
            ✕
          </button>
        </div>

        {issueUrl ? (
          <div className="px-6 py-8 text-center space-y-3">
            <p className="text-sm text-foreground font-medium">Issue created successfully.</p>
            <a
              href={issueUrl}
              target="_blank"
              rel="noreferrer"
              className="text-sm text-primary underline break-all"
            >
              {issueUrl}
            </a>
            <div className="pt-2">
              <button
                onClick={handleClose}
                className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
              >
                Close
              </button>
            </div>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="px-6 py-5 space-y-4">
            {error && (
              <div role="alert" className="rounded-md border border-destructive/50 bg-destructive/10 px-4 py-3 text-sm text-destructive">
                {error}
              </div>
            )}

            <div className="flex flex-col gap-1.5">
              <label className="text-sm font-medium text-foreground" htmlFor="issue-type">Type</label>
              <select
                id="issue-type"
                value={type}
                onChange={e => setType(e.target.value)}
                className="rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
              >
                <option value="bug">Bug</option>
                <option value="feature">Feature request</option>
              </select>
            </div>

            <div className="flex flex-col gap-1.5">
              <label className="text-sm font-medium text-foreground" htmlFor="issue-title">Title</label>
              <input
                id="issue-title"
                type="text"
                value={title}
                onChange={e => setTitle(e.target.value)}
                required
                placeholder="Short summary of the issue"
                className="rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
              />
            </div>

            <div className="flex flex-col gap-1.5">
              <label className="text-sm font-medium text-foreground" htmlFor="issue-description">Description</label>
              <textarea
                id="issue-description"
                value={description}
                onChange={e => setDescription(e.target.value)}
                required
                rows={4}
                placeholder="Describe the issue or feature in detail"
                className="rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring resize-none"
              />
            </div>

            <div className="flex flex-col gap-1.5">
              <label className="text-sm font-medium text-foreground">Current page</label>
              <p className="rounded-md border border-border bg-muted px-3 py-2 text-sm font-mono text-muted-foreground">
                {location.pathname}
              </p>
            </div>

            <div className="flex justify-end gap-3 pt-1">
              <button
                type="button"
                onClick={handleClose}
                disabled={submitting}
                className="rounded-md border border-border bg-background px-4 py-2 text-sm font-medium text-foreground hover:bg-accent disabled:opacity-50 transition-colors"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={submitting || !title || !description}
                className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-colors"
              >
                {submitting ? 'Submitting…' : 'Submit issue'}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
