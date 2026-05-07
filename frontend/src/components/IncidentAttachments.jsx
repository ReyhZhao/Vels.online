import { useState, useEffect, useRef } from 'react';
import api from '../lib/axios';
import { useAuth } from '../context/AuthContext';

function formatBytes(bytes) {
  if (!bytes) return '0 B';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1048576) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1048576).toFixed(1)} MB`;
}

export default function IncidentAttachments({ incidentId }) {
  const { user } = useAuth();
  const [attachments, setAttachments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState(null);
  const fileInputRef = useRef(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const res = await api.get(`/api/incidents/${incidentId}/attachments/`);
      setAttachments(res.data);
    } catch (err) {
      setError('Failed to load attachments.');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, [incidentId]);

  async function handleFileChange(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    setUploadError(null);
    try {
      const initiateRes = await api.post(`/api/incidents/${incidentId}/attachments/`, {
        filename: file.name,
        content_type: file.type || 'application/octet-stream',
        is_internal: true,
      });
      const { attachment, upload_url } = initiateRes.data;

      await fetch(upload_url, {
        method: 'PUT',
        body: file,
        headers: { 'Content-Type': file.type || 'application/octet-stream' },
      });

      await api.post(`/api/incidents/${incidentId}/attachments/${attachment.id}/confirm/`);
      await load();
    } catch (err) {
      setUploadError('Upload failed. Please try again.');
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  }

  async function handleDownload(attachment) {
    try {
      const res = await api.get(`/api/incidents/${incidentId}/attachments/${attachment.id}/download/`);
      window.open(res.data.url, '_blank', 'noopener,noreferrer');
    } catch {
      // silently fail — 404 for internal attachments surfaced by browser
    }
  }

  async function handleDelete(attachment) {
    if (!window.confirm(`Delete "${attachment.filename}"?`)) return;
    try {
      await api.delete(`/api/incidents/${incidentId}/attachments/${attachment.id}/`);
      setAttachments(prev => prev.filter(a => a.id !== attachment.id));
    } catch {
      setError('Delete failed.');
    }
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="text-base font-semibold text-foreground">Attachments</h2>
        <label className="cursor-pointer text-sm text-primary hover:underline">
          {uploading ? 'Uploading…' : '+ Add file'}
          <input
            ref={fileInputRef}
            type="file"
            className="hidden"
            disabled={uploading}
            onChange={handleFileChange}
            aria-label="Upload file"
          />
        </label>
      </div>

      {uploadError && (
        <p className="text-sm text-destructive">{uploadError}</p>
      )}

      {loading ? (
        <p className="text-sm text-muted-foreground">Loading attachments…</p>
      ) : error ? (
        <p className="text-sm text-muted-foreground italic">{error}</p>
      ) : attachments.length === 0 ? (
        <p className="text-sm text-muted-foreground">No attachments yet.</p>
      ) : (
        <ul className="divide-y divide-border">
          {attachments.map(att => (
            <li key={att.id} className="flex items-center gap-3 py-2">
              <div className="flex-1 min-w-0">
                <p className="text-sm text-foreground truncate">{att.filename}</p>
                <p className="text-xs text-muted-foreground">
                  {formatBytes(att.size_bytes)}
                  {att.is_internal && (
                    <span className="ml-2 rounded bg-amber-100 px-1 text-amber-800 text-xs">internal</span>
                  )}
                </p>
              </div>
              <button
                onClick={() => handleDownload(att)}
                className="text-sm text-primary hover:underline shrink-0"
              >
                Download
              </button>
              {user?.is_staff && (
                <button
                  onClick={() => handleDelete(att)}
                  className="text-sm text-destructive hover:underline shrink-0"
                  aria-label={`Delete ${att.filename}`}
                >
                  Delete
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
