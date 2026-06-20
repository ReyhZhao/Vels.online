import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';

vi.mock('../lib/axios', () => ({
  default: { get: vi.fn(), post: vi.fn() },
}));

import api from '../lib/axios';
import { OrgContext } from '../context/OrgContext';
import FleetEventsPage from './FleetEventsPage';

const SELECTED_ORG = { id: 1, name: 'Acme Corp', slug: 'acme', wazuh_group: 'acme' };

const AGENTS = [
  { id: '001', name: 'server-01', ip: '10.0.0.1', status: 'active',       os: 'Ubuntu 22.04', last_seen: '2024-01-15T10:00:00Z' },
  { id: '002', name: 'server-02', ip: '10.0.0.2', status: 'disconnected', os: 'Debian 11',    last_seen: '2024-01-14T08:00:00Z' },
];

const EVENTS_PAGE_1 = [
  { id: 'evt-001', timestamp: '2024-01-15T10:00:00Z', rule_description: 'SSH brute force', rule_id: '5710', level: 10, severity: 'high',     agent_id: '001', agent_name: 'server-01' },
  { id: 'evt-002', timestamp: '2024-01-15T09:00:00Z', rule_description: 'Rootkit detected', rule_id: '9999', level: 13, severity: 'critical', agent_id: '002', agent_name: 'server-02' },
];

const EVENTS_PAGE_2 = [
  { id: 'evt-003', timestamp: '2024-01-15T08:00:00Z', rule_description: 'Package updated', rule_id: '2900', level: 2, severity: 'low', agent_id: '001', agent_name: 'server-01' },
];

const STATS = {
  critical: 3,
  high: 7,
  medium: 12,
  low: 5,
  total: 27,
  events_24h: 42,
};

const EVENT_DETAIL = {
  id: 'evt-001',
  timestamp: '2024-01-15T10:00:00Z',
  severity: 'high',
  rule_description: 'SSH brute force',
  rule_id: '5710',
  level: 10,
  rule_groups: ['sshd'],
  agent_name: 'server-01',
  agent_ip: '10.0.0.1',
  log_source: '/var/log/auth.log',
  raw_log: 'Failed password for root',
};

function renderPage(selectedOrg = SELECTED_ORG) {
  return render(
    <MemoryRouter>
      <OrgContext.Provider value={{ orgs: [SELECTED_ORG], selectedOrg, setSelectedOrg: vi.fn(), isLoading: false }}>
        <FleetEventsPage />
      </OrgContext.Provider>
    </MemoryRouter>
  );
}

function setupMocks({ events = EVENTS_PAGE_1, total = 2, stats = STATS } = {}) {
  api.get.mockImplementation((url) => {
    if (url.includes('/security/agents/') && url.includes('/events/')) {
      return Promise.resolve({ data: EVENT_DETAIL });
    }
    if (url.includes('/security/agents/')) {
      return Promise.resolve({ data: AGENTS });
    }
    if (url.includes('/security/events/')) {
      return Promise.resolve({ data: { events, total, stats } });
    }
    return Promise.reject(new Error(`unexpected url: ${url}`));
  });
}

