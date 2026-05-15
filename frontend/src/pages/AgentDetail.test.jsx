import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

vi.mock('../lib/axios', () => ({
  default: { get: vi.fn(), post: vi.fn() },
}));

import api from '../lib/axios';
import { OrgContext } from '../context/OrgContext';
import AgentDetail from './AgentDetail';

const SELECTED_ORG = { id: 1, name: 'Acme Corp', slug: 'acme', wazuh_group: 'acme' };

const EVENTS_PAGE_1 = [
  { id: 'evt-abc', timestamp: '2024-01-15T10:00:00Z', rule_description: 'SSH brute force', rule_id: '5710', level: 10, severity: 'high',     agent_name: 'server-01' },
  { id: 'evt-def', timestamp: '2024-01-15T09:00:00Z', rule_description: 'Sudo usage',       rule_id: '5402', level:  5, severity: 'medium',   agent_name: 'server-01' },
  { id: 'evt-ghi', timestamp: '2024-01-15T08:00:00Z', rule_description: 'Failed login',     rule_id: '5501', level: 13, severity: 'critical', agent_name: 'server-01' },
];

const EVENTS_PAGE_2 = [
  { id: 'evt-jkl', timestamp: '2024-01-15T07:00:00Z', rule_description: 'Package updated', rule_id: '2900', level: 2, severity: 'low', agent_name: 'server-01' },
];

const EVENT_DETAIL_FULL = {
  id: 'evt-abc',
  timestamp: '2024-01-15T10:00:00Z',
  severity: 'high',
  rule_description: 'SSH brute force',
  rule_id: '5710',
  level: 10,
  rule_groups: ['authentication_failures', 'sshd'],
  agent_name: 'server-01',
  agent_ip: '10.0.0.1',
  log_source: '/var/log/auth.log',
  raw_log: 'Jan 15 10:00:00 server-01 sshd: Failed password for root',
  mitre: { tactic: ['Credential Access'], technique: ['Brute Force'], technique_id: ['T1110'] },
  network: { src_ip: '192.168.1.100', dst_ip: '10.0.0.1', protocol: 'tcp' },
};

const EVENT_DETAIL_MINIMAL = {
  id: 'evt-abc',
  timestamp: '2024-01-15T10:00:00Z',
  severity: 'high',
  rule_description: 'SSH brute force',
  rule_id: '5710',
  level: 10,
  rule_groups: ['authentication_failures'],
  agent_name: 'server-01',
  agent_ip: '10.0.0.1',
  log_source: '/var/log/auth.log',
  raw_log: 'Jan 15 10:00:00 server-01 sshd: Failed password for root',
};

const VULNS = [
  { id: 'vuln-001', cve: 'CVE-2024-0001', severity: 'critical', package: 'curl',    version: '7.68.0', fix_available: false },
  { id: 'vuln-002', cve: 'CVE-2024-0002', severity: 'high',     package: 'openssl', version: '1.1.1',  fix_available: true  },
  { id: 'vuln-003', cve: 'CVE-2024-0003', severity: 'medium',   package: 'libc6',   version: '2.31',   fix_available: true  },
];

const VULN_DETAIL_FULL = {
  id: 'vuln-001',
  cve: 'CVE-2024-0001',
  severity: 'critical',
  cvss_score: 9.8,
  package: 'curl',
  installed_version: '7.68.0',
  fixed_version: '7.88.1',
  description: 'A buffer overflow in curl allows remote attackers to execute arbitrary code.',
  published: '2024-01-10T00:00:00Z',
  references: [
    'https://nvd.nist.gov/vuln/detail/CVE-2024-0001',
    'https://curl.se/docs/CVE-2024-0001.html',
  ],
};

const VULN_DETAIL_MINIMAL = {
  id: 'vuln-002',
  cve: 'CVE-2024-0002',
  severity: 'high',
  cvss_score: null,
  package: 'openssl',
  installed_version: '1.1.1',
  fixed_version: null,
  description: 'An issue in openssl.',
  published: null,
};

