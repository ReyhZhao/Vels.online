import { useState, useEffect, useCallback } from 'react';
import { useParams, Link } from 'react-router-dom';
import api from '../lib/axios';
import { useAuth } from '../context/AuthContext';
import DelegationPanel from '../components/DelegationPanel';
import IncidentAttachments from '../components/IncidentAttachments';
import IncidentComments from '../components/IncidentComments';
import IncidentTimeline from '../components/IncidentTimeline';
import IncidentTasks from './IncidentTasks';

const TRIAGE_STATES = new Set(['new', 'triaged']);

const SEVERITY_CLASSES = {
  critical: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400',
  high:     'bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-400',
  medium:   'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400',
  low:      'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400',
  info:     'bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-400',
};

const TLP_CLASSES = {
  white: 'bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-300',
  green: 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400',
  amber: 'bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-400',
  red:   'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400',
};

const STATE_CLASSES = {
  new:         'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400',
  triaged:     'bg-purple-100 text-purple-800 dark:bg-purple-900/30 dark:text-purple-400',
  in_progress: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400',
  on_hold:     'bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-400',
  resolved:    'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400',
  closed:      'bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-400',
};

const ALLOWED_TRANSITIONS = {
  new:         [{ state: 'triaged', label: 'Triage' }, { state: 'in_progress', label: 'Start work' }],
  triaged:     [{ state: 'in_progress', label: 'Start work' }, { state: 'on_hold', label: 'Put on hold' }],
  in_progress: [{ state: 'on_hold', label: 'Put on hold' }, { state: 'resolved', label: 'Mark resolved' }, { state: 'closed', label: 'Close' }],
  on_hold:     [{ state: 'in_progress', label: 'Resume' }, { state: 'resolved', label: 'Mark resolved' }, { state: 'closed', label: 'Close' }],
  resolved:    [{ state: 'in_progress', label: 'Reopen' }, { state: 'closed', label: 'Close' }],
  closed:      [{ state: 'in_progress', label: 'Reopen' }],
};

const CLOSURE_REASONS = [
  { value: 'resolved',       label: 'Resolved' },
  { value: 'false_positive', label: 'False Positive' },
  { value: 'duplicate',      label: 'Duplicate' },
  { value: 'informational',  label: 'Informational' },
  { value: 'accepted_risk',  label: 'Accepted Risk' },
];

function Badge({ label, value, badgeClass }) {
  return (
    <div className="flex flex-col gap-1">
      <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">{label}</span>
      <span className={`inline-flex w-fit items-center rounded-full px-2 py-0.5 text-xs font-medium ${badgeClass}`}>
        {value}
      </span>
    </div>
  );
}

function Field({ label, value }) {
  return (
    <div className="flex flex-col gap-1">
      <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">{label}</span>
      <span className="text-sm text-foreground">{value || '—'}</span>
    </div>
  );
}

function ClosureReasonDialog({ onConfirm, onCancel, transitioning }) {
  const [reason, setReason] = useState('');
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="w-full max-w-sm rounded-lg border border-border bg-card p-6 shadow-lg space-y-4">
        <h2 className="text-lg font-semibold text-foreground">Close incident</h2>
        <div className="flex flex-col gap-1">
          <label className="text-sm font-medium text-foreground" htmlFor="closure-reason">
            Closure reason
          </label>
          <select
            id="closure-reason"
            value={reason}
            onChange={e => setReason(e.target.value)}
            className="rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
          >
            <option value="">Select a reason…</option>
            {CLOSURE_REASONS.map(r => (
              <option key={r.value} value={r.value}>{r.label}</option>
            ))}
          </select>
        </div>
        <div className="flex justify-end gap-3">
          <button
            onClick={onCancel}
            disabled={transitioning}
            className="rounded-md border border-border bg-background px-4 py-2 text-sm font-medium text-foreground hover:bg-accent disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            onClick={() => reason && onConfirm(reason)}
            disabled={!reason || transitioning}
            className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
          >
            {transitioning ? 'Closing…' : 'Close incident'}
          </button>
        </div>
      </div>
    </div>
  );
}

function TransferDialog({ onConfirm, onCancel, transferring, staffUsers }) {
  const [selectedId, setSelectedId] = useState('');
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="w-full max-w-sm rounded-lg border border-border bg-card p-6 shadow-lg space-y-4">
        <h2 className="text-lg font-semibold text-foreground">Transfer incident</h2>
        <div className="flex flex-col gap-1">
          <label className="text-sm font-medium text-foreground" htmlFor="transfer-assignee">
            New assignee
          </label>
          <select
            id="transfer-assignee"
            value={selectedId}
            onChange={e => setSelectedId(e.target.value)}
            className="rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
          >
            <option value="">Select a staff user…</option>
            {staffUsers.map(u => (
              <option key={u.id} value={u.id}>{u.username}</option>
            ))}
          </select>
        </div>
        <div className="flex justify-end gap-3">
          <button
            onClick={onCancel}
            disabled={transferring}
            className="rounded-md border border-border bg-background px-4 py-2 text-sm font-medium text-foreground hover:bg-accent disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            onClick={() => selectedId && onConfirm(Number(selectedId))}
            disabled={!selectedId || transferring}
            className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
          >
            {transferring ? 'Transferring…' : 'Confirm transfer'}
          </button>
        </div>
      </div>
    </div>
  );
}

