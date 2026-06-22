import { useState, useEffect, useCallback, useRef } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import api from '../lib/axios';
import MarkdownToolbar from './MarkdownToolbar';

const EDIT_WINDOW_MS = 15 * 60 * 1000;

// A confidence value may legitimately be 0, so test presence rather than truthiness.
function isPresent(value) {
  return value !== null && value !== undefined && value !== '';
}

// LLM confidences arrive as 0–1 floats; show them as whole percentages.
function formatConfidence(value) {
  return `${Math.round(Number(value) * 100)}%`;
}

// Whether an ai_triage comment carries any of the LLM-response fields we surface as labels.
function hasTriageLabels(metadata) {
  return (
    isPresent(metadata.primary_action) ||
    isPresent(metadata.secondary_action) ||
    isPresent(metadata.false_positive_confidence) ||
    isPresent(metadata.disposition_confidence) ||
    isPresent(metadata.subject_recommendation)
  );
}

function isEditable(comment, currentUserId) {
  if (comment.deleted_at) return false;
  if (comment.author !== currentUserId) return false;
  return Date.now() - new Date(comment.created_at).getTime() < EDIT_WINDOW_MS;
}

function isDeletable(comment, currentUserId, isStaff) {
  if (comment.deleted_at) return false;
  if (isStaff) return true;
  if (comment.author !== currentUserId) return false;
  return Date.now() - new Date(comment.created_at).getTime() < EDIT_WINDOW_MS;
}