function renderAgentDetail(agentId = '001', selectedOrg = SELECTED_ORG, search = '') {
  const path = `/security/agents/${agentId}${search ? `?${search}` : ''}`;
  return render(
    <MemoryRouter initialEntries={[path]}>
      <OrgContext.Provider value={{ orgs: [SELECTED_ORG], selectedOrg, setSelectedOrg: vi.fn(), isLoading: false }}>
        <Routes>
          <Route path="/security/agents/:agentId" element={<AgentDetail />} />
        </Routes>
      </OrgContext.Provider>
    </MemoryRouter>
  );
}

// Default: events endpoint returns EVENTS_PAGE_1, vulns endpoint returns VULNS
function setupMocks({
  events = EVENTS_PAGE_1,
  eventsTotal = 3,
  vulns = VULNS,
  vulnsTotal = 3,
  eventDetail = EVENT_DETAIL_FULL,
  vulnDetail = VULN_DETAIL_FULL,
  acceptances = [],
} = {}) {
  api.get.mockImplementation((url) => {
    if (url.includes('/risk-acceptances/'))       return Promise.resolve({ data: acceptances });
    // Detail URL: /events/<id>/ — has a non-empty segment after /events/
    if (/\/events\/[^?/]+\//.test(url))          return Promise.resolve({ data: eventDetail });
    if (url.includes('/events/'))                 return Promise.resolve({ data: { events, total: eventsTotal } });
    // Detail URL: /vulnerabilities/<id>/ — has a non-empty segment after /vulnerabilities/
    if (/\/vulnerabilities\/[^?/]+\//.test(url)) return Promise.resolve({ data: vulnDetail });
    if (url.includes('/vulnerabilities/'))        return Promise.resolve({ data: { vulnerabilities: vulns, total: vulnsTotal } });
    return Promise.reject(new Error(`unexpected: ${url}`));
  });
  api.post.mockResolvedValue({ data: { detail: 'Cache cleared.' } });
}

describe('AgentDetail — events tab', () => {
  beforeEach(() => { vi.clearAllMocks(); setupMocks(); });

  it('renders event list with severity badges', async () => {
    renderAgentDetail();

    await waitFor(() => expect(screen.getByText('SSH brute force')).toBeInTheDocument());
    expect(screen.getByText('Sudo usage')).toBeInTheDocument();
    expect(screen.getByText('Failed login')).toBeInTheDocument();
    expect(screen.getAllByText('high').length).toBeGreaterThan(0);
    expect(screen.getAllByText('medium').length).toBeGreaterThan(0);
    expect(screen.getAllByText('critical').length).toBeGreaterThan(0);
  });

  it('does not show Show more when total equals loaded count', async () => {
    renderAgentDetail();

    await waitFor(() => screen.getByText('SSH brute force'));
    expect(screen.queryByRole('button', { name: /show more/i })).not.toBeInTheDocument();
  });

  it('shows Show more button when total exceeds loaded count', async () => {
    setupMocks({ eventsTotal: 150 });
    renderAgentDetail();

    await waitFor(() => expect(screen.getByRole('button', { name: /show more/i })).toBeInTheDocument());
  });

  it('clicking Show more appends results without clearing existing ones', async () => {
    api.get
      .mockResolvedValueOnce({ data: { events: EVENTS_PAGE_1, total: 4 } })
      .mockResolvedValueOnce({ data: { events: EVENTS_PAGE_2, total: 4 } });
    api.post.mockResolvedValue({ data: { detail: 'Cache cleared.' } });

    const user = userEvent.setup();
    renderAgentDetail();

    await waitFor(() => screen.getByText('SSH brute force'));
    await user.click(screen.getByRole('button', { name: /show more/i }));

    await waitFor(() => expect(screen.getByText('Package updated')).toBeInTheDocument());
    expect(screen.getByText('SSH brute force')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /show more/i })).not.toBeInTheDocument();
  });

  it('shows no org message when selectedOrg is null', () => {
    renderAgentDetail('001', null);
    expect(screen.getByText('No organisation assigned.')).toBeInTheDocument();
  });
});