describe('FleetEventsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setupMocks();
  });

  it('shows no org message when selectedOrg is null', () => {
    renderPage(null);
    expect(screen.getByText('No organisation assigned.')).toBeInTheDocument();
  });

  it('shows loading state while fetching', async () => {
    api.get.mockReturnValue(new Promise(() => {})); // never resolves
    renderPage();
    await waitFor(() => expect(screen.getAllByText('Loading…').length).toBeGreaterThan(0));
  });

  it('renders all six stats cards with API values', async () => {
    renderPage();

    await waitFor(() => expect(screen.getAllByText('SSH brute force').length).toBeGreaterThan(0));

    expect(screen.getByText('3')).toBeInTheDocument();   // critical
    expect(screen.getByText('7')).toBeInTheDocument();   // high
    expect(screen.getByText('12')).toBeInTheDocument();  // medium
    expect(screen.getByText('5')).toBeInTheDocument();   // low
    expect(screen.getByText('27')).toBeInTheDocument();  // total
    expect(screen.getByText('42')).toBeInTheDocument();  // events_24h
  });

  it('renders event rows with agent, severity, rule id, description', async () => {
    renderPage();

    await waitFor(() => expect(screen.getAllByText('SSH brute force').length).toBeGreaterThan(0));

    // agent name appears in the dropdown, the table row and the mobile card
    expect(screen.getAllByText('server-01').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('server-02').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('5710').length).toBeGreaterThan(0);
    expect(screen.getAllByText('9999').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Rootkit detected').length).toBeGreaterThan(0);
  });

  it('shows empty state when no events returned', async () => {
    setupMocks({ events: [], total: 0 });
    renderPage();

    await waitFor(() => expect(screen.getAllByText('No events found.').length).toBeGreaterThan(0));
  });

  it('shows error fallback when API fails', async () => {
    api.get.mockImplementation((url) => {
      if (url.includes('/security/agents/') && !url.includes('/events/')) {
        return Promise.resolve({ data: AGENTS });
      }
      return Promise.reject({ response: { data: { detail: 'OpenSearch unavailable' } } });
    });
    renderPage();

    await waitFor(() =>
      expect(screen.getByText('OpenSearch unavailable')).toBeInTheDocument()
    );
  });

  it('shows generic error fallback when API error has no detail', async () => {
    api.get.mockRejectedValue(new Error('Network error'));
    renderPage();

    await waitFor(() =>
      expect(screen.getByText('Failed to load events.')).toBeInTheDocument()
    );
  });

  it('show more button appends next page of events', async () => {
    const user = userEvent.setup();
    setupMocks({ events: EVENTS_PAGE_1, total: 3 });

    renderPage();
    await waitFor(() => expect(screen.getAllByText('SSH brute force').length).toBeGreaterThan(0));

    api.get.mockImplementation((url) => {
      if (url.includes('/security/agents/') && !url.includes('/events/')) {
        return Promise.resolve({ data: AGENTS });
      }
      if (url.includes('/security/events/')) {
        return Promise.resolve({ data: { events: EVENTS_PAGE_2, total: 3, stats: STATS } });
      }
      return Promise.reject(new Error(`unexpected url: ${url}`));
    });

    const showMoreBtn = screen.getByRole('button', { name: /show more/i });
    await user.click(showMoreBtn);

    await waitFor(() => expect(screen.getAllByText('Package updated').length).toBeGreaterThan(0));
    // original rows still present
    expect(screen.getAllByText('SSH brute force').length).toBeGreaterThan(0);
  });

  it('hides show more when all events are loaded', async () => {
    setupMocks({ events: EVENTS_PAGE_1, total: 2 });
    renderPage();

    await waitFor(() => expect(screen.getAllByText('SSH brute force').length).toBeGreaterThan(0));
    expect(screen.queryByRole('button', { name: /show more/i })).not.toBeInTheDocument();
  });

  it('clicking a row opens the slide-over and fetches event detail', async () => {
    const user = userEvent.setup();
    renderPage();

    await waitFor(() => expect(screen.getAllByText('SSH brute force').length).toBeGreaterThan(0));
    await user.click(screen.getAllByText('SSH brute force')[0]);

    await waitFor(() =>
      expect(api.get).toHaveBeenCalledWith(expect.stringContaining('/events/evt-001/'))
    );
    await waitFor(() =>
      expect(screen.getByText('Event Detail')).toBeInTheDocument()
    );
  });

  it('renders the Events heading with org name', async () => {
    renderPage();
    await waitFor(() => expect(screen.getByText('Events — Acme Corp')).toBeInTheDocument());
  });

  it('renders all eight time range buttons', async () => {
    renderPage();
    await waitFor(() => expect(screen.getAllByText('SSH brute force').length).toBeGreaterThan(0));

    for (const label of ['5m', '15m', '30m', '1h', '6h', '24h', '7d', '30d']) {
      expect(screen.getByRole('button', { name: label })).toBeInTheDocument();
    }
  });
});

describe('FleetEventsPage — bulk promote', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setupMocks();
    api.post.mockImplementation((url, body) => {
      if (body && body.commit) {
        return Promise.resolve({ data: { display_id: 'INC-2026-0123' } });
      }
      return Promise.resolve({
        data: {
          form_payload: {
            title: 'Wazuh alert on server-01: SSH brute force',
            description: 'Wazuh alert triggered',
            severity: 'high',
            source_kind: 'wazuh_event',
            source_ref: { event_id: 'evt-001' },
          },
          open_incidents: [],
        },
      });
    });
  });

  it('renders a sm:hidden mobile card list with per-event checkboxes', async () => {
    renderPage();
    await waitFor(() => expect(screen.getAllByText('SSH brute force').length).toBeGreaterThan(0));
    const cardList = document.querySelector('.sm\\:hidden');
    expect(cardList.querySelector('input[type="checkbox"]')).toBeTruthy();
    expect(cardList.textContent).toContain('SSH brute force');
  });

  it('selecting events and promoting opens a modal that aggregates them into one incident', async () => {
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => expect(screen.getAllByText('SSH brute force').length).toBeGreaterThan(0));

    await user.click(screen.getByLabelText('Select all'));
    await user.click(screen.getByRole('button', { name: /promote to incident \(2\)/i }));

    // preview call to the promote endpoint
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/api/incidents/promote/', expect.objectContaining({ source_kind: 'wazuh_event' })));
    // modal with aggregated title
    await waitFor(() => expect(screen.getByText(/Create Incident from 2 events/i)).toBeInTheDocument());

    await user.click(screen.getByRole('button', { name: /^create incident$/i }));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/api/incidents/promote/', expect.objectContaining({ commit: true, org: 'acme' })));
  });
});