function CommentItem({ comment, superseded = false, currentUserId, isStaff, onEdited, onDeleted }) {
  const [editing, setEditing] = useState(false);
  const [editBody, setEditBody] = useState(comment.body);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const editRef = useRef(null);

  async function handleSave() {
    setSaving(true);
    setError(null);
    try {
      const res = await api.patch(`/api/comments/${comment.id}/`, { body: editBody });
      onEdited(res.data);
      setEditing(false);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to save.');
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete() {
    setSaving(true);
    setError(null);
    try {
      await api.delete(`/api/comments/${comment.id}/`);
      onDeleted(comment.id);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to delete.');
      setSaving(false);
    }
  }

  const canEdit = isEditable(comment, currentUserId);
  const canDelete = isDeletable(comment, currentUserId, isStaff);

  return (
    <div className={`rounded-md border p-3 space-y-1 ${comment.is_internal ? 'border-amber-300 bg-amber-50 dark:bg-amber-900/10 dark:border-amber-700' : 'border-border bg-muted'} ${superseded ? 'opacity-60' : ''}`}>
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        <span className="font-medium text-foreground">
          {comment.kind === 'ai_triage' ? 'AI Triage' : comment.kind === 'system' ? 'System' : (comment.author_username ?? '[deleted user]')}
        </span>
        <span>·</span>
        <span>{new Date(comment.created_at).toLocaleString()}</span>
        {comment.is_internal && (
          <span className="ml-1 rounded-full bg-amber-200 dark:bg-amber-700 px-1.5 py-0.5 text-xs font-semibold text-amber-800 dark:text-amber-200">
            Internal
          </span>
        )}
        {superseded && (
          <span className="ml-1 rounded-full bg-slate-200 dark:bg-slate-700 px-1.5 py-0.5 text-xs font-semibold text-slate-600 dark:text-slate-300">
            Superseded
          </span>
        )}
      </div>

      {comment.kind === 'ai_triage' && comment.metadata && hasTriageLabels(comment.metadata) && (
        <div className="mt-1 flex flex-wrap gap-2">
          {comment.metadata.primary_action && (
            <span className="inline-flex items-center rounded-full bg-blue-100 dark:bg-blue-900/30 px-2.5 py-0.5 text-xs font-medium text-blue-800 dark:text-blue-300">
              {comment.metadata.primary_action.replace(/_/g, ' ')}
            </span>
          )}
          {comment.metadata.secondary_action && (
            <span className="inline-flex items-center rounded-full bg-slate-100 dark:bg-slate-800 px-2.5 py-0.5 text-xs font-medium text-slate-600 dark:text-slate-300">
              {comment.metadata.secondary_action.replace(/_/g, ' ')}
            </span>
          )}
          {isPresent(comment.metadata.false_positive_confidence) && (
            <span className="inline-flex items-center rounded-full bg-emerald-100 dark:bg-emerald-900/30 px-2.5 py-0.5 text-xs font-medium text-emerald-800 dark:text-emerald-300">
              FP confidence: {formatConfidence(comment.metadata.false_positive_confidence)}
            </span>
          )}
          {isPresent(comment.metadata.disposition_confidence) && (
            <span className="inline-flex items-center rounded-full bg-emerald-100 dark:bg-emerald-900/30 px-2.5 py-0.5 text-xs font-medium text-emerald-800 dark:text-emerald-300">
              Disposition confidence: {formatConfidence(comment.metadata.disposition_confidence)}
            </span>
          )}
          {comment.metadata.subject_recommendation && (
            <span className="inline-flex items-center rounded-full bg-purple-100 dark:bg-purple-900/30 px-2.5 py-0.5 text-xs font-medium text-purple-800 dark:text-purple-300">
              Subject: {comment.metadata.subject_recommendation.replace(/_/g, ' ')}
            </span>
          )}
        </div>
      )}

      {comment.deleted_at ? (
        <p className="text-sm italic text-muted-foreground">[deleted]</p>
      ) : editing ? (
        <div className="space-y-2">
          <MarkdownToolbar textareaRef={editRef} value={editBody} onChange={setEditBody} />
          <textarea
            ref={editRef}
            value={editBody}
            onChange={e => setEditBody(e.target.value)}
            rows={3}
            className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring resize-none"
          />
          {error && <p className="text-xs text-red-600">{error}</p>}
          <div className="flex gap-2">
            <button
              onClick={handleSave}
              disabled={saving || !editBody.trim()}
              className="rounded-md bg-primary px-3 py-1 text-xs font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
            >
              {saving ? 'Saving…' : 'Save'}
            </button>
            <button
              onClick={() => { setEditing(false); setEditBody(comment.body); }}
              disabled={saving}
              className="rounded-md border border-border px-3 py-1 text-xs font-medium text-muted-foreground hover:text-foreground disabled:opacity-50"
            >
              Cancel
            </button>
          </div>
        </div>
      ) : (
        <div className="prose prose-sm dark:prose-invert max-w-none">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{comment.body}</ReactMarkdown>
        </div>
      )}

      {!comment.deleted_at && !editing && (canEdit || canDelete) && (
        <div className="flex gap-3 pt-1">
          {canEdit && (
            <button
              onClick={() => setEditing(true)}
              className="text-xs text-muted-foreground hover:text-foreground"
            >
              Edit
            </button>
          )}
          {canDelete && (
            <button
              onClick={handleDelete}
              disabled={saving}
              className="text-xs text-red-600 hover:text-red-700 disabled:opacity-50"
            >
              Delete
            </button>
          )}
          {error && <p className="text-xs text-red-600">{error}</p>}
        </div>
      )}
    </div>
  );
}

function CommentForm({ onSubmit }) {
  const [body, setBody] = useState('');
  const [isInternal, setIsInternal] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);
  const bodyRef = useRef(null);

  async function handleSubmit(e) {
    e.preventDefault();
    if (!body.trim()) return;
    setSubmitting(true);
    setError(null);
    try {
      await onSubmit({ body: body.trim(), is_internal: isInternal });
      setBody('');
      setIsInternal(false);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to post comment.');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-2">
      <div className="rounded-md border border-border bg-background px-3 py-2 focus-within:ring-2 focus-within:ring-ring">
        <MarkdownToolbar textareaRef={bodyRef} value={body} onChange={setBody} />
        <textarea
          ref={bodyRef}
          value={body}
          onChange={e => setBody(e.target.value)}
          placeholder="Add a comment…"
          rows={3}
          disabled={submitting}
          className="w-full bg-transparent text-sm focus:outline-none resize-none disabled:opacity-50"
        />
      </div>
      <div className="flex items-center justify-between gap-3">
        <label className="flex items-center gap-1.5 text-xs text-muted-foreground cursor-pointer select-none">
          <input
            type="checkbox"
            checked={isInternal}
            onChange={e => setIsInternal(e.target.checked)}
            className="rounded border-border"
          />
          Internal note
        </label>
        <div className="flex items-center gap-2">
          {error && <p className="text-xs text-red-600">{error}</p>}
          <button
            type="submit"
            disabled={submitting || !body.trim()}
            className="rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
          >
            {submitting ? 'Posting…' : 'Post comment'}
          </button>
        </div>
      </div>
    </form>
  );
}

export default function IncidentComments({ incidentId, taskId, currentUserId, isStaff, refreshKey = 0 }) {
  const [comments, setComments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const url = taskId
    ? `/api/tasks/${taskId}/comments/`
    : `/api/incidents/${incidentId}/comments/`;

  const load = useCallback(() => {
    setLoading(true);
    api.get(url)
      .then(res => setComments(res.data))
      .catch(() => setError('Failed to load comments.'))
      .finally(() => setLoading(false));
  }, [url]);

  useEffect(() => { load(); }, [load, refreshKey]); // eslint-disable-line react-hooks/exhaustive-deps

  async function handlePost(data) {
    const postUrl = taskId
      ? `/api/tasks/${taskId}/comments/`
      : `/api/incidents/${incidentId}/comments/`;
    const res = await api.post(postUrl, data);
    setComments(prev => [...prev, res.data]);
  }

  function handleEdited(updated) {
    setComments(prev => prev.map(c => c.id === updated.id ? updated : c));
  }

  function handleDeleted(id) {
    setComments(prev => prev.map(c => c.id === id ? { ...c, deleted_at: new Date().toISOString() } : c));
  }

  // Rerunning triage posts a fresh AI Triage comment that supersedes the previous one
  // (#593). The newest ai_triage comment by created_at is current; older ones are dimmed.
  const latestTriageId = comments
    .filter(c => c.kind === 'ai_triage' && !c.deleted_at)
    .reduce((latest, c) => (
      !latest || new Date(c.created_at) >= new Date(latest.created_at) ? c : latest
    ), null)?.id;

  return (
    <div className="space-y-3">
      {error && <p className="text-xs text-red-600">{error}</p>}
      {loading ? (
        <p className="text-xs text-muted-foreground">Loading comments…</p>
      ) : comments.length === 0 ? null : (
        <div className="space-y-2">
          {comments.map(c => (
            <CommentItem
              key={c.id}
              comment={c}
              superseded={c.kind === 'ai_triage' && c.id !== latestTriageId}
              currentUserId={currentUserId}
              isStaff={isStaff}
              onEdited={handleEdited}
              onDeleted={handleDeleted}
            />
          ))}
        </div>
      )}
      <CommentForm onSubmit={handlePost} />
    </div>
  );
}
