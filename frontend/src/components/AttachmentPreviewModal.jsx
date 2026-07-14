import { useEffect, useState } from 'react';
import { X } from 'lucide-react';
import api from '../lib/axios';

// A Content-Security-Policy that neutralises phishing email HTML: no scripts, no
// remote resource loads at all (so tracking pixels / beacons never fire), inline
// styles and data: images only. Combined with a script-less sandboxed iframe it
// gives defence in depth — the sandbox blocks JS even if the CSP were bypassed.
const EMAIL_CSP =
  "default-src 'none'; img-src data:; style-src 'unsafe-inline'; font-src data:; media-src data:";

function wrapEmailHtml(html) {
  return `<!doctype html><html><head><meta charset="utf-8">` +
    `<meta http-equiv="Content-Security-Policy" content="${EMAIL_CSP}">` +
    `</head><body>${html || ''}</body></html>`;
}

function formatBytes(bytes) {
  if (!bytes) return '0 B';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1048576) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1048576).toFixed(1)} MB`;
}

function EmailView({ email }) {
  const { headers = {}, text_body, html_body, inner_attachments = [] } = email;
  const rows = [
    ['From', headers.from],
    ['To', headers.to],
    ['Cc', headers.cc],
    ['Subject', headers.subject],
    ['Date', headers.date],
  ].filter(([, v]) => v);

  return (
    <div className="space-y-3">
      <dl className="rounded-md border border-border bg-background p-3 text-sm">
        {rows.map(([label, value]) => (
          <div key={label} className="flex gap-2 py-0.5">
            <dt className="w-16 shrink-0 font-medium text-muted-foreground">{label}</dt>
            <dd className="min-w-0 break-words text-foreground">{value}</dd>
          </div>
        ))}
      </dl>

      {text_body ? (
        <pre className="max-h-[50vh] overflow-auto whitespace-pre-wrap rounded-md border border-border bg-background p-3 text-sm text-foreground">
          {text_body}
        </pre>
      ) : html_body ? (
        <iframe
          title="Email body"
          sandbox=""
          srcDoc={wrapEmailHtml(html_body)}
          className="h-[50vh] w-full rounded-md border border-border bg-white"
        />
      ) : (
        <p className="text-sm text-muted-foreground">This email has no readable body.</p>
      )}

      {inner_attachments.length > 0 && (
        <div className="text-sm">
          <p className="mb-1 font-medium text-foreground">
            Attachments in this email ({inner_attachments.length})
          </p>
          <ul className="divide-y divide-border rounded-md border border-border">
            {inner_attachments.map((a, i) => (
              <li key={i} className="flex items-center justify-between px-3 py-1.5">
                <span className="truncate text-foreground">{a.filename || '(unnamed)'}</span>
                <span className="ml-2 shrink-0 text-xs text-muted-foreground">
                  {a.content_type} · {formatBytes(a.size_bytes)}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

export default function AttachmentPreviewModal({ incidentId, attachment, onClose }) {
  const [state, setState] = useState({ loading: true, error: null, data: null });

  useEffect(() => {
    let cancelled = false;
    setState({ loading: true, error: null, data: null });
    api
      .get(`/api/incidents/${incidentId}/attachments/${attachment.id}/preview/`)
      .then((res) => {
        if (!cancelled) setState({ loading: false, error: null, data: res.data });
      })
      .catch(() => {
        if (!cancelled) setState({ loading: false, error: 'Could not load preview.', data: null });
      });
    return () => { cancelled = true; };
  }, [incidentId, attachment.id]);

  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  const { loading, error, data } = state;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label={`Preview of ${attachment.filename}`}
        className="flex max-h-[90vh] w-full max-w-3xl flex-col rounded-lg border border-border bg-card shadow-lg"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-border px-4 py-3">
          <h3 className="truncate text-sm font-semibold text-foreground">{attachment.filename}</h3>
          <button
            onClick={onClose}
            aria-label="Close preview"
            className="rounded-md p-1 text-muted-foreground hover:bg-accent hover:text-accent-foreground"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="min-h-0 flex-1 overflow-auto p-4">
          {loading ? (
            <p className="text-sm text-muted-foreground">Loading preview…</p>
          ) : error ? (
            <p className="text-sm text-destructive">{error}</p>
          ) : data?.kind === 'email' ? (
            <EmailView email={data.email} />
          ) : data?.kind === 'image' ? (
            <img
              src={data.url}
              alt={attachment.filename}
              className="mx-auto max-h-[70vh] max-w-full object-contain"
            />
          ) : data?.kind === 'pdf' ? (
            <iframe
              title={attachment.filename}
              src={data.url}
              className="h-[70vh] w-full rounded-md border border-border"
            />
          ) : data?.kind === 'text' ? (
            <iframe
              title={attachment.filename}
              src={data.url}
              sandbox=""
              className="h-[70vh] w-full rounded-md border border-border bg-white"
            />
          ) : (
            <p className="text-sm text-muted-foreground">Nothing to preview.</p>
          )}
        </div>
      </div>
    </div>
  );
}