describe('AgentDetail — vulnerabilities tab', () => {
  beforeEach(() => { vi.clearAllMocks(); setupMocks(); });

  async function openVulnsTab() {
    const user = userEvent.setup();
    renderAgentDetail();
    // Wait for events tab to finish loading, then switch
    await waitFor(() => screen.getByText('SSH brute force'));
    await user.click(screen.getByRole('button', { name: /vulnerabilities/i }));
    return user;
  }

  it('renders vulnerability list with severity badges and CVE IDs', async () => {
    await openVulnsTab();

    await waitFor(() => expect(screen.getByText('CVE-2024-0001')).toBeInTheDocument());
    expect(screen.getByText('CVE-2024-0002')).toBeInTheDocument();
    expect(screen.getByText('CVE-2024-0003')).toBeInTheDocument();
    // Severity badges in vuln list
    expect(screen.getAllByText('critical').length).toBeGreaterThan(0);
    expect(screen.getAllByText('high').length).toBeGreaterThan(0);
    expect(screen.getAllByText('medium').length).toBeGreaterThan(0);
  });

  it('shows Fix available correctly', async () => {
    await openVulnsTab();

    await waitFor(() => screen.getByText('CVE-2024-0001'));
    // CVE-2024-0001 fix_available=false → "None"; CVE-2024-0002 fix_available=true → "Available"
    expect(screen.getByText('None')).toBeInTheDocument();
    expect(screen.getAllByText('Available').length).toBeGreaterThan(0);
  });

  it('shows pagination controls when total > 50', async () => {
    setupMocks({ vulnsTotal: 120 });
    await openVulnsTab();

    await waitFor(() =>
      expect(screen.getByRole('button', { name: /next/i })).toBeInTheDocument()
    );
    expect(screen.getByRole('button', { name: /previous/i })).toBeInTheDocument();
  });

  it('Previous button disabled on first page', async () => {
    setupMocks({ vulnsTotal: 120 });
    await openVulnsTab();

    await waitFor(() => screen.getByRole('button', { name: /previous/i }));
    expect(screen.getByRole('button', { name: /previous/i })).toBeDisabled();
  });

  it('clicking Next navigates to page 2', async () => {
    setupMocks({ vulnsTotal: 120 });
    const user = await openVulnsTab();

    await waitFor(() => screen.getByRole('button', { name: /next/i }));
    await user.click(screen.getByRole('button', { name: /next/i }));

    await waitFor(() =>
      expect(api.get).toHaveBeenCalledWith(expect.stringContaining('offset=50'))
    );
  });
});

