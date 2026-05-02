import { useState, useEffect } from 'react';
import api from '../lib/axios';
import { useOrganization } from '../context/OrgContext';

export default function EnrollmentPage() {
  const { selectedOrg, isLoading: orgLoading } = useOrganization();
  const [enrollment, setEnrollment] = useState(null);
  const [loading, setLoading] = useState(false);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!selectedOrg) return;
    setLoading(true);
    setEnrollment(null);
    api
      .get(`/api/security/enrollment/?org=${selectedOrg.slug}`)
      .then((res) => setEnrollment(res.data))
      .finally(() => setLoading(false));
  }, [selectedOrg]);

  async function handleCopy() {
    if (!enrollment) return;
    await navigator.clipboard.writeText(enrollment.install_command);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  if (orgLoading) {
    return <p className="text-sm text-muted-foreground">Loading…</p>;
  }

  if (!selectedOrg) {
    return <p className="text-sm text-muted-foreground">No organisation assigned.</p>;
  }

  return (
    <div className="max-w-3xl space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-foreground">Enroll an Agent</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Run the command below on the device you want to enroll in{' '}
          <strong className="text-foreground">{selectedOrg.name}</strong>.
        </p>
      </div>

      {loading && <p className="text-sm text-muted-foreground">Loading…</p>}

      {!loading && enrollment && (
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

          <pre className="overflow-x-auto rounded-lg border border-border bg-muted p-4 text-sm text-foreground">
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
    </div>
  );
}
