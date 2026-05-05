import { useState, useEffect } from 'react';
import api from '../lib/axios';
import SlideOver from './SlideOver';

const SEVERITY_CLASSES = {
  critical: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400',
  high:     'bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-400',
  medium:   'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400',
  low:      'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400',
};

function SeverityBadge({ severity }) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${
        SEVERITY_CLASSES[severity] ?? SEVERITY_CLASSES.low
      }`}
    >
      {severity}
    </span>
  );
}

function Section({ title, children }) {
  return (
    <div>
      <h3 className="text-sm font-semibold text-foreground mb-2">{title}</h3>
      <dl className="space-y-1">{children}</dl>
    </div>
  );
}

function Field({ label, children }) {
  return (
    <div className="flex gap-2 text-sm">
      <dt className="w-32 shrink-0 text-muted-foreground">{label}</dt>
      <dd className="text-foreground">{children}</dd>
    </div>
  );
}

export default function EventSlideOver({ agentId, orgSlug, eventId, onClose }) {
  const [detail, setDetail] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const open = Boolean(eventId);

  useEffect(() => {
    if (!eventId) { setDetail(null); return; }
    let cancelled = false;
    setLoading(true);
    setError(null);
    api.get(`/api/security/agents/${agentId}/events/${eventId}/?org=${orgSlug}`)
      .then(res => { if (!cancelled) { setDetail(res.data); setLoading(false); } })
      .catch(() => { if (!cancelled) { setError('Failed to load event details.'); setLoading(false); } });
    return () => { cancelled = true; };
  }, [agentId, orgSlug, eventId]);

  return (
    <SlideOver open={open} onClose={onClose} title="Event Detail" loading={loading}>
      {error ? (
        <p className="px-6 py-4 text-sm text-red-600">{error}</p>
      ) : detail ? (
        <div className="px-6 py-4 space-y-6">
          <Section title="Summary">
            <Field label="Timestamp">{detail.timestamp ? new Date(detail.timestamp).toLocaleString() : '—'}</Field>
            <Field label="Severity"><SeverityBadge severity={detail.severity} /></Field>
            <Field label="Rule">{detail.rule_description}</Field>
          </Section>

          <Section title="Rule Details">
            <Field label="Rule ID">{detail.rule_id}</Field>
            <Field label="Level">{detail.level}</Field>
            {detail.rule_groups?.length > 0 && (
              <Field label="Groups">{detail.rule_groups.join(', ')}</Field>
            )}
          </Section>

          {detail.mitre && (
            <Section title="MITRE ATT&CK">
              {detail.mitre.tactic && <Field label="Tactic">{detail.mitre.tactic.join(', ')}</Field>}
              {detail.mitre.technique && <Field label="Technique">{detail.mitre.technique.join(', ')}</Field>}
              {detail.mitre.technique_id && <Field label="Technique ID">{detail.mitre.technique_id.join(', ')}</Field>}
            </Section>
          )}

          <Section title="Agent">
            <Field label="Name">{detail.agent_name}</Field>
            {detail.agent_ip && <Field label="IP">{detail.agent_ip}</Field>}
            {detail.log_source && <Field label="Source">{detail.log_source}</Field>}
          </Section>

          {detail.network && (
            <Section title="Network">
              {detail.network.src_ip && <Field label="Source IP">{detail.network.src_ip}</Field>}
              {detail.network.dst_ip && <Field label="Dest IP">{detail.network.dst_ip}</Field>}
              {detail.network.protocol && <Field label="Protocol">{detail.network.protocol}</Field>}
            </Section>
          )}

          <details>
            <summary className="cursor-pointer text-sm font-medium text-foreground py-2">Advanced</summary>
            <pre className="mt-2 rounded bg-muted p-3 text-xs font-mono whitespace-pre-wrap break-all">
              {detail.raw_log || 'No raw log available.'}
            </pre>
          </details>
        </div>
      ) : null}
    </SlideOver>
  );
}