describe('AgentDetail — FilterBar', () => {
  beforeEach(() => { vi.clearAllMocks(); setupMocks(); });

  it('renders all four severity chips', async () => {
    renderAgentDetail();
    await waitFor(() => screen.getByText('SSH brute force'));
    expect(screen.getByRole('button', { name: 'critical' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'high' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'medium' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'low' })).toBeInTheDocument();
  });

  it('renders time range dropdown and search input', async () => {
    renderAgentDetail();
    await waitFor(() => screen.getByText('SSH brute force'));
    expect(screen.getByRole('combobox', { name: /time range/i })).toBeInTheDocument();
    expect(screen.getByRole('textbox', { name: /search rules/i })).toBeInTheDocument();
  });

  it('does not show clear button when no filters are active', async () => {
    renderAgentDetail();
    await waitFor(() => screen.getByText('SSH brute force'));
    expect(screen.queryByRole('button', { name: /clear filters/i })).not.toBeInTheDocument();
  });

  it('clicking a severity chip calls API with that severity', async () => {
    const user = userEvent.setup();
    renderAgentDetail();
    await waitFor(() => screen.getByText('SSH brute force'));

    await user.click(screen.getByRole('button', { name: 'critical' }));

    await waitFor(() =>
      expect(api.get).toHaveBeenCalledWith(expect.stringContaining('severity=critical'))
    );
  });

  it('clicking two severity chips calls API with both', async () => {
    const user = userEvent.setup();
    renderAgentDetail();
    await waitFor(() => screen.getByText('SSH brute force'));

    await user.click(screen.getByRole('button', { name: 'critical' }));
    await waitFor(() => expect(api.get).toHaveBeenCalledWith(expect.stringContaining('severity=critical')));

    await user.click(screen.getByRole('button', { name: 'high' }));
    await waitFor(() =>
      expect(api.get).toHaveBeenCalledWith(expect.stringContaining('severity=critical%2Chigh'))
    );
  });

  it('changing time range calls API with hours param', async () => {
    const user = userEvent.setup();
    renderAgentDetail();
    await waitFor(() => screen.getByText('SSH brute force'));

    await user.selectOptions(screen.getByRole('combobox', { name: /time range/i }), '6');

    await waitFor(() =>
      expect(api.get).toHaveBeenCalledWith(expect.stringContaining('hours=6'))
    );
  });

  it('typing in search calls API with search param', async () => {
    const user = userEvent.setup();
    renderAgentDetail();
    await waitFor(() => screen.getByText('SSH brute force'));

    await user.type(screen.getByRole('textbox', { name: /search rules/i }), 'brute');

    await waitFor(() =>
      expect(api.get).toHaveBeenCalledWith(expect.stringContaining('search=brute'))
    );
  });

  it('shows clear button when a filter is active', async () => {
    const user = userEvent.setup();
    renderAgentDetail();
    await waitFor(() => screen.getByText('SSH brute force'));

    await user.click(screen.getByRole('button', { name: 'critical' }));

    await waitFor(() =>
      expect(screen.getByRole('button', { name: /clear filters/i })).toBeInTheDocument()
    );
  });

  it('clear button removes filter params from URL and calls API without them', async () => {
    const user = userEvent.setup();
    renderAgentDetail();
    await waitFor(() => screen.getByText('SSH brute force'));

    await user.click(screen.getByRole('button', { name: 'critical' }));
    await waitFor(() => screen.getByRole('button', { name: /clear filters/i }));

    await user.click(screen.getByRole('button', { name: /clear filters/i }));

    await waitFor(() => {
      const calls = api.get.mock.calls.map(c => c[0]);
      const lastCall = calls[calls.length - 1];
      expect(lastCall).not.toContain('severity=');
    });
  });

  it('filter change resets offset to 0', async () => {
    api.get
      .mockResolvedValueOnce({ data: { events: EVENTS_PAGE_1, total: 4 } })
      .mockResolvedValueOnce({ data: { events: EVENTS_PAGE_2, total: 4 } })
      .mockResolvedValue({ data: { events: EVENTS_PAGE_1, total: 4 } });
    api.post.mockResolvedValue({ data: { detail: 'Cache cleared.' } });

    const user = userEvent.setup();
    renderAgentDetail();

    await waitFor(() => screen.getByText('SSH brute force'));
    await user.click(screen.getByRole('button', { name: /show more/i }));
    await waitFor(() => screen.getByText('Package updated'));

    await user.click(screen.getByRole('button', { name: 'critical' }));

    await waitFor(() => {
      const calls = api.get.mock.calls.map(c => c[0]);
      const lastCall = calls[calls.length - 1];
      expect(lastCall).toContain('offset=0');
      expect(lastCall).toContain('severity=critical');
    });
  });

  it('initial URL params restore filter state and pass them to API', async () => {
    renderAgentDetail('001', SELECTED_ORG, 'severity=high&hours=6');

    await waitFor(() =>
      expect(api.get).toHaveBeenCalledWith(expect.stringMatching(/severity=high/))
    );
    await waitFor(() =>
      expect(api.get).toHaveBeenCalledWith(expect.stringMatching(/hours=6/))
    );
  });
});