function SubjectDropdown({ incident, subjects, onSubjectChange, saving }) {
  const locked = !TRIAGE_STATES.has(incident.state);
  const value = incident.subject ?? '';

  return (
    <div className="flex flex-col gap-1">
      <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Subject</span>
      <div title={locked ? 'Subject is locked once the incident leaves triage.' : undefined}>
        <select
          value={value}
          onChange={e => !locked && onSubjectChange(e.target.value ? Number(e.target.value) : null)}
          disabled={locked || saving}
          aria-label="Subject"
          className="w-full rounded-md border border-border bg-background px-2 py-1.5 text-sm text-foreground disabled:cursor-not-allowed disabled:opacity-50 focus:outline-none focus:ring-2 focus:ring-ring"
        >
          <option value="">— None —</option>
          {subjects.filter(s => !s.archived || s.id === incident.subject).map(s => (
            <option key={s.id} value={s.id}>{s.name}</option>
          ))}
        </select>
      </div>
    </div>
  );
}

export default function IncidentDetail() {
  const { incidentId } = useParams();
  const { user } = useAuth();
  const [incident, setIncident] = useState(null);
  const [subjects, setSubjects] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [transitioning, setTransitioning] = useState(false);
  const [transitionError, setTransitionError] = useState(null);
  const [pendingClose, setPendingClose] = useState(false);
  const [savingSubject, setSavingSubject] = useState(false);
  const [subjectError, setSubjectError] = useState(null);
  const [tasksRefreshKey, setTasksRefreshKey] = useState(0);
  const [showTransferDialog, setShowTransferDialog] = useState(false);
  const [staffUsers, setStaffUsers] = useState([]);
  const [transferring, setTransferring] = useState(false);
  const [transferError, setTransferError] = useState(null);

  useEffect(() => {
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const [incRes, subRes] = await Promise.all([
          api.get(`/api/incidents/${incidentId}/`),
          api.get('/api/subjects/'),
        ]);
        setIncident(incRes.data);
        setSubjects(subRes.data);
      } catch (err) {
        setError(err.response?.status === 404 ? 'Incident not found.' : 'Failed to load incident.');
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [incidentId]);

  async function handleOpenTransfer() {
    if (staffUsers.length === 0) {
      try {
        const res = await api.get('/api/incidents/staff-users/');
        setStaffUsers(res.data);
      } catch {
        setTransferError('Failed to load staff users.');
        return;
      }
    }
    setTransferError(null);
    setShowTransferDialog(true);
  }

  async function handleTransfer(assigneeId) {
    setTransferring(true);
    setTransferError(null);
    try {
      const res = await api.post(`/api/incidents/${incidentId}/transfer/`, { assignee_id: assigneeId });
      setIncident(res.data);
      setShowTransferDialog(false);
    } catch (err) {
      setTransferError(err.response?.data?.detail || 'Transfer failed.');
    } finally {
      setTransferring(false);
    }
  }

  const handleSubjectChange = useCallback(async (subjectId) => {
    setSavingSubject(true);
    setSubjectError(null);
    try {
      const res = await api.patch(`/api/incidents/${incidentId}/`, { subject: subjectId });
      setIncident(res.data);
      setTasksRefreshKey(k => k + 1);
    } catch (err) {
      setSubjectError(err.response?.data?.detail || 'Failed to update subject.');
    } finally {
      setSavingSubject(false);
    }
  }, [incidentId]);

  async function handleTransition(targetState, closureReason = undefined) {
    setTransitioning(true);
    setTransitionError(null);
    try {
      const payload = { state: targetState };
      if (closureReason) payload.closure_reason = closureReason;
      const res = await api.post(`/api/incidents/${incidentId}/transition/`, payload);
      setIncident(res.data);
    } catch (err) {
      setTransitionError(err.response?.data?.detail || 'Transition failed.');
    } finally {
      setTransitioning(false);
      setPendingClose(false);
    }
  }

  function handleActionClick(targetState) {
    if (targetState === 'closed') {
      setPendingClose(true);
    } else {
      handleTransition(targetState);
    }
  }

  if (loading) return <p className="text-sm text-muted-foreground p-6">Loading…</p>;
  if (error) return <p className="text-sm text-red-600 p-6">{error}</p>;
  if (!incident) return null;

  const nextStates = ALLOWED_TRANSITIONS[incident.state] ?? [];

  return (
    <div className="space-y-6 p-6">
      {pendingClose && (
        <ClosureReasonDialog
          transitioning={transitioning}
          onConfirm={reason => handleTransition('closed', reason)}
          onCancel={() => setPendingClose(false)}
        />
      )}

      {showTransferDialog && (
        <TransferDialog
          staffUsers={staffUsers}
          transferring={transferring}
          onConfirm={handleTransfer}
          onCancel={() => setShowTransferDialog(false)}
        />
      )}

      <div className="flex items-center gap-3">
        <Link to="/incidents" className="text-sm text-muted-foreground hover:text-foreground transition-colors">
          ← Incidents
        </Link>
      </div>

      <div className="rounded-lg border border-border bg-card p-6 space-y-6">
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="font-mono text-xs text-muted-foreground">{incident.display_id}</p>
            <h1 className="mt-1 text-2xl font-semibold text-foreground">{incident.title}</h1>
          </div>

          <div className="flex shrink-0 flex-wrap gap-2">
            {nextStates.map(({ state, label }) => (
              <button
                key={state}
                onClick={() => handleActionClick(state)}
                disabled={transitioning}
                className="rounded-md border border-border bg-background px-3 py-1.5 text-sm font-medium text-foreground hover:bg-accent disabled:opacity-50 transition-colors"
              >
                {label}
              </button>
            ))}
            {user?.is_staff && (
              <button
                onClick={handleOpenTransfer}
                disabled={transitioning || transferring}
                className="rounded-md border border-border bg-background px-3 py-1.5 text-sm font-medium text-foreground hover:bg-accent disabled:opacity-50 transition-colors"
              >
                Transfer
              </button>
            )}
          </div>
        </div>

        {transitionError && <p className="text-sm text-red-600">{transitionError}</p>}
        {transferError && <p className="text-sm text-red-600">{transferError}</p>}

        <div className="grid grid-cols-2 gap-6 sm:grid-cols-3 lg:grid-cols-4">
          <Badge
            label="State"
            value={incident.state.replace('_', ' ')}
            badgeClass={STATE_CLASSES[incident.state] ?? ''}
          />
          <Badge
            label="Severity"
            value={incident.severity}
            badgeClass={SEVERITY_CLASSES[incident.severity] ?? ''}
          />
          <Badge
            label="TLP"
            value={`TLP:${incident.tlp.toUpperCase()}`}
            badgeClass={TLP_CLASSES[incident.tlp] ?? ''}
          />
          <Badge
            label="PAP"
            value={`PAP:${incident.pap.toUpperCase()}`}
            badgeClass={TLP_CLASSES[incident.pap] ?? ''}
          />
          <Field label="Organisation" value={incident.org_slug} />
          <Field label="Source" value={incident.source_kind} />
          <Field label="Assignee" value={incident.assignee_username} />
          <Field label="Created By" value={incident.created_by_username} />
          {incident.closure_reason && (
            <Field label="Closure Reason" value={incident.closure_reason.replace('_', ' ')} />
          )}
          <SubjectDropdown
            incident={incident}
            subjects={subjects}
            onSubjectChange={handleSubjectChange}
            saving={savingSubject}
          />
        </div>

        {subjectError && <p className="text-sm text-red-600">{subjectError}</p>}

        {incident.description && (
          <div className="flex flex-col gap-1">
            <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Description</span>
            <p className="text-sm text-foreground whitespace-pre-wrap">{incident.description}</p>
          </div>
        )}

        <div className="grid grid-cols-2 gap-4 text-xs text-muted-foreground">
          <span>Created: {incident.created_at ? new Date(incident.created_at).toLocaleString() : '—'}</span>
          <span>Updated: {incident.updated_at ? new Date(incident.updated_at).toLocaleString() : '—'}</span>
        </div>
      </div>

      <div className="rounded-lg border border-border bg-card p-6">
        <IncidentTasks incidentId={incidentId} subjectId={incident.subject} refreshKey={tasksRefreshKey} />
      </div>

      <div className="rounded-lg border border-border bg-card p-6">
        <DelegationPanel
          incidentId={incidentId}
          activeDelegations={incident.active_delegations ?? []}
          isStaff={user?.is_staff ?? false}
          onIncidentUpdate={setIncident}
        />
      </div>

      <div className="rounded-lg border border-border bg-card p-6">
        <IncidentTimeline incidentId={incidentId} />
      </div>

      <div className="rounded-lg border border-border bg-card p-6">
        <IncidentAttachments incidentId={incidentId} />
      </div>

      <div className="rounded-lg border border-border bg-card p-6 space-y-3">
        <h2 className="text-base font-semibold text-foreground">Comments</h2>
        <IncidentComments
          incidentId={incidentId}
          currentUserId={user?.id}
          isStaff={user?.is_staff ?? false}
        />
      </div>
    </div>
  );
}
