import { useCallback, useEffect, useState } from 'react';
import { UserCheck } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import api from '@/lib/axios';

const STATUSES = ['pending', 'approved', 'rejected', 'expired', 'completed'];

const STATUS_LABELS = {
  pending: 'Pending',
  approved: 'Approved',
  rejected: 'Rejected',
  expired: 'Expired',
  completed: 'Completed',
};

const STATUS_COLORS = {
  pending: 'bg-yellow-100 text-yellow-800',
  approved: 'bg-blue-100 text-blue-800',
  rejected: 'bg-red-100 text-red-800',
  expired: 'bg-gray-100 text-gray-600',
  completed: 'bg-green-100 text-green-800',
};

const REJECTION_REASONS = [
  'spam',
  'duplicate',
  'incomplete',
  'not_eligible',
  'other',
];

function StatusBadge({ status }) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_COLORS[status] ?? 'bg-gray-100 text-gray-600'}`}
    >
      {STATUS_LABELS[status] ?? status}
    </span>
  );
}

function RequestRow({ req, onAction }) {
  const [expanded, setExpanded] = useState(false);
  const [approveOrgName, setApproveOrgName] = useState('');
  const [rejectReason, setRejectReason] = useState('spam');
  const [rejectNote, setRejectNote] = useState('');
  const [sendEmail, setSendEmail] = useState(true);
  const [working, setWorking] = useState(false);
  const [actionError, setActionError] = useState('');
  const [conflictWarning, setConflictWarning] = useState(false);

  async function doAction(url, payload) {
    setWorking(true);
    setActionError('');
    setConflictWarning(false);
    try {
      const resp = await api.post(url, payload);
      onAction(resp.data);
      setExpanded(false);
    } catch (err) {
      const data = err.response?.data ?? {};
      if (data.conflict) {
        setConflictWarning(true);
        setActionError(data.detail ?? 'Name conflict — provide a different name.');
      } else {
        setActionError(data.detail ?? 'Action failed.');
      }
    } finally {
      setWorking(false);
    }
  }

  async function doDelete() {
    if (!window.confirm(`Delete request from ${req.email}? This will deprovision their org and Authentik group.`)) return;
    setWorking(true);
    setActionError('');
    try {
      await api.delete(`/api/signups/${req.id}/`);
      onAction(null);
    } catch (err) {
      setActionError(err.response?.data?.detail ?? 'Delete failed.');
    } finally {
      setWorking(false);
    }
  }

  return (
    <div className="border rounded-lg">
      <button
        className="w-full flex items-center justify-between px-4 py-3 text-left hover:bg-accent/50 transition-colors"
        onClick={() => setExpanded((e) => !e)}
      >
        <div className="flex items-center gap-3 flex-1 min-w-0">
          <StatusBadge status={req.status} />
          <span className="font-medium text-sm text-foreground truncate">{req.email}</span>
          <span className="text-sm text-muted-foreground hidden sm:inline truncate">{req.org_name}</span>
        </div>
        <span className="text-xs text-muted-foreground ml-4 shrink-0">
          {new Date(req.submitted_at).toLocaleDateString()}
        </span>
      </button>

      {expanded && (
        <div className="px-4 pb-4 pt-2 border-t space-y-4">
          <div className="grid grid-cols-2 gap-x-6 gap-y-1 text-sm">
            <span className="text-muted-foreground">Name</span>
            <span>{req.full_name}</span>
            <span className="text-muted-foreground">Email</span>
            <span>{req.email}</span>
            <span className="text-muted-foreground">Org name</span>
            <span>{req.org_name}</span>
            <span className="text-muted-foreground">Intended use</span>
            <span className="whitespace-pre-wrap">{req.intended_use}</span>
            {req.approved_org_name && (
              <>
                <span className="text-muted-foreground">Approved org</span>
                <span>{req.approved_org_name}</span>
              </>
            )}
            {req.invite_expires_at && (
              <>
                <span className="text-muted-foreground">Invite expires</span>
                <span>{new Date(req.invite_expires_at).toLocaleString()}</span>
              </>
            )}
            {req.rejection_reason && (
              <>
                <span className="text-muted-foreground">Rejection reason</span>
                <span>{req.rejection_reason}</span>
              </>
            )}
            {req.rejection_note && (
              <>
                <span className="text-muted-foreground">Rejection note</span>
                <span className="whitespace-pre-wrap">{req.rejection_note}</span>
              </>
            )}
          </div>

          {/* Approve panel */}
          {req.status === 'pending' && (
            <div className="space-y-3 border-t pt-3">
              <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                Approve
              </p>
              <div className="space-y-1.5">
                <Label htmlFor={`org-name-${req.id}`} className="text-xs">
                  Organisation name (leave blank to use submitted name)
                </Label>
                <Input
                  id={`org-name-${req.id}`}
                  placeholder={req.org_name}
                  value={approveOrgName}
                  onChange={(e) => setApproveOrgName(e.target.value)}
                  disabled={working}
                />
              </div>
              {conflictWarning && (
                <p className="text-xs text-destructive">{actionError}</p>
              )}
              <Button
                size="sm"
                onClick={() =>
                  doAction(`/api/signups/${req.id}/approve/`, {
                    approved_org_name: approveOrgName || undefined,
                  })
                }
                disabled={working}
              >
                {working ? 'Approving…' : 'Approve & provision'}
              </Button>
            </div>
          )}

          {/* Reject panel */}
          {req.status === 'pending' && (
            <div className="space-y-3 border-t pt-3">
              <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                Reject
              </p>
              <div className="space-y-1.5">
                <Label htmlFor={`reject-reason-${req.id}`} className="text-xs">
                  Reason
                </Label>
                <select
                  id={`reject-reason-${req.id}`}
                  className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                  value={rejectReason}
                  onChange={(e) => setRejectReason(e.target.value)}
                  disabled={working}
                >
                  {REJECTION_REASONS.map((r) => (
                    <option key={r} value={r}>
                      {r}
                    </option>
                  ))}
                </select>
              </div>
              <div className="space-y-1.5">
                <Label htmlFor={`reject-note-${req.id}`} className="text-xs">
                  Note (optional)
                </Label>
                <Textarea
                  id={`reject-note-${req.id}`}
                  rows={2}
                  value={rejectNote}
                  onChange={(e) => setRejectNote(e.target.value)}
                  disabled={working}
                />
              </div>
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={sendEmail}
                  onChange={(e) => setSendEmail(e.target.checked)}
                  disabled={working}
                />
                Send rejection email
              </label>
              <Button
                size="sm"
                variant="destructive"
                onClick={() =>
                  doAction(`/api/signups/${req.id}/reject/`, {
                    rejection_reason: rejectReason,
                    rejection_note: rejectNote,
                    send_rejection_email: sendEmail,
                  })
                }
                disabled={working}
              >
                {working ? 'Rejecting…' : 'Reject'}
              </Button>
            </div>
          )}

          {/* Resend panel */}
          {req.status === 'expired' && (
            <div className="space-y-2 border-t pt-3">
              <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                Resend invite
              </p>
              <Button
                size="sm"
                onClick={() => doAction(`/api/signups/${req.id}/resend/`, {})}
                disabled={working}
              >
                {working ? 'Sending…' : 'Resend invite'}
              </Button>
            </div>
          )}

          {/* Delete */}
          <div className="border-t pt-3">
            <Button size="sm" variant="outline" onClick={doDelete} disabled={working}>
              Delete request
            </Button>
          </div>

          {actionError && !conflictWarning && (
            <p className="text-sm text-destructive">{actionError}</p>
          )}
        </div>
      )}
    </div>
  );
}

function SignupRequests() {
  const [requests, setRequests] = useState([]);
  const [statusFilter, setStatusFilter] = useState('pending');
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);

  const load = useCallback(() => {
    setIsLoading(true);
    setError(null);
    api
      .get(`/api/signups/${statusFilter ? `?status=${statusFilter}` : ''}`)
      .then((res) => setRequests(res.data))
      .catch(() => setError('Failed to load signup requests.'))
      .finally(() => setIsLoading(false));
  }, [statusFilter]);

  useEffect(() => {
    load();
  }, [load]);

  function handleAction(updatedReq) {
    if (updatedReq === null) {
      load();
    } else {
      setRequests((prev) => prev.map((r) => (r.id === updatedReq.id ? updatedReq : r)));
      load();
    }
  }

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center gap-3">
        <UserCheck className="h-6 w-6 text-muted-foreground" />
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-foreground">Signup Requests</h1>
          <p className="text-sm text-muted-foreground">
            Review and manage customer signup requests.
          </p>
        </div>
      </div>

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Filter by status</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex flex-wrap gap-2">
            <button
              className={`rounded-full px-3 py-1 text-sm font-medium transition-colors ${
                statusFilter === ''
                  ? 'bg-primary text-primary-foreground'
                  : 'bg-muted text-muted-foreground hover:bg-accent hover:text-accent-foreground'
              }`}
              onClick={() => setStatusFilter('')}
            >
              All
            </button>
            {STATUSES.map((s) => (
              <button
                key={s}
                className={`rounded-full px-3 py-1 text-sm font-medium transition-colors ${
                  statusFilter === s
                    ? 'bg-primary text-primary-foreground'
                    : 'bg-muted text-muted-foreground hover:bg-accent hover:text-accent-foreground'
                }`}
                onClick={() => setStatusFilter(s)}
              >
                {STATUS_LABELS[s]}
              </button>
            ))}
          </div>
        </CardContent>
      </Card>

      {isLoading && <p className="text-sm text-muted-foreground">Loading…</p>}
      {error && <p className="text-sm text-destructive">{error}</p>}
      {!isLoading && !error && requests.length === 0 && (
        <p className="text-sm text-muted-foreground">No requests found.</p>
      )}
      {!isLoading && !error && requests.length > 0 && (
        <div className="space-y-2">
          {requests.map((req) => (
            <RequestRow key={req.id} req={req} onAction={handleAction} />
          ))}
        </div>
      )}
    </div>
  );
}

export default SignupRequests;