describe('AgentDetail — EventSlideOver', () => {
  beforeEach(() => { vi.clearAllMocks(); setupMocks(); });

  it('clicking an event row opens the slide-over and fetches detail', async () => {
    const user = userEvent.setup();
    renderAgentDetail();
    await waitFor(() => screen.getByText('SSH brute force'));

    await user.click(screen.getByText('SSH brute force'));

    await waitFor(() =>
      expect(api.get).toHaveBeenCalledWith(expect.stringContaining('/events/evt-abc/'))
    );
    await waitFor(() =>
      expect(screen.getByText('Event Detail')).toBeInTheDocument()
    );
  });

  it('renders summary, rule details, and agent sections', async () => {
    const user = userEvent.setup();
    renderAgentDetail();
    await waitFor(() => screen.getByText('SSH brute force'));

    await user.click(screen.getByText('SSH brute force'));

    await waitFor(() => screen.getByText('Summary'));
    expect(screen.getByText('Rule Details')).toBeInTheDocument();
    expect(screen.getByText('Agent')).toBeInTheDocument();
  });

  it('renders MITRE ATT&CK section when data is present', async () => {
    const user = userEvent.setup();
    renderAgentDetail();
    await waitFor(() => screen.getByText('SSH brute force'));

    await user.click(screen.getByText('SSH brute force'));

    await waitFor(() => screen.getByText('MITRE ATT&CK'));
    expect(screen.getByText('Credential Access')).toBeInTheDocument();
    expect(screen.getByText('T1110')).toBeInTheDocument();
  });

  it('renders Network section when data is present', async () => {
    const user = userEvent.setup();
    renderAgentDetail();
    await waitFor(() => screen.getByText('SSH brute force'));

    await user.click(screen.getByText('SSH brute force'));

    await waitFor(() => screen.getByText('Network'));
    expect(screen.getByText('192.168.1.100')).toBeInTheDocument();
  });

  it('does not render MITRE ATT&CK section when absent from response', async () => {
    setupMocks({ eventDetail: EVENT_DETAIL_MINIMAL });
    const user = userEvent.setup();
    renderAgentDetail();
    await waitFor(() => screen.getByText('SSH brute force'));

    await user.click(screen.getByText('SSH brute force'));

    await waitFor(() => screen.getByText('Rule Details'));
    expect(screen.queryByText('MITRE ATT&CK')).not.toBeInTheDocument();
  });

  it('does not render Network section when absent from response', async () => {
    setupMocks({ eventDetail: EVENT_DETAIL_MINIMAL });
    const user = userEvent.setup();
    renderAgentDetail();
    await waitFor(() => screen.getByText('SSH brute force'));

    await user.click(screen.getByText('SSH brute force'));

    await waitFor(() => screen.getByText('Rule Details'));
    expect(screen.queryByText('Network')).not.toBeInTheDocument();
  });

  it('raw log Advanced section is collapsed by default', async () => {
    const user = userEvent.setup();
    renderAgentDetail();
    await waitFor(() => screen.getByText('SSH brute force'));

    await user.click(screen.getByText('SSH brute force'));

    await waitFor(() => screen.getByText('Advanced'));
    const details = screen.getByText('Advanced').closest('details');
    expect(details.open).toBe(false);
  });

  it('slide-over closes when close button is clicked', async () => {
    const user = userEvent.setup();
    renderAgentDetail();
    await waitFor(() => screen.getByText('SSH brute force'));

    await user.click(screen.getByText('SSH brute force'));
    await waitFor(() => screen.getByText('Event Detail'));

    await user.click(screen.getByRole('button', { name: /close/i }));

    await waitFor(() =>
      expect(screen.queryByText('Summary')).not.toBeInTheDocument()
    );
  });
});

