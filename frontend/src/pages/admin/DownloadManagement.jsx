import { useEffect, useRef, useState } from 'react';
import { Upload, Download, Trash2 } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import api from '@/lib/axios';

const PLATFORMS = ['windows', 'linux', 'macos', 'all'];
const CATEGORIES = ['agent', 'tool', 'config'];
const PLATFORM_LABELS = { windows: 'Windows', linux: 'Linux', macos: 'macOS', all: 'All' };
const CATEGORY_LABELS = { agent: 'Agent', tool: 'Tool', config: 'Config' };

function UploadCell({ download, onUploaded }) {
  const inputRef = useRef(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState(null);

  async function handleFile(e) {
    const file = e.target.files[0];
    if (!file) return;
    setUploading(true);
    setError(null);
    const form = new FormData();
    form.append('file', file);
    try {
      const res = await api.post(`/api/security/downloads/${download.id}/upload/`, form);
      onUploaded(res.data);
    } catch {
      setError('Upload failed.');
    } finally {
      setUploading(false);
      e.target.value = '';
    }
  }

  return (
    <div className="flex items-center gap-2">
      {download.has_file ? (
        <span className="text-xs text-muted-foreground">File uploaded</span>
      ) : (
        <span className="text-xs text-muted-foreground">No file</span>
      )}
      <input ref={inputRef} type="file" className="hidden" onChange={handleFile} />
      <Button
        size="sm"
        variant="outline"
        disabled={uploading}
        onClick={() => inputRef.current?.click()}
        className="text-xs"
      >
        <Upload className="h-3 w-3 mr-1" />
        {uploading ? 'Uploading…' : download.has_file ? 'Replace' : 'Upload'}
      </Button>
      {error && <span className="text-xs text-destructive">{error}</span>}
    </div>
  );
}

function DownloadManagement() {
  const [downloads, setDownloads] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);
  const [orgs, setOrgs] = useState([]);
  const [form, setForm] = useState({ label: '', platform: 'all', category: 'agent', organization_slug: '' });
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState(null);
  const [confirmDeleteId, setConfirmDeleteId] = useState(null);
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    Promise.all([
      api.get('/api/security/downloads/'),
      api.get('/api/security/organizations/'),
    ])
      .then(([dlRes, orgRes]) => {
        setDownloads(dlRes.data);
        setOrgs(orgRes.data);
      })
      .catch(() => setError('Failed to load downloads.'))
      .finally(() => setIsLoading(false));
  }, []);

  function handleChange(e) {
    setForm((prev) => ({ ...prev, [e.target.name]: e.target.value }));
  }

  async function handleCreate(e) {
    e.preventDefault();
    if (!form.label.trim()) return;
    setSubmitting(true);
    setFormError(null);
    try {
      const payload = { ...form, label: form.label.trim() };
      if (!payload.organization_slug) delete payload.organization_slug;
      const res = await api.post('/api/security/downloads/', payload);
      setDownloads((prev) => [...prev, res.data]);
      setForm({ label: '', platform: 'all', category: 'agent', organization_slug: '' });
    } catch (err) {
      const detail = err.response?.data?.detail ?? 'Failed to create download.';
      setFormError(detail);
    } finally {
      setSubmitting(false);
    }
  }

  function handleUploaded(updated) {
    setDownloads((prev) => prev.map((d) => (d.id === updated.id ? updated : d)));
  }

  async function handleDelete(id) {
    setDeleting(true);
    try {
      await api.delete(`/api/security/downloads/${id}/`);
      setDownloads((prev) => prev.filter((d) => d.id !== id));
    } finally {
      setDeleting(false);
      setConfirmDeleteId(null);
    }
  }

  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-foreground">Downloads</h1>
        <p className="text-sm text-muted-foreground">
          Manage agent installers, tools, and config files available for download.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Add Download</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleCreate} className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div className="sm:col-span-2 space-y-1">
              <Label htmlFor="label">Label</Label>
              <Input
                id="label"
                name="label"
                placeholder="e.g. Wazuh Agent 4.7 (Linux)"
                value={form.label}
                onChange={handleChange}
                disabled={submitting}
              />
            </div>
            <div className="space-y-1">
              <Label htmlFor="platform">Platform</Label>
              <select
                id="platform"
                name="platform"
                value={form.platform}
                onChange={handleChange}
                disabled={submitting}
                className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm transition-colors"
              >
                {PLATFORMS.map((p) => (
                  <option key={p} value={p}>{PLATFORM_LABELS[p]}</option>
                ))}
              </select>
            </div>
            <div className="space-y-1">
              <Label htmlFor="category">Category</Label>
              <select
                id="category"
                name="category"
                value={form.category}
                onChange={handleChange}
                disabled={submitting}
                className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm transition-colors"
              >
                {CATEGORIES.map((c) => (
                  <option key={c} value={c}>{CATEGORY_LABELS[c]}</option>
                ))}
              </select>
            </div>
            <div className="space-y-1">
              <Label htmlFor="organization_slug">Organisation (optional — leave blank for global)</Label>
              <select
                id="organization_slug"
                name="organization_slug"
                value={form.organization_slug}
                onChange={handleChange}
                disabled={submitting}
                className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm transition-colors"
              >
                <option value="">Global (all orgs)</option>
                {orgs.map((o) => (
                  <option key={o.slug} value={o.slug}>{o.name}</option>
                ))}
              </select>
            </div>
            {formError && (
              <p className="sm:col-span-2 text-sm text-destructive">{formError}</p>
            )}
            <div className="sm:col-span-2">
              <Button type="submit" disabled={submitting || !form.label.trim()}>
                {submitting ? 'Creating…' : 'Create'}
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">All Downloads</CardTitle>
        </CardHeader>
        <CardContent>
          {isLoading && <p className="text-sm text-muted-foreground">Loading…</p>}
          {error && <p className="text-sm text-destructive">{error}</p>}
          {!isLoading && !error && downloads.length === 0 && (
            <p className="text-sm text-muted-foreground">No downloads yet.</p>
          )}
          {!isLoading && !error && downloads.length > 0 && (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left text-muted-foreground">
                  <th className="pb-2 font-medium">Label</th>
                  <th className="pb-2 font-medium">Platform</th>
                  <th className="pb-2 font-medium">Category</th>
                  <th className="pb-2 font-medium">Organisation</th>
                  <th className="pb-2 font-medium">File</th>
                  <th className="pb-2 font-medium"></th>
                </tr>
              </thead>
              <tbody>
                {downloads.map((dl) => (
                  <tr key={dl.id} className="border-b last:border-0">
                    <td className="py-3 font-medium text-foreground">{dl.label}</td>
                    <td className="py-3 text-muted-foreground">{PLATFORM_LABELS[dl.platform] ?? dl.platform}</td>
                    <td className="py-3 text-muted-foreground">{CATEGORY_LABELS[dl.category] ?? dl.category}</td>
                    <td className="py-3 font-mono text-muted-foreground">
                      {dl.organization_slug ?? <span className="italic">global</span>}
                    </td>
                    <td className="py-3">
                      <UploadCell download={dl} onUploaded={handleUploaded} />
                    </td>
                    <td className="py-3 text-right">
                      {confirmDeleteId === dl.id ? (
                        <div className="flex items-center justify-end gap-2">
                          <span className="text-xs text-muted-foreground">Remove?</span>
                          <Button
                            size="sm"
                            variant="destructive"
                            disabled={deleting}
                            onClick={() => handleDelete(dl.id)}
                            className="text-xs"
                          >
                            {deleting ? 'Removing…' : 'Yes'}
                          </Button>
                          <Button
                            size="sm"
                            variant="outline"
                            disabled={deleting}
                            onClick={() => setConfirmDeleteId(null)}
                            className="text-xs"
                          >
                            Cancel
                          </Button>
                        </div>
                      ) : (
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => setConfirmDeleteId(dl.id)}
                          className="text-xs text-muted-foreground hover:text-destructive"
                        >
                          <Trash2 className="h-3 w-3" />
                        </Button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

export default DownloadManagement;
