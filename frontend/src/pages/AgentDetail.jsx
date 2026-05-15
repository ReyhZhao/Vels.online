import { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate, useSearchParams } from 'react-router-dom';
import api from '../lib/axios';
import { useOrganization } from '../context/OrgContext';
import SlideOver from '../components/SlideOver';
import EventSlideOver from '../components/EventSlideOver';
import CveAdvisoryBlock from '../components/CveAdvisoryBlock';
import PromoteToIncidentButton from '../components/PromoteToIncidentButton';
import LinkedIncidents from '../components/LinkedIncidents';

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

function AcceptedBadge() {
  return (
    <span className="inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400">
      Accepted
    </span>
  );
}

const LIMIT = 50;

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

const TIME_RANGES = [
  { label: 'Last 1h',  value: '1' },
  { label: 'Last 6h',  value: '6' },
  { label: 'Last 24h', value: '24' },
  { label: 'Last 7d',  value: '168' },
  { label: 'Last 30d', value: '720' },
];

const ALL_SEVERITIES = ['critical', 'high', 'medium', 'low'];

function FilterBar({
  filters,
  onChange,
  onClear,
  showTimeRange = true,
  showFixAvailable = false,
  showHideAccepted = false,
  hideAccepted = false,
  onToggleHideAccepted,
  searchPlaceholder = "Search rules…",
}) {
  const hasActive = filters.severities.length > 0
    || (showTimeRange && (filters.hours || '24') !== '24')
    || (showFixAvailable && !!filters.fixAvailable)
    || filters.search !== '';

  function toggleSeverity(sev) {
    const next = filters.severities.includes(sev)
      ? filters.severities.filter(s => s !== sev)
      : [...filters.severities, sev];
    onChange({ ...filters, severities: next });
  }

  return (
    <div className="flex flex-wrap items-center gap-2 pb-3">
      {ALL_SEVERITIES.map(sev => (
        <button
          key={sev}
          onClick={() => toggleSeverity(sev)}
          className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium border transition-colors ${
            filters.severities.includes(sev)
              ? `${SEVERITY_CLASSES[sev]} border-current`
              : 'border-border text-muted-foreground hover:text-foreground'
          }`}
        >
          {sev}
        </button>
      ))}
      {showTimeRange && (
        <select
          value={filters.hours}
          onChange={e => onChange({ ...filters, hours: e.target.value })}
          className="rounded-md border border-border bg-background px-2 py-1 text-xs text-foreground"
          aria-label="Time range"
        >
          {TIME_RANGES.map(({ label, value }) => (
            <option key={value} value={value}>{label}</option>
          ))}
        </select>
      )}
      {showFixAvailable && (
        <button
          onClick={() => onChange({ ...filters, fixAvailable: !filters.fixAvailable })}
          aria-pressed={!!filters.fixAvailable}
          className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium border transition-colors ${
            filters.fixAvailable
              ? 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400 border-current'
              : 'border-border text-muted-foreground hover:text-foreground'
          }`}
        >
          Fix available
        </button>
      )}
      {showHideAccepted && (
        <button
          onClick={onToggleHideAccepted}
          aria-pressed={hideAccepted}
          className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium border transition-colors ${
            hideAccepted
              ? 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400 border-current'
              : 'border-border text-muted-foreground hover:text-foreground'
          }`}
        >
          Hide accepted
        </button>
      )}
      <input
        type="text"
        placeholder={searchPlaceholder}
        value={filters.search}
        onChange={e => onChange({ ...filters, search: e.target.value })}
        className="rounded-md border border-border bg-background px-2 py-1 text-xs text-foreground w-40"
        aria-label={searchPlaceholder}
      />
      {hasActive && (
        <button
          onClick={onClear}
          className="text-xs text-muted-foreground hover:text-foreground transition-colors"
        >
          Clear filters
        </button>
      )}
    </div>
  );
}

function EventsTab({ agentId, orgSlug }) {
  const [selectedEventId, setSelectedEventId] = useState(null);
  const [searchParams, setSearchParams] = useSearchParams();

  const severitiesStr = searchParams.get('severity') || '';
  const hours = searchParams.get('hours') || '24';
  const search = searchParams.get('search') || '';
  const severities = severitiesStr ? severitiesStr.split(',').filter(Boolean) : [];

  const [events, setEvents] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    const params = new URLSearchParams({ org: orgSlug, offset: '0', limit: '100', hours });
    if (severities.length > 0) params.set('severity', severities.join(','));
    if (search) params.set('search', search);
    api.get(`/api/security/agents/${agentId}/events/?${params}`)
      .then(res => {
        if (!cancelled) {
          setEvents(res.data.events);
          setTotal(res.data.total);
        }
      })
      .catch(() => { if (!cancelled) setError('Failed to load events.'); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [agentId, orgSlug, hours, severitiesStr, search]); // eslint-disable-line react-hooks/exhaustive-deps

  async function handleShowMore() {
    if (loadingMore) return;
    setLoadingMore(true);
    const params = new URLSearchParams({ org: orgSlug, offset: String(events.length), limit: '100', hours });
    if (severities.length > 0) params.set('severity', severities.join(','));
    if (search) params.set('search', search);
    try {
      const res = await api.get(`/api/security/agents/${agentId}/events/?${params}`);
      setEvents(prev => [...prev, ...res.data.events]);
      setTotal(res.data.total);
    } finally {
      setLoadingMore(false);
    }
  }

  function handleFilterChange(newFilters) {
    setSearchParams(prev => {
      const next = new URLSearchParams(prev);
      if (newFilters.severities.length > 0) {
        next.set('severity', newFilters.severities.join(','));
      } else {
        next.delete('severity');
      }
      if (newFilters.hours !== '24') {
        next.set('hours', newFilters.hours);
      } else {
        next.delete('hours');
      }
      if (newFilters.search) {
        next.set('search', newFilters.search);
      } else {
        next.delete('search');
      }
      return next;
    });
  }

  function handleClearFilters() {
    setSearchParams(prev => {
      const next = new URLSearchParams(prev);
      next.delete('severity');
      next.delete('hours');
      next.delete('search');
      return next;
    });
  }

  const filters = { severities, hours, search };

  return (
    <div className="space-y-2">
      <FilterBar filters={filters} onChange={handleFilterChange} onClear={handleClearFilters} />
      {loading ? (
        <p className="py-4 text-sm text-muted-foreground">Loading…</p>
      ) : error ? (
        <p className="text-sm text-red-600">{error}</p>
      ) : (
        <>
          {total > 0 && (
            <p className="text-xs text-muted-foreground text-right">
              Showing {events.length} of {total}
            </p>
          )}
          <div className="overflow-hidden rounded-lg border border-border bg-card">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border">
                  <th className="px-4 py-3 text-left font-medium text-muted-foreground">Timestamp</th>
                  <th className="px-4 py-3 text-left font-medium text-muted-foreground">Severity</th>
                  <th className="px-4 py-3 text-left font-medium text-muted-foreground">Rule</th>
                </tr>
              </thead>
              <tbody>
                {events.length === 0 ? (
                  <tr>
                    <td colSpan={3} className="px-4 py-8 text-center text-muted-foreground">
                      No events found.
                    </td>
                  </tr>
                ) : (
                  events.map((event, idx) => (
                    <tr
                      key={`${event.timestamp}-${idx}`}
                      onClick={() => setSelectedEventId(event.id)}
                      className="border-b border-border last:border-0 cursor-pointer hover:bg-accent/40 transition-colors"
                    >
                      <td className="px-4 py-3 text-muted-foreground whitespace-nowrap">
                        {event.timestamp ? new Date(event.timestamp).toLocaleString() : '—'}
                      </td>
                      <td className="px-4 py-3">
                        <SeverityBadge severity={event.severity} />
                      </td>
                      <td className="px-4 py-3 text-foreground">{event.rule_description}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
          {total > events.length && (
            <div className="flex justify-center pt-2">
              <button
                onClick={handleShowMore}
                disabled={loadingMore}
                className="rounded-md border border-border bg-background px-4 py-2 text-sm font-medium text-foreground hover:bg-accent disabled:opacity-50"
              >
                {loadingMore ? 'Loading…' : `Show more (${total - events.length} remaining)`}
              </button>
            </div>
          )}
        </>
      )}
      <EventSlideOver
        agentId={agentId}
        orgSlug={orgSlug}
        eventId={selectedEventId}
        onClose={() => setSelectedEventId(null)}
      />
    </div>
  );
}

function VulnerabilitySlideOver({ agentId, orgSlug, vulnId, onClose }) {
  const [detail, setDetail] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const open = Boolean(vulnId);

  useEffect(() => {
    if (!vulnId) { setDetail(null); return; }
    let cancelled = false;
    setLoading(true);
    setError(null);
    api.get(`/api/security/agents/${agentId}/vulnerabilities/${vulnId}/?org=${orgSlug}`)
      .then(res => { if (!cancelled) { setDetail(res.data); setLoading(false); } })
      .catch(() => { if (!cancelled) { setError('Failed to load vulnerability details.'); setLoading(false); } });
    return () => { cancelled = true; };
  }, [agentId, orgSlug, vulnId]);

  return (
    <SlideOver open={open} onClose={onClose} title="Vulnerability Detail" loading={loading}>
      {error ? (
        <p className="px-6 py-4 text-sm text-red-600">{error}</p>
      ) : detail ? (
        <div className="px-6 py-4 space-y-6">
          <Section title="Summary">
            <Field label="CVE"><span className="font-mono text-xs">{detail.cve}</span></Field>
            <Field label="Severity"><SeverityBadge severity={detail.severity} /></Field>
            {detail.cvss_score != null && <Field label="CVSS Score">{detail.cvss_score}</Field>}
          </Section>

          <Section title="Package">
            <Field label="Name">{detail.package}</Field>
            <Field label="Installed">{detail.installed_version}</Field>
            {detail.fixed_version && <Field label="Fixed in">{detail.fixed_version}</Field>}
          </Section>

          <Section title="Details">
            {detail.description && <Field label="Description">{detail.description}</Field>}
            {detail.published && <Field label="Published">{new Date(detail.published).toLocaleDateString()}</Field>}
          </Section>

          {detail.references?.length > 0 && (
            <Section title="References">
              <ul className="space-y-1">
                {detail.references.map((ref, i) => (
                  <li key={i}>
                    <a
                      href={ref}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-xs text-blue-600 dark:text-blue-400 hover:underline break-all"
                    >
                      {ref}
                    </a>
                  </li>
                ))}
              </ul>
            </Section>
          )}

          <LinkedIncidents
            sourceKind="agent_finding"
            sourceRef={{ agent_id: agentId, cve_id: detail.cve }}
          />

          <div className="pt-2">
            <PromoteToIncidentButton
              sourceKind="agent_finding"
              sourceRef={{
                agent_id: agentId,
                agent_name: detail.agent_name,
                cve_id: detail.cve,
                cvss_score: detail.cvss_score,
              }}
              orgSlug={orgSlug}
            />
          </div>
        </div>
      ) : null}
    </SlideOver>
  );
}

function VulnerabilitiesTab({ agentId, orgSlug }) {
  const [selectedVulnId, setSelectedVulnId] = useState(null);
  const [searchParams, setSearchParams] = useSearchParams();

  const severitiesStr = searchParams.get('severity') || '';
  const fixAvailableParam = searchParams.get('fix_available') || '';
  const search = searchParams.get('search') || '';
  const severities = severitiesStr ? severitiesStr.split(',').filter(Boolean) : [];
  const fixAvailable = fixAvailableParam === 'true';

  const [vulns, setVulns] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(0);
  const [loading, setLoading] = useState(false);
  const [expandedCve, setExpandedCve] = useState(null);
  const [error, setError] = useState(null);
  const [acceptedCveIds, setAcceptedCveIds] = useState(new Set());
  const [hideAccepted, setHideAccepted] = useState(true);

  // Reset to page 0 when filters change
  useEffect(() => { setPage(0); }, [severitiesStr, fixAvailableParam, search]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    let cancelled = false;
    api.get(`/api/security/risk-acceptances/?org=${orgSlug}`)
      .then(res => { if (!cancelled) setAcceptedCveIds(new Set(res.data.map(a => a.cve_id))); })
      .catch(() => {});
    return () => { cancelled = true; };
  }, [orgSlug]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    const params = new URLSearchParams({ org: orgSlug, offset: String(page * LIMIT), limit: String(LIMIT) });
    if (severities.length > 0) params.set('severity', severities.join(','));
    if (fixAvailable) params.set('fix_available', 'true');
    if (search) params.set('search', search);
    api.get(`/api/security/agents/${agentId}/vulnerabilities/?${params}`)
      .then(res => { if (!cancelled) { setVulns(res.data.vulnerabilities); setTotal(res.data.total); } })
      .catch(() => { if (!cancelled) setError('Failed to load vulnerabilities.'); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [agentId, orgSlug, page, severitiesStr, fixAvailableParam, search]); // eslint-disable-line react-hooks/exhaustive-deps

  const totalPages = Math.max(1, Math.ceil(total / LIMIT));

  function goToPage(p) { setPage(p); }

  function handleFilterChange(newFilters) {
    setPage(0);
    setSearchParams(prev => {
      const next = new URLSearchParams(prev);
      if (newFilters.severities.length > 0) { next.set('severity', newFilters.severities.join(',')); } else { next.delete('severity'); }
      if (newFilters.fixAvailable) { next.set('fix_available', 'true'); } else { next.delete('fix_available'); }
      if (newFilters.search) { next.set('search', newFilters.search); } else { next.delete('search'); }
      return next;
    });
  }

  function handleClearFilters() {
    setPage(0);
    setSearchParams(prev => {
      const next = new URLSearchParams(prev);
      next.delete('severity');
      next.delete('fix_available');
      next.delete('search');
      return next;
    });
  }

  const filters = { severities, fixAvailable, search };
  const displayedVulns = hideAccepted ? vulns.filter(v => !acceptedCveIds.has(v.cve)) : vulns;

  if (loading) return <p className="py-4 text-sm text-muted-foreground">Loading…</p>;
  if (error) return <p className="text-sm text-red-600">{error}</p>;

  return (
    <div className="space-y-2">
      <FilterBar
        filters={filters}
        onChange={handleFilterChange}
        onClear={handleClearFilters}
        showTimeRange={false}
        showFixAvailable={true}
        showHideAccepted={true}
        hideAccepted={hideAccepted}
        onToggleHideAccepted={() => setHideAccepted(h => !h)}
        searchPlaceholder="Search CVE or package…"
      />
      {total > 0 && (
        <p className="text-xs text-muted-foreground text-right">
          Page {page + 1} of {totalPages} · {total} total
        </p>
      )}
      <div className="overflow-hidden rounded-lg border border-border bg-card">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border">
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">CVE</th>
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">Severity</th>
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">Package</th>
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">Version</th>
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">Fix</th>
            </tr>
          </thead>
          <tbody>
            {displayedVulns.length === 0 ? (
              <tr>
                <td colSpan={5} className="px-4 py-8 text-center text-muted-foreground">
                  No vulnerabilities found.
                </td>
              </tr>
            ) : (
              displayedVulns.flatMap((vuln) => {
                const isExpanded = expandedCve === vuln.cve;
                return [
                  <tr
                    key={vuln.cve}
                    onClick={() => setExpandedCve(isExpanded ? null : vuln.cve)}
                    className="border-b border-border last:border-0 cursor-pointer hover:bg-accent/40 transition-colors"
                  >
                    <td className="px-4 py-3 font-mono text-xs text-foreground">
                      <span className="flex items-center gap-1.5 flex-wrap">
                        <span className="text-muted-foreground text-xs select-none">{isExpanded ? '▾' : '▸'}</span>
                        {vuln.cve}
                        {acceptedCveIds.has(vuln.cve) && <AcceptedBadge />}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <SeverityBadge severity={vuln.severity} />
                    </td>
                    <td className="px-4 py-3 text-foreground">{vuln.package}</td>
                    <td className="px-4 py-3 font-mono text-xs text-muted-foreground">{vuln.version}</td>
                    <td className="px-4 py-3">
                      {vuln.fix_available ? (
                        <span className="text-xs font-medium text-green-600 dark:text-green-400">
                          Available
                        </span>
                      ) : (
                        <span className="text-xs text-muted-foreground">None</span>
                      )}
                    </td>
                  </tr>,
                  isExpanded && (
                    <tr key={`${vuln.cve}-advisory`} className="border-b border-border bg-muted/20">
                      <td colSpan={5} className="px-6 py-4">
                        <div className="flex items-center justify-between mb-2">
                          <button
                            onClick={(e) => { e.stopPropagation(); setSelectedVulnId(vuln.id); }}
                            className="text-xs text-blue-600 dark:text-blue-400 hover:underline"
                          >
                            View vulnerability details →
                          </button>
                        </div>
                        {vuln.advisory ? (
                          <CveAdvisoryBlock advisories={[vuln.advisory]} />
                        ) : (
                          <p className="text-sm text-muted-foreground italic">No advisory available.</p>
                        )}
                      </td>
                    </tr>
                  ),
                ].filter(Boolean);
              })
            )}
          </tbody>
        </table>
      </div>

      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-2 pt-2">
          <button
            onClick={() => goToPage(page - 1)}
            disabled={page === 0}
            aria-label="Previous page"
            className="rounded-md border border-border bg-background px-3 py-1.5 text-sm font-medium text-foreground hover:bg-accent disabled:opacity-50"
          >
            ← Previous
          </button>
          <span className="text-sm text-muted-foreground">
            {page + 1} / {totalPages}
          </span>
          <button
            onClick={() => goToPage(page + 1)}
            disabled={page >= totalPages - 1}
            aria-label="Next page"
            className="rounded-md border border-border bg-background px-3 py-1.5 text-sm font-medium text-foreground hover:bg-accent disabled:opacity-50"
          >
            Next →
          </button>
        </div>
      )}
      <VulnerabilitySlideOver
        agentId={agentId}
        orgSlug={orgSlug}
        vulnId={selectedVulnId}
        onClose={() => setSelectedVulnId(null)}
      />
    </div>
  );
}

export default function AgentDetail() {
  const { agentId } = useParams();
  const navigate = useNavigate();
  const { selectedOrg, isLoading: orgLoading } = useOrganization();

  const [activeTab, setActiveTab] = useState('events');
  const [refreshing, setRefreshing] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);

  async function handleRefresh() {
    if (!selectedOrg || refreshing) return;
    setRefreshing(true);
    try {
      await api.post('/api/security/dashboard/refresh/', {
        org: selectedOrg.slug,
        agent_id: agentId,
      });
      setRefreshKey((k) => k + 1);
    } finally {
      setRefreshing(false);
    }
  }

  if (orgLoading) return <p className="text-sm text-muted-foreground">Loading…</p>;
  if (!selectedOrg) return <p className="text-sm text-muted-foreground">No organisation assigned.</p>;

  return (
    <div className="space-y-6 p-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <button
            onClick={() => navigate('/security')}
            className="text-sm text-muted-foreground hover:text-foreground transition-colors"
          >
            ← Fleet
          </button>
          <h1 className="text-2xl font-semibold text-foreground">Agent {agentId}</h1>
        </div>
        <button
          onClick={handleRefresh}
          disabled={refreshing}
          className="rounded-md border border-border bg-background px-3 py-1.5 text-sm font-medium text-foreground shadow-sm hover:bg-accent disabled:opacity-50"
        >
          {refreshing ? 'Refreshing…' : 'Refresh'}
        </button>
      </div>

      <div>
        <div className="flex gap-4 border-b border-border">
          {['events', 'vulnerabilities'].map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`pb-2 text-sm font-medium capitalize transition-colors border-b-2 ${
                activeTab === tab
                  ? 'border-foreground text-foreground'
                  : 'border-transparent text-muted-foreground hover:text-foreground'
              }`}
            >
              {tab}
            </button>
          ))}
        </div>

        <div className="pt-4">
          {activeTab === 'events' && (
            <EventsTab key={`events-${refreshKey}`} agentId={agentId} orgSlug={selectedOrg.slug} />
          )}
          {activeTab === 'vulnerabilities' && (
            <VulnerabilitiesTab key={`vulns-${refreshKey}`} agentId={agentId} orgSlug={selectedOrg.slug} />
          )}
        </div>
      </div>
    </div>
  );
}
