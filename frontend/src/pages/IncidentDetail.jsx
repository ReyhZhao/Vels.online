import { useState, useEffect, useCallback, useRef } from 'react';
import { useParams, Link } from 'react-router-dom';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import api from '../lib/axios';
import { useAuth } from '../context/AuthContext';
import DelegationPanel from '../components/DelegationPanel';
import IncidentAttachments from '../components/IncidentAttachments';
import IncidentComments from '../components/IncidentComments';
import IncidentTimeline from '../components/IncidentTimeline';
import IncidentTasks from './IncidentTasks';
import SLAPill from '../components/SLAPill';
import CreateExceptionSlideOver from '../components/CreateExceptionSlideOver';

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
  new:          'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400',
  triaged:      'bg-purple-100 text-purple-800 dark:bg-purple-900/30 dark:text-purple-400',
  in_progress:  'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400',
  on_hold:      'bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-400',
  needs_tuning: 'bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-400',
  resolved:     'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400',
  closed:       'bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-400',
};

// States from which the resolve dropdown (Resolved / Needs tuning) is shown.
const RESOLVE_DROPDOWN_STATES = new Set(['in_progress', 'on_hold']);

const ALLOWED_TRANSITIONS = {
  new:          [{ state: 'triaged', label: 'Triage' }, { state: 'in_progress', label: 'Start work' }],
  triaged:      [{ state: 'in_progress', label: 'Start work' }, { state: 'on_hold', label: 'Put on hold' }],
  in_progress:  [{ state: 'on_hold', label: 'Put on hold' }, { state: 'closed', label: 'Close' }],
  on_hold:      [{ state: 'in_progress', label: 'Resume' }, { state: 'closed', label: 'Close' }],
  needs_tuning: [{ state: 'in_progress', label: 'Reopen' }, { state: 'closed', label: 'Close' }],
  resolved:     [{ state: 'in_progress', label: 'Reopen' }, { state: 'closed', label: 'Close' }],
  closed:       [{ state: 'in_progress', label: 'Reopen' }],
};

const TRANSITION_BTN_CLASSES = {
  triaged:      'bg-blue-600 text-white hover:bg-blue-700 dark:bg-blue-700 dark:hover:bg-blue-600',
  in_progress:  'bg-blue-600 text-white hover:bg-blue-700 dark:bg-blue-700 dark:hover:bg-blue-600',
  on_hold:      'bg-amber-500 text-white hover:bg-amber-600 dark:bg-amber-600 dark:hover:bg-amber-500',
  needs_tuning: 'bg-amber-600 text-white hover:bg-amber-700 dark:bg-amber-700 dark:hover:bg-amber-600',
  resolved:     'bg-green-600 text-white hover:bg-green-700 dark:bg-green-700 dark:hover:bg-green-600',
  closed:       'bg-red-600 text-white hover:bg-red-700 dark:bg-red-700 dark:hover:bg-red-600',
};

const CLOSURE_REASONS = [
  { value: 'resolved',       label: 'Resolved' },
  { value: 'false_positive', label: 'False Positive' },
  { value: 'duplicate',      label: 'Duplicate' },
  { value: 'informational',  label: 'Informational' },
  { value: 'accepted_risk',  label: 'Accepted Risk' },
];

const SECONDARY_TABS = [
  { key: 'timeline',    label: 'Timeline' },
  { key: 'attachments', label: 'Attachments' },
  { key: 'tasks',       label: 'Tasks' },
  { key: 'delegations', label: 'Delegations' },
];

const EXCEPTION_STATUS_CLASSES = {
  pending:  'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400',
  applied:  'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400',
  disabled: 'bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-400',
};