describe('AgentDetail — Vuln FilterBar', () => {
  beforeEach(() => { vi.clearAllMocks(); setupMocks(); });

  async function openVulnsTab() {
    const user = userEvent.setup();
    renderAgentDetail();
    await waitFor(() => screen.getByText('SSH brute force'));
    await user.click(screen.getByRole('button', { name: /vulnerabilities/i }));
    await waitFor(() => screen.getByText('CVE-2024-0001'));
    return user;
  }

  it('shows Fix available toggle but not time range dropdown', async () => {
    await openVulnsTab();
    expect(screen.getByRole('button', { name: /fix available/i })).toBeInTheDocument();
    expect(screen.queryByRole('combobox', { name: /time range/i })).not.toBeInTheDocument();
  });

  it('shows Search CVE or package input', async () => {
    await openVulnsTab();
    expect(screen.getByRole('textbox', { name: /search cve or package/i })).toBeInTheDocument();
  });

  it('clicking Fix available calls API with fix_available=true', async () => {
    const user = await openVulnsTab();
    await user.click(screen.getByRole('button', { name: /fix available/i }));
    await waitFor(() =>
      expect(api.get).toHaveBeenCalledWith(expect.stringContaining('fix_available=true'))
    );
  });

  it('clicking a severity chip calls API with that severity', async () => {
    const user = await openVulnsTab();
    await user.click(screen.getByRole('button', { name: 'critical' }));
    await waitFor(() =>
      expect(api.get).toHaveBeenCalledWith(expect.stringContaining('severity=critical'))
    );
  });

  it('typing in search calls API with search param', async () => {
    const user = await openVulnsTab();
    await user.type(screen.getByRole('textbox', { name: /search cve or package/i }), 'z');
    await waitFor(() =>
      expect(api.get).toHaveBeenCalledWith(expect.stringContaining('search=z'))
    );
  });

  it('filter change resets page to offset 0', async () => {
    setupMocks({ vulnsTotal: 120 });
    const user = await openVulnsTab();

    await waitFor(() => screen.getByRole('button', { name: /next/i }));
    await user.click(screen.getByRole('button', { name: /next/i }));
    await waitFor(() =>
      expect(api.get).toHaveBeenCalledWith(expect.stringContaining('offset=50'))
    );

    await user.click(screen.getByRole('button', { name: 'critical' }));

    await waitFor(() => {
      const calls = api.get.mock.calls.map(c => c[0]);
      const lastCall = calls[calls.length - 1];
      expect(lastCall).toContain('offset=0');
      expect(lastCall).toContain('severity=critical');
    });
  });

  it('initial URL params restore filter state on mount', async () => {
    const user = userEvent.setup();
    renderAgentDetail('001', SELECTED_ORG, 'severity=critical&fix_available=true');
    await waitFor(() => screen.getByText('SSH brute force'));
    await user.click(screen.getByRole('button', { name: /vulnerabilities/i }));

    await waitFor(() =>
      expect(api.get).toHaveBeenCalledWith(
        expect.stringMatching(/vulnerabilities.*severity=critical/)
      )
    );
    await waitFor(() =>
      expect(api.get).toHaveBeenCalledWith(
        expect.stringMatching(/vulnerabilities.*fix_available=true/)
      )
    );
  });

  it('clear filters removes all vuln filter params', async () => {
    const user = await openVulnsTab();

    await user.click(screen.getByRole('button', { name: /fix available/i }));
    await waitFor(() => screen.getByRole('button', { name: /clear filters/i }));

    await user.click(screen.getByRole('button', { name: /clear filters/i }));

    await waitFor(() => {
      const calls = api.get.mock.calls.map(c => c[0]);
      const lastVulnCall = [...calls].reverse().find(c => c.includes('/vulnerabilities/'));
      expect(lastVulnCall).not.toContain('fix_available=');
      expect(lastVulnCall).not.toContain('severity=');
    });
  });
});

describe('AgentDetail — VulnerabilitySlideOver', () => {
  beforeEach(() => { vi.clearAllMocks(); setupMocks(); });

  async function openVulnsTab() {
    const user = userEvent.setup();
    renderAgentDetail();
    await waitFor(() => screen.getByText('SSH brute force'));
    await user.click(screen.getByRole('button', { name: /vulnerabilities/i }));
    await waitFor(() => screen.getByText('CVE-2024-0001'));
    return user;
  }

  async function openSlideOver(user) {
    await user.click(screen.getByText('CVE-2024-0001'));
    await waitFor(() => screen.getByText('View vulnerability details →'));
    await user.click(screen.getByText('View vulnerability details →'));
  }

  it('clicking a vuln row opens the slide-over and fetches detail', async () => {
    const user = await openVulnsTab();

    await openSlideOver(user);

    await waitFor(() =>
      expect(api.get).toHaveBeenCalledWith(expect.stringContaining('/vulnerabilities/vuln-001/'))
    );
    await waitFor(() =>
      expect(screen.getByText('Vulnerability Detail')).toBeInTheDocument()
    );
  });

  it('renders Summary, Package, and Details sections', async () => {
    const user = await openVulnsTab();

    await openSlideOver(user);

    await waitFor(() => screen.getByText('Summary'));
    expect(screen.getAllByText('Package').length).toBeGreaterThan(0);
    expect(screen.getByText('Details')).toBeInTheDocument();
  });

  it('renders CVE ID, CVSS score, severity, and package details', async () => {
    const user = await openVulnsTab();

    await openSlideOver(user);

    await waitFor(() => screen.getByText('Summary'));
    expect(screen.getAllByText('CVE-2024-0001').length).toBeGreaterThan(0);
    expect(screen.getByText('9.8')).toBeInTheDocument();
    expect(screen.getAllByText('7.68.0').length).toBeGreaterThan(0);
    expect(screen.getByText('7.88.1')).toBeInTheDocument();
  });

  it('renders References section with clickable links when present', async () => {
    const user = await openVulnsTab();

    await openSlideOver(user);

    await waitFor(() => screen.getByText('References'));
    const links = screen.getAllByRole('link');
    expect(links.some(l => l.href.includes('nvd.nist.gov'))).toBe(true);
  });

  it('does not render References section when absent from response', async () => {
    setupMocks({ vulnDetail: VULN_DETAIL_MINIMAL });
    const user = await openVulnsTab();

    await openSlideOver(user);

    await waitFor(() => screen.getByText('Summary'));
    expect(screen.queryByText('References')).not.toBeInTheDocument();
  });

  it('slide-over closes when close button is clicked', async () => {
    const user = await openVulnsTab();

    await user.click(screen.getByText('CVE-2024-0001'));
    await waitFor(() => screen.getByText('Vulnerability Detail'));

    await user.click(screen.getByRole('button', { name: /close/i }));

    await waitFor(() =>
      expect(screen.queryByText('Summary')).not.toBeInTheDocument()
    );
  });
});

