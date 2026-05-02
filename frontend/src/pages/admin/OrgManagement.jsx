import { useEffect, useState } from 'react';
import { Shield } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import api from '@/lib/axios';

function OrgManagement() {
  const [orgs, setOrgs] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);
  const [name, setName] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState(null);

  useEffect(() => {
    api
      .get('/api/security/organizations/')
      .then((res) => setOrgs(res.data))
      .catch(() => setError('Failed to load organisations.'))
      .finally(() => setIsLoading(false));
  }, []);

  function handleCreate(e) {
    e.preventDefault();
    if (!name.trim()) return;

    setSubmitting(true);
    setFormError(null);

    api
      .post('/api/security/organizations/', { name: name.trim() })
      .then((res) => {
        setOrgs((prev) => [...prev, res.data].sort((a, b) => a.name.localeCompare(b.name)));
        setName('');
      })
      .catch((err) => {
        const detail = err.response?.data?.detail ?? 'Failed to create organisation.';
        setFormError(detail);
      })
      .finally(() => setSubmitting(false));
  }

  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-foreground">Organisations</h1>
        <p className="text-sm text-muted-foreground">
          Manage customer organisations and their Wazuh agent groups.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Add Organisation</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleCreate} className="flex items-start gap-3">
            <div className="flex-1 space-y-1">
              <Input
                placeholder="Organisation name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                disabled={submitting}
              />
              {formError && <p className="text-sm text-destructive">{formError}</p>}
            </div>
            <Button type="submit" disabled={submitting || !name.trim()}>
              {submitting ? 'Creating…' : 'Create'}
            </Button>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">All Organisations</CardTitle>
        </CardHeader>
        <CardContent>
          {isLoading && <p className="text-sm text-muted-foreground">Loading…</p>}
          {error && <p className="text-sm text-destructive">{error}</p>}
          {!isLoading && !error && orgs.length === 0 && (
            <p className="text-sm text-muted-foreground">No organisations yet.</p>
          )}
          {!isLoading && !error && orgs.length > 0 && (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left text-muted-foreground">
                  <th className="pb-2 font-medium">Name</th>
                  <th className="pb-2 font-medium">Slug</th>
                  <th className="pb-2 font-medium">Wazuh group</th>
                </tr>
              </thead>
              <tbody>
                {orgs.map((org) => (
                  <tr key={org.id} className="border-b last:border-0">
                    <td className="py-3 font-medium text-foreground">{org.name}</td>
                    <td className="py-3 font-mono text-muted-foreground">{org.slug}</td>
                    <td className="py-3 font-mono text-muted-foreground">{org.wazuh_group}</td>
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

export default OrgManagement;
