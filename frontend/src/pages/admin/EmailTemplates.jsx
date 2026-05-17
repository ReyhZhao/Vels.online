import { useEffect, useRef, useState } from 'react';
import api from '@/lib/axios';

const LABEL = {
  notification_digest: 'Notification Digest',
  incident_digest: 'Incident Digest',
  invite: 'Account Invitation',
  rejection: 'Signup Rejection',
  signup_request: 'New Signup Request (Admin)',
  test: 'Test Email',
};

function TemplateEditor({ template, onSave, onReset, onBack }) {
  const [subject, setSubject] = useState(template.subject);
  const [html, setHtml] = useState(template.html_body);
  const [saving, setSaving] = useState(false);
  const [resetting, setResetting] = useState(false);
  const [error, setError] = useState(null);
  const [preview, setPreview] = useState(false);
  const iframeRef = useRef(null);

  useEffect(() => {
    if (preview && iframeRef.current) {
      const doc = iframeRef.current.contentDocument;
      doc.open();
      doc.write(html);
      doc.close();
    }
  }, [preview, html]);

  async function handleSave() {
    setSaving(true);
    setError(null);
    try {
      const res = await api.put(`/api/me/email-templates/${template.name}/`, { subject, html_body: html });
      onSave(res.data);
    } catch (err) {
      setError(err.response?.data?.detail || 'Save failed.');
    } finally {
      setSaving(false);
    }
  }

  async function handleReset() {
    if (!window.confirm('Reset this template to the built-in default?')) return;
    setResetting(true);
    setError(null);
    try {
      await api.delete(`/api/me/email-templates/${template.name}/`);
      onReset(template.name);
    } catch (err) {
      setError(err.response?.data?.detail || 'Reset failed.');
    } finally {
      setResetting(false);
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <button
          onClick={onBack}
          className="text-sm text-muted-foreground hover:text-foreground transition-colors"
        >
          ← Back
        </button>
        <h2 className="text-lg font-semibold text-foreground">{LABEL[template.name] ?? template.name}</h2>
        {template.in_db === false && (
          <span className="rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground">default</span>
        )}
      </div>

      {template.description && (
        <p className="text-sm text-muted-foreground">{template.description}</p>
      )}

      <div className="space-y-1">
        <label className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Subject</label>
        <input
          value={subject}
          onChange={e => setSubject(e.target.value)}
          className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring font-mono"
        />
      </div>

      <div className="space-y-1">
        <div className="flex items-center justify-between">
          <label className="text-xs font-medium text-muted-foreground uppercase tracking-wide">HTML Body</label>
          <button
            onClick={() => setPreview(p => !p)}
            className="text-xs text-primary hover:underline"
          >
            {preview ? 'Edit' : 'Preview'}
          </button>
        </div>
        {preview ? (
          <iframe
            ref={iframeRef}
            title="Email preview"
            className="w-full rounded-md border border-border bg-white"
            style={{ height: '500px' }}
            sandbox="allow-same-origin"
          />
        ) : (
          <textarea
            value={html}
            onChange={e => setHtml(e.target.value)}
            rows={24}
            className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground font-mono focus:outline-none focus:ring-2 focus:ring-ring resize-y"
            spellCheck={false}
          />
        )}
      </div>

      {error && <p className="text-sm text-red-500">{error}</p>}

      <div className="flex items-center gap-3">
        <button
          onClick={handleSave}
          disabled={saving}
          className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
        >
          {saving ? 'Saving…' : 'Save template'}
        </button>
        {template.in_db && (
          <button
            onClick={handleReset}
            disabled={resetting}
            className="rounded-md border border-border bg-background px-4 py-2 text-sm font-medium text-foreground hover:bg-accent disabled:opacity-50"
          >
            {resetting ? 'Resetting…' : 'Reset to default'}
          </button>
        )}
      </div>
    </div>
  );
}

export default function EmailTemplates() {
  const [templates, setTemplates] = useState([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(null);

  useEffect(() => {
    api.get('/api/me/email-templates/')
      .then(res => setTemplates(res.data))
      .finally(() => setLoading(false));
  }, []);

  async function openEditor(name) {
    const res = await api.get(`/api/me/email-templates/${name}/`);
    setEditing(res.data);
  }

  function handleSaved(updated) {
    setTemplates(prev => prev.map(t => t.name === updated.name ? { ...t, ...updated } : t));
    setEditing(updated);
  }

  function handleReset(name) {
    setTemplates(prev => prev.map(t => t.name === name ? { ...t, updated_at: null } : t));
    setEditing(prev => ({ ...prev, in_db: false }));
  }

  if (editing) {
    return (
      <div className="p-6">
        <TemplateEditor
          template={editing}
          onSave={handleSaved}
          onReset={handleReset}
          onBack={() => setEditing(null)}
        />
      </div>
    );
  }

  return (
    <div className="space-y-4 p-6">
      <h1 className="text-2xl font-semibold text-foreground">Email Templates</h1>
      <p className="text-sm text-muted-foreground">
        Customise the HTML emails sent by the platform. Unsaved templates use the built-in default.
        Templates support Django template syntax: <code className="font-mono text-xs bg-muted px-1 rounded">{'{{ variable }}'}</code>.
      </p>

      {loading ? (
        <p className="text-sm text-muted-foreground">Loading…</p>
      ) : (
        <div className="overflow-hidden rounded-lg border border-border bg-card">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border">
                <th className="px-4 py-3 text-left font-medium text-muted-foreground">Template</th>
                <th className="px-4 py-3 text-left font-medium text-muted-foreground">Description</th>
                <th className="px-4 py-3 text-left font-medium text-muted-foreground">Status</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody>
              {templates.map(t => (
                <tr key={t.name} className="border-b border-border last:border-0 hover:bg-accent/50 transition-colors">
                  <td className="px-4 py-3 font-medium text-foreground">{LABEL[t.name] ?? t.name}</td>
                  <td className="px-4 py-3 text-muted-foreground text-xs max-w-xs">{t.description}</td>
                  <td className="px-4 py-3">
                    {t.updated_at ? (
                      <span className="inline-flex items-center rounded-full bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary">
                        Customised
                      </span>
                    ) : (
                      <span className="inline-flex items-center rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground">
                        Default
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <button
                      onClick={() => openEditor(t.name)}
                      className="text-xs font-medium text-primary hover:underline"
                    >
                      Edit
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