describe('AgentDetail — vulnerabilities tab — risk acceptance', () => {
  const ACCEPTANCES = [
    { id: 1, cve_id: 'CVE-2024-0001', org_slug: 'acme', accepted_by: 'alice', accepted_at: '2024-01-15T10:00:00Z', note: 'Mitigated', severity: 'critical', cvss_score: 9.8 },
  ];

  beforeEach(() => { vi.clearAllMocks(); });

  it('shows Accepted badge on a CVE that has been accepted', async () => {
    setupMocks({ acceptances: ACCEPTANCES });
    const user = userEvent.setup();
    renderAgentDetail();
    await user.click(screen.getByRole('button', { name: /vulnerabilities/i }));
    // CVE-2024-0001 is hidden by default; toggle to reveal it
    await waitFor(() => screen.getByRole('button', { name: /hide accepted/i }));
    await user.click(screen.getByRole('button', { name: /hide accepted/i }));
    await waitFor(() => screen.getByText('CVE-2024-0001'));
    expect(screen.getAllByText('Accepted').length).toBeGreaterThan(0);
  });

  it('does not show Accepted badge when no acceptances exist', async () => {
    setupMocks({ acceptances: [] });
    const user = userEvent.setup();
    renderAgentDetail();
    await user.click(screen.getByRole('button', { name: /vulnerabilities/i }));
    await waitFor(() => screen.getByText('CVE-2024-0001'));
    expect(screen.queryByText('Accepted')).not.toBeInTheDocument();
  });

  it('hides accepted CVEs by default', async () => {
    setupMocks({ acceptances: ACCEPTANCES });
    const user = userEvent.setup();
    renderAgentDetail();
    await user.click(screen.getByRole('button', { name: /vulnerabilities/i }));
    // CVE-2024-0002 is not accepted — it should be visible
    await waitFor(() => screen.getByText('CVE-2024-0002'));
    expect(screen.queryByText('CVE-2024-0001')).not.toBeInTheDocument();
  });

  it('shows accepted CVEs after toggling Hide accepted off', async () => {
    setupMocks({ acceptances: ACCEPTANCES });
    const user = userEvent.setup();
    renderAgentDetail();
    await user.click(screen.getByRole('button', { name: /vulnerabilities/i }));
    await waitFor(() => screen.getByText('CVE-2024-0002'));
    expect(screen.queryByText('CVE-2024-0001')).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /hide accepted/i }));

    await waitFor(() => screen.getByText('CVE-2024-0001'));
    expect(screen.getAllByText('Accepted').length).toBeGreaterThan(0);
  });

  it('Hide accepted button is highlighted (aria-pressed) by default', async () => {
    setupMocks({ acceptances: [] });
    const user = userEvent.setup();
    renderAgentDetail();
    await user.click(screen.getByRole('button', { name: /vulnerabilities/i }));
    await waitFor(() => screen.getByText('CVE-2024-0001'));
    expect(screen.getByRole('button', { name: /hide accepted/i })).toHaveAttribute('aria-pressed', 'true');
  });
});
