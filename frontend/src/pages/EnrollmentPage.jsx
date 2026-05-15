import { useState, useEffect } from 'react';
import { Download } from 'lucide-react';
import api from '../lib/axios';
import { useOrganization } from '../context/OrgContext';

const CATEGORY_LABELS = { agent: 'Agent', tool: 'Tool', config: 'Config' };
const PLATFORM_LABELS = { windows: 'Windows', linux: 'Linux', macos: 'macOS', all: 'All' };

function groupByCategory(downloads) {
  return downloads.reduce((acc, d) => {
    const key = d.category;
    if (!acc[key]) acc[key] = [];
    acc[key].push(d);
    return acc;
  }, {});
}

export default function EnrollmentPage() {
  const { selectedOrg, isLoading: orgLoading } = useOrganization();
  const [enrollment, setEnrollment] = useState(null);
  const [loading, setLoading] = useState(false);
  const [copied, setCopied] = useState(false);
  const [downloads, setDownloads] = useState([]);
  const [downloadingId, setDownloadingId] = useState(null);
  const [platform, setPlatform] = useState('linux');

  useEffect(() => {
    if (!selectedOrg) return;
    setLoading(true);
    setEnrollment(null);
    setDownloads([]);
    Promise.all([
      api.get(`/api/security/enrollment/?org=${selectedOrg.slug}`),
      api.get(`/api/security/downloads/?org=${selectedOrg.slug}`),
    ])
      .then(([enrollRes, dlRes]) => {
        setEnrollment(enrollRes.data);
        setDownloads(dlRes.data);
      })
      .finally(() => setLoading(false));
  }, [selectedOrg]);

  async function handleCopy() {
    if (!enrollment) return;
    const command = platform === 'windows'
      ? enrollment.windows_install_command
      : enrollment.install_command;
    await navigator.clipboard.writeText(command);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  async function handleDownload(downloadId) {
    setDownloadingId(downloadId);
    try {
      const res = await api.get(`/api/security/downloads/${downloadId}/presigned/`);
      const a = document.createElement('a');
      a.href = res.data.url;
      a.download = '';
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
    } finally {
      setDownloadingId(null);
    }
  }

  if (orgLoading) {
    return <p className="text-sm text-muted-foreground">Loading…</p>;
  }

  if (!selectedOrg) {
    return <p className="text-sm text-muted-foreground">No organisation assigned.</p>;
  }

  const grouped = groupByCategory(downloads);

  return (
    <div className="max-w-3xl space-y-8 p-6">
      <div>
        <h1 className="text-2xl font-semibold text-foreground">Enroll an Agent</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Run the command below on the device you want to enroll in{' '}
          <strong className="text-foreground">{selectedOrg.name}</strong>.
        </p>
      </div>

      {loading && <p className="text-sm text-muted-foreground">Loading…</p>}

      {!loading && enrollment && (
        <div className="space-y-4">
          <div className="flex gap-2">
            <button
              onClick={() => { setPlatform('linux'); setCopied(false); }}
              className={`rounded-md border px-4 py-1.5 text-sm font-medium transition-colors ${
                platform === 'linux'
                  ? 'border-primary bg-primary text-primary-foreground'
                  : 'border-border bg-background text-foreground hover:bg-accent'
              }`}
            >
              Linux
            </button>
            <button
              onClick={() => { setPlatform('windows'); setCopied(false); }}
              className={`rounded-md border px-4 py-1.5 text-sm font-medium transition-colors ${
                platform === 'windows'
                  ? 'border-primary bg-primary text-primary-foreground'
                  : 'border-border bg-background text-foreground hover:bg-accent'
              }`}
            >
              Windows
            </button>
          </div>

          {platform === 'linux' && (
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <p className="text-sm font-medium text-foreground">Install command (Linux / DEB)</p>
                <button
                  onClick={handleCopy}
                  className="rounded-md border border-border bg-background px-3 py-1 text-xs font-medium text-foreground shadow-sm hover:bg-accent transition-colors"
                >
                  {copied ? 'Copied!' : 'Copy'}
                </button>
              </div>
              <pre className="whitespace-pre-wrap break-all rounded-lg border border-border bg-muted p-4 text-sm text-foreground">
                <code data-testid="install-command">{enrollment.install_command}</code>
              </pre>
              <p className="text-xs text-muted-foreground">
                Group:{' '}
                <code className="rounded bg-muted px-1 py-0.5 font-mono">{enrollment.wazuh_group}</code>
                {enrollment.manager_host && (
                  <>
                    {' '}· Manager:{' '}
                    <code className="rounded bg-muted px-1 py-0.5 font-mono">
                      {enrollment.manager_host}
                    </code>
                  </>
                )}
              </p>
            </div>
          )}

          {platform === 'windows' && (
            <div className="space-y-6">
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <p className="text-sm font-medium text-foreground">
                    Install command (Windows — PowerShell, run as Administrator)
                  </p>
                  <button
                    onClick={handleCopy}
                    className="rounded-md border border-border bg-background px-3 py-1 text-xs font-medium text-foreground shadow-sm hover:bg-accent transition-colors"
                  >
                    {copied ? 'Copied!' : 'Copy'}
                  </button>
                </div>
                <pre className="whitespace-pre-wrap break-all rounded-lg border border-border bg-muted p-4 text-sm text-foreground">
                  <code data-testid="windows-install-command">{enrollment.windows_install_command}</code>
                </pre>
                <p className="text-xs text-muted-foreground">
                  Group:{' '}
                  <code className="rounded bg-muted px-1 py-0.5 font-mono">{enrollment.wazuh_group}</code>
                  {enrollment.manager_host && (
                    <>
                      {' '}· Manager:{' '}
                      <code className="rounded bg-muted px-1 py-0.5 font-mono">
                        {enrollment.manager_host}
                      </code>
                    </>
                  )}
                </p>
              </div>

              <div className="rounded-lg border border-border p-4 space-y-3">
                <h3 className="text-sm font-semibold text-foreground">
                  Optional: Install Sysmon (enhanced process monitoring)
                </h3>
                <ol className="space-y-1.5 text-sm text-foreground list-decimal list-inside">
                  <li>
                    Download <strong>Sysmon installer</strong> and <strong>Sysmon config</strong> from
                    the Downloads section below.
                  </li>
                  <li>
                    Open PowerShell as Administrator in the folder where you saved the files.
                  </li>
                  <li>
                    Run:{' '}
                    <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-xs">
                      sysmon64.exe -accepteula -i sysmonconfig.xml
                    </code>
                  </li>
                  <li>Sysmon runs as a service — no reboot needed.</li>
                </ol>
              </div>
            </div>
          )}
        </div>
      )}

      {!loading && downloads.length > 0 && (
        <div className="space-y-6" data-testid="downloads-section">
          <h2 className="text-lg font-semibold text-foreground">Downloads</h2>
          {Object.entries(grouped).map(([category, items]) => (
            <div key={category} className="space-y-2">
              <h3 className="text-sm font-medium text-muted-foreground uppercase tracking-wide">
                {CATEGORY_LABELS[category] ?? category}
              </h3>
              <div className="rounded-lg border border-border divide-y divide-border">
                {items.map((dl) => (
                  <div key={dl.id} className="flex items-center justify-between px-4 py-3">
                    <div>
                      <p className="text-sm font-medium text-foreground">{dl.label}</p>
                      <p className="text-xs text-muted-foreground">
                        {PLATFORM_LABELS[dl.platform] ?? dl.platform}
                      </p>
                    </div>
                    <button
                      data-testid={`download-btn-${dl.id}`}
                      onClick={() => handleDownload(dl.id)}
                      disabled={downloadingId === dl.id}
                      className="flex items-center gap-1.5 rounded-md border border-border bg-background px-3 py-1.5 text-xs font-medium text-foreground shadow-sm hover:bg-accent transition-colors disabled:opacity-50"
                    >
                      <Download className="h-3.5 w-3.5" />
                      {downloadingId === dl.id ? 'Downloading…' : 'Download'}
                    </button>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