function IncidentExceptionsSection({ displayId }) {
  const [exceptions, setExceptions] = useState([]);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    api.get('/api/exceptions/', { params: { incident: displayId } })
      .then(res => { setExceptions(Array.isArray(res.data) ? res.data : []); setLoaded(true); })
      .catch(() => setLoaded(true));
  }, [displayId]);

  if (!loaded || exceptions.length === 0) return null;

  return (
    <div className="rounded-lg border border-border bg-card p-6 space-y-3">
      <h2 className="text-base font-semibold text-foreground">Exceptions</h2>
      <ul className="divide-y divide-border">
        {exceptions.map(ex => (
          <li key={ex.id} className="flex items-center justify-between gap-3 py-2">
            <span className="text-sm text-foreground truncate flex-1">{ex.description || '—'}</span>
            <span className="text-xs text-muted-foreground shrink-0">{ex.scope}</span>
            <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium shrink-0 ${EXCEPTION_STATUS_CLASSES[ex.status] ?? ''}`}>
              {ex.status}
            </span>
            <Link to="/exceptions" className="text-xs text-primary hover:underline shrink-0">
              View
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}

function ResolveDropdown({ onResolve, onNeedsTuning, disabled }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    function handleOutside(e) {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false);
    }
    document.addEventListener('mousedown', handleOutside);
    return () => document.removeEventListener('mousedown', handleOutside);
  }, []);

  return (
    <div className="relative" ref={ref}>
      <div className="flex rounded-md overflow-hidden">
        <button
          onClick={() => { setOpen(false); onResolve(); }}
          disabled={disabled}
          className="bg-green-600 text-white hover:bg-green-700 dark:bg-green-700 dark:hover:bg-green-600 px-3 py-1.5 text-sm font-medium disabled:opacity-50 transition-colors"
        >
          Mark resolved
        </button>
        <button
          onClick={() => setOpen(o => !o)}
          disabled={disabled}
          aria-label="More resolution options"
          className="bg-green-600 text-white hover:bg-green-700 dark:bg-green-700 dark:hover:bg-green-600 px-2 py-1.5 text-sm font-medium disabled:opacity-50 transition-colors border-l border-green-500 dark:border-green-600"
        >
          ▾
        </button>
      </div>
      {open && (
        <div className="absolute right-0 top-full mt-1 z-10 w-44 rounded-md border border-border bg-card shadow-lg">
          <button
            onClick={() => { setOpen(false); onResolve(); }}
            disabled={disabled}
            className="w-full text-left px-3 py-2 text-sm text-foreground hover:bg-accent disabled:opacity-50 rounded-t-md"
          >
            Resolved
          </button>
          <button
            onClick={() => { setOpen(false); onNeedsTuning(); }}
            disabled={disabled}
            className="w-full text-left px-3 py-2 text-sm text-foreground hover:bg-accent disabled:opacity-50 rounded-b-md"
          >
            Needs tuning
          </button>
        </div>
      )}
    </div>
  );
}

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

function InlineSelect({ label, value, options, colorClasses, onChange, saving }) {
  return (
    <div className="flex flex-col gap-1">
      <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">{label}</span>
      <select
        value={value}
        onChange={e => onChange(e.target.value)}
        disabled={saving}
        aria-label={label}
        className={`w-fit cursor-pointer rounded-full border-0 px-2 py-0.5 text-xs font-medium focus:outline-none focus:ring-2 focus:ring-ring disabled:cursor-not-allowed disabled:opacity-50 ${colorClasses[value] ?? ''}`}
      >
        {options.map(opt => (
          <option key={opt} value={opt}>{opt}</option>
        ))}
      </select>
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

function TransferDialog({ onConfirm, onCancel, transferring, staffUsers, isInitialAssignment }) {
  const [selectedId, setSelectedId] = useState('');
  const title = isInitialAssignment ? 'Assign incident' : 'Transfer incident';
  const confirmLabel = transferring
    ? (isInitialAssignment ? 'Assigning…' : 'Transferring…')
    : (isInitialAssignment ? 'Confirm assignment' : 'Confirm transfer');
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="w-full max-w-sm rounded-lg border border-border bg-card p-6 shadow-lg space-y-4">
        <h2 className="text-lg font-semibold text-foreground">{title}</h2>
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
            {confirmLabel}
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
  const { displayId } = useParams();
  const { user } = useAuth();
  const [incident, setIncident]           = useState(null);
  const [subjects, setSubjects]           = useState([]);
  const [loading, setLoading]             = useState(true);
  const [error, setError]                 = useState(null);
  const [transitioning, setTransitioning] = useState(false);
  const [transitionError, setTransitionError] = useState(null);
  const [pendingClose, setPendingClose]   = useState(false);
  const [savingSubject, setSavingSubject] = useState(false);
  const [subjectError, setSubjectError]   = useState(null);
  const [tasksRefreshKey, setTasksRefreshKey] = useState(0);
  const [showTransferDialog, setShowTransferDialog] = useState(false);
  const [staffUsers, setStaffUsers]       = useState([]);
  const [transferring, setTransferring]   = useState(false);
  const [transferError, setTransferError] = useState(null);
  const [savingBadge, setSavingBadge]     = useState(false);
  const [badgeError, setBadgeError]       = useState(null);
  const [activeTab, setActiveTab]         = useState('timeline');
  const [showExceptionSlideOver, setShowExceptionSlideOver] = useState(false);
  const pollRef = useRef(null);

  useEffect(() => {
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const [incRes, subRes] = await Promise.all([
          api.get(`/api/incidents/${displayId}/`),
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

    if (pollRef.current) clearInterval(pollRef.current);
    pollRef.current = setInterval(() => {
      if (document.visibilityState !== 'hidden') {
        api.get(`/api/incidents/${displayId}/`)
          .then(res => setIncident(prev => prev ? res.data : prev))
          .catch(() => {});
      }
    }, 30000);
    return () => clearInterval(pollRef.current);
  }, [displayId]);

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
      const res = await api.post(`/api/incidents/${displayId}/transfer/`, { assignee_id: assigneeId });
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
      const res = await api.patch(`/api/incidents/${displayId}/`, { subject: subjectId });
      setIncident(res.data);
      setTasksRefreshKey(k => k + 1);
    } catch (err) {
      setSubjectError(err.response?.data?.detail || 'Failed to update subject.');
    } finally {
      setSavingSubject(false);
    }
  }, [displayId]);

  const handleBadgeChange = useCallback(async (field, value) => {
    setSavingBadge(true);
    setBadgeError(null);
    try {
      const res = await api.patch(`/api/incidents/${displayId}/`, { [field]: value });
      setIncident(res.data);
    } catch (err) {
      setBadgeError(err.response?.data?.detail || `Failed to update ${field}.`);
    } finally {
      setSavingBadge(false);
    }
  }, [displayId]);

  async function handleTransition(targetState, closureReason = undefined) {
    setTransitioning(true);
    setTransitionError(null);
    try {
      const payload = { state: targetState };
      if (closureReason) payload.closure_reason = closureReason;
      const res = await api.post(`/api/incidents/${displayId}/transition/`, payload);
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
  if (error)   return <p className="text-sm text-red-600 p-6">{error}</p>;
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
          isInitialAssignment={!incident.assignee_username}
        />
      )}

      <CreateExceptionSlideOver
        open={showExceptionSlideOver}
        onClose={() => setShowExceptionSlideOver(false)}
        incident={incident}
      />

      <div className="flex items-center gap-3">
        <Link to="/incidents" className="text-sm text-muted-foreground hover:text-foreground transition-colors">
          ← Incidents
        </Link>
      </div>

      {/* ── Header card ── */}
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
                className={`rounded-md px-3 py-1.5 text-sm font-medium disabled:opacity-50 transition-colors ${TRANSITION_BTN_CLASSES[state] ?? 'border border-border bg-background text-foreground hover:bg-accent'}`}
              >
                {label}
              </button>
            ))}
            {RESOLVE_DROPDOWN_STATES.has(incident.state) && (
              <ResolveDropdown
                onResolve={() => handleActionClick('resolved')}
                onNeedsTuning={() => handleActionClick('needs_tuning')}
                disabled={transitioning}
              />
            )}
            {user?.is_staff && (
              <button
                onClick={handleOpenTransfer}
                disabled={transitioning || transferring}
                className="rounded-md border border-slate-400 bg-slate-100 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-200 disabled:opacity-50 transition-colors dark:border-slate-600 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700"
              >
                {incident.assignee_username ? 'Transfer' : 'Assign'}
              </button>
            )}
            {user?.is_staff && incident.source_kind === 'wazuh_event' && (
              <button
                onClick={() => setShowExceptionSlideOver(true)}
                className="rounded-md border border-amber-400 bg-amber-50 px-3 py-1.5 text-sm font-medium text-amber-700 hover:bg-amber-100 transition-colors dark:border-amber-600 dark:bg-amber-900/20 dark:text-amber-400 dark:hover:bg-amber-900/40"
              >
                Create Exception
              </button>
            )}
          </div>
        </div>

        {transitionError && <p className="text-sm text-red-600">{transitionError}</p>}
        {transferError   && <p className="text-sm text-red-600">{transferError}</p>}
        {badgeError      && <p className="text-sm text-red-600">{badgeError}</p>}

        {/* Metadata grid */}
        <div className="grid grid-cols-2 gap-6 sm:grid-cols-3 lg:grid-cols-4">
          <Badge
            label="State"
            value={incident.state.replace('_', ' ')}
            badgeClass={STATE_CLASSES[incident.state] ?? ''}
          />
          <InlineSelect
            label="Severity"
            value={incident.severity}
            options={['critical', 'high', 'medium', 'low', 'info']}
            colorClasses={SEVERITY_CLASSES}
            onChange={v => handleBadgeChange('severity', v)}
            saving={savingBadge}
          />
          <InlineSelect
            label="TLP"
            value={incident.tlp}
            options={['white', 'green', 'amber', 'red']}
            colorClasses={TLP_CLASSES}
            onChange={v => handleBadgeChange('tlp', v)}
            saving={savingBadge}
          />
          <InlineSelect
            label="PAP"
            value={incident.pap}
            options={['white', 'green', 'amber', 'red']}
            colorClasses={TLP_CLASSES}
            onChange={v => handleBadgeChange('pap', v)}
            saving={savingBadge}
          />
          <Field label="Organisation" value={incident.org_slug} />
          <Field label="Source"       value={incident.source_kind} />
          <Field label="Assignee"     value={incident.assignee_username} />
          <Field label="Created By"   value={incident.created_by_username} />
          {incident.closure_reason && (
            <Field label="Closure Reason" value={incident.closure_reason.replace('_', ' ')} />
          )}
          {incident.response_sla?.applies && (
            <div className="flex flex-col gap-1">
              <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Response SLA</span>
              <SLAPill sla={incident.response_sla} label="Response SLA" />
            </div>
          )}
          {incident.resolve_sla?.applies && (
            <div className="flex flex-col gap-1">
              <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Resolve SLA</span>
              <SLAPill sla={incident.resolve_sla} label="Resolve SLA" />
            </div>
          )}
          <SubjectDropdown
            incident={incident}
            subjects={subjects}
            onSubjectChange={handleSubjectChange}
            saving={savingSubject}
          />
        </div>

        {subjectError && <p className="text-sm text-red-600">{subjectError}</p>}

        {/* Description + Comments split */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div className="space-y-4">
            <div>
              <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Description</span>
              {incident.description ? (
                <div className="mt-1 prose prose-sm dark:prose-invert max-w-none">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{incident.description}</ReactMarkdown>
                </div>
              ) : (
                <p className="mt-1 text-sm text-muted-foreground italic">No description provided.</p>
              )}
            </div>
            <div className="grid grid-cols-2 gap-4 text-xs text-muted-foreground">
              <span>Created: {incident.created_at ? new Date(incident.created_at).toLocaleString() : '—'}</span>
              <span>Updated: {incident.updated_at ? new Date(incident.updated_at).toLocaleString() : '—'}</span>
            </div>
          </div>
          <div>
            <IncidentComments
              incidentId={displayId}
              currentUserId={user?.id}
              isStaff={user?.is_staff ?? false}
            />
          </div>
        </div>
      </div>

      {/* ── Exceptions sidebar ── */}
      <IncidentExceptionsSection displayId={displayId} />

      {/* ── Tabbed secondary content ── */}
      <div className="rounded-lg border border-border bg-card overflow-hidden">
        <div className="flex border-b border-border">
          {SECONDARY_TABS.map(tab => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={`px-4 py-3 text-sm font-medium border-b-2 -mb-px transition-colors ${
                activeTab === tab.key
                  ? 'border-primary text-primary'
                  : 'border-transparent text-muted-foreground hover:text-foreground'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>
        <div className="p-6">
          {activeTab === 'timeline' && (
            <IncidentTimeline incidentId={displayId} />
          )}
          {activeTab === 'attachments' && (
            <IncidentAttachments incidentId={displayId} />
          )}
          {activeTab === 'tasks' && (
            <IncidentTasks
              incidentId={displayId}
              subjectId={incident.subject}
              refreshKey={tasksRefreshKey}
            />
          )}
          {activeTab === 'delegations' && (
            <DelegationPanel
              incidentId={displayId}
              activeDelegations={incident.active_delegations ?? []}
              isStaff={user?.is_staff ?? false}
              onIncidentUpdate={setIncident}
            />
          )}
        </div>
      </div>
    </div>
  );
}
