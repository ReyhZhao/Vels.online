import { render, screen, waitFor, act, fireEvent, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';

vi.mock('../lib/axios', () => ({
  default: { get: vi.fn(), post: vi.fn() },
}));

vi.mock('../components/CreateIncidentModal', () => ({
  default: ({ open, onClose }) =>
    open ? <div data-testid="create-modal"><button onClick={onClose}>close-modal</button></div> : null,
}));

const mockUseAuth = vi.fn(() => ({ user: null }));
vi.mock('../context/AuthContext', () => ({ useAuth: () => mockUseAuth() }));

const mockNavigate = vi.fn();
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return { ...actual, useNavigate: () => mockNavigate };
});

import api from '../lib/axios';
import IncidentList from './IncidentList';

const INCIDENTS = [
  {
    id: 1,
    display_id: 'INC-2026-0001',
    title: 'Suspicious login',
    severity: 'high',
    tlp: 'amber',
    state: 'new',
    org_slug: 'acme',
    created_at: '2026-01-15T10:00:00Z',
    assignee_username: null,
  },
  {
    id: 2,
    display_id: 'INC-2026-0002',
    title: 'Malware detected',
    severity: 'critical',
    tlp: 'green',
    state: 'in_progress',
    org_slug: 'acme',
    created_at: '2026-01-20T12:00:00Z',
    assignee_username: 'charlie',
  },
];

const PAGE_RESPONSE = (results = INCIDENTS, extras = {}) => ({
  data: { count: results.length, page: 1, per_page: 25, total_pages: 1, results, ...extras },
});

function renderPage(initialEntry = '/') {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <IncidentList />
    </MemoryRouter>
  );
}

describe('IncidentList', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuth.mockReturnValue({ user: null });
    mockNavigate.mockReset();
  });

  it('shows loading state while fetching', () => {
    api.get.mockReturnValue(new Promise(() => {}));
    renderPage();
    // Both mobile card list and desktop table render "Loading…" in jsdom (no CSS media queries)
    expect(screen.getAllByText('Loading…').length).toBeGreaterThan(0);
  });

  it('shows empty state when no incidents', async () => {
    api.get.mockResolvedValue(PAGE_RESPONSE([]));
    renderPage();
    await waitFor(() => expect(screen.getAllByText('No incidents.').length).toBeGreaterThan(0));
  });

  it('renders incident rows with correct data', async () => {
    api.get.mockResolvedValue(PAGE_RESPONSE());
    renderPage();
    await waitFor(() => screen.getAllByText('INC-2026-0001'));
    expect(screen.getAllByText('Suspicious login').length).toBeGreaterThan(0);
    expect(screen.getAllByText('INC-2026-0002').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Malware detected').length).toBeGreaterThan(0);
    expect(screen.getAllByText('high').length).toBeGreaterThan(0);
    expect(screen.getAllByText('critical').length).toBeGreaterThan(0);
  });

  it('aligns desktop State and TLP cells under their own headers', async () => {
    // Regression for #392: header order was State, TLP but the body rendered
    // TLP, State — so each value sat under the wrong column header.
    api.get.mockResolvedValue(PAGE_RESPONSE());
    renderPage();
    await waitFor(() => screen.getAllByText('INC-2026-0001'));

    const table = screen.getByRole('table');
    const headers = within(table)
      .getAllByRole('columnheader')
      .map(h => h.textContent.trim());
    const stateIdx = headers.findIndex(h => /^State/.test(h));
    const tlpIdx = headers.findIndex(h => /^TLP/.test(h));
    expect(stateIdx).toBeGreaterThanOrEqual(0);
    expect(tlpIdx).toBeGreaterThanOrEqual(0);

    const firstRow = within(table).getAllByRole('row')[1]; // [0] is the header row
    const cells = within(firstRow).getAllByRole('cell');
    expect(cells[stateIdx].textContent).toContain('new');       // INC-2026-0001.state
    expect(cells[tlpIdx].textContent).toContain('TLP:AMBER');    // INC-2026-0001.tlp
  });

  it('shows page heading', async () => {
    api.get.mockResolvedValue(PAGE_RESPONSE([]));
    renderPage();
    await waitFor(() => expect(screen.getByText('Incidents')).toBeInTheDocument());
  });

  it('fetches from the incidents endpoint', async () => {
    api.get.mockResolvedValue(PAGE_RESPONSE([]));
    renderPage();
    await waitFor(() => expect(api.get).toHaveBeenCalledWith('/api/incidents/', expect.any(Object)));
  });

  it('shows error message on failure', async () => {
    api.get.mockRejectedValue({ response: { data: { detail: 'Permission denied.' } } });
    renderPage();
    await waitFor(() => expect(screen.getByText('Permission denied.')).toBeInTheDocument());
  });

  it('renders the New Incident button', async () => {
    api.get.mockResolvedValue(PAGE_RESPONSE([]));
    renderPage();
    await waitFor(() => expect(screen.getByRole('button', { name: /new incident/i })).toBeInTheDocument());
  });

  it('opens the create modal when New Incident is clicked', async () => {
    api.get.mockResolvedValue(PAGE_RESPONSE([]));
    renderPage();
    await waitFor(() => screen.getByRole('button', { name: /new incident/i }));
    fireEvent.click(screen.getByRole('button', { name: /new incident/i }));
    expect(screen.getByTestId('create-modal')).toBeInTheDocument();
  });

  it('closes the create modal when onClose is called', async () => {
    api.get.mockResolvedValue(PAGE_RESPONSE([]));
    renderPage();
    await waitFor(() => screen.getByRole('button', { name: /new incident/i }));
    fireEvent.click(screen.getByRole('button', { name: /new incident/i }));
    fireEvent.click(screen.getByText('close-modal'));
    expect(screen.queryByTestId('create-modal')).not.toBeInTheDocument();
  });

  it('renders three tab buttons', async () => {
    api.get.mockResolvedValue(PAGE_RESPONSE([]));
    renderPage();
    await waitFor(() => expect(screen.getByText('My Queue')).toBeInTheDocument());
    expect(screen.getByText('Unassigned')).toBeInTheDocument();
    expect(screen.getByText('All')).toBeInTheDocument();
  });

  it('clicking My Queue tab re-fetches with tab=my_queue', async () => {
    api.get.mockResolvedValue(PAGE_RESPONSE([]));
    renderPage();
    await waitFor(() => screen.getByText('My Queue'));
    fireEvent.click(screen.getByText('My Queue'));
    await waitFor(() =>
      expect(api.get).toHaveBeenCalledWith('/api/incidents/', expect.objectContaining({
        params: expect.objectContaining({ tab: 'my_queue' }),
      }))
    );
  });

  it('clicking Unassigned tab re-fetches with tab=unassigned', async () => {
    api.get.mockResolvedValue(PAGE_RESPONSE([]));
    renderPage();
    await waitFor(() => screen.getByText('Unassigned'));
    fireEvent.click(screen.getByText('Unassigned'));
    await waitFor(() =>
      expect(api.get).toHaveBeenCalledWith('/api/incidents/', expect.objectContaining({
        params: expect.objectContaining({ tab: 'unassigned' }),
      }))
    );
  });

  it('changing severity filter re-fetches with severity param', async () => {
    api.get.mockResolvedValue(PAGE_RESPONSE([]));
    renderPage();
    await waitFor(() => screen.getByLabelText('Severity filter'));
    fireEvent.change(screen.getByLabelText('Severity filter'), { target: { value: 'critical' } });
    await waitFor(() =>
      expect(api.get).toHaveBeenCalledWith('/api/incidents/', expect.objectContaining({
        params: expect.objectContaining({ severity: 'critical' }),
      }))
    );
  });

  it('clicking a row navigates directly to the incident detail page', async () => {
    api.get.mockResolvedValue(PAGE_RESPONSE());
    renderPage();
    await waitFor(() => screen.getAllByText('INC-2026-0001'));
    fireEvent.click(screen.getAllByText('Suspicious login')[0]);
    expect(mockNavigate).toHaveBeenCalledWith('/incidents/INC-2026-0001');
  });

  it('renders pagination buttons when total_pages > 1', async () => {
    api.get.mockResolvedValue(PAGE_RESPONSE(INCIDENTS, { count: 30, total_pages: 2 }));
    renderPage();
    await waitFor(() => screen.getByText('1'));
    expect(screen.getByText('2')).toBeInTheDocument();
  });

  it('clicking a page button re-fetches with page param', async () => {
    api.get.mockResolvedValue(PAGE_RESPONSE(INCIDENTS, { count: 30, total_pages: 2 }));
    renderPage();
    await waitFor(() => screen.getByText('2'));
    fireEvent.click(screen.getByText('2'));
    await waitFor(() =>
      expect(api.get).toHaveBeenCalledWith('/api/incidents/', expect.objectContaining({
        params: expect.objectContaining({ page: '2' }),
      }))
    );
  });

  // ── multi-select state filter ─────────────────────────────────────────────

  function lastListParams() {
    const calls = api.get.mock.calls.filter(c => c[0] === '/api/incidents/');
    return calls[calls.length - 1]?.[1]?.params ?? {};
  }

  it('default state selection excludes only closed (no state param sent)', async () => {
    api.get.mockResolvedValue(PAGE_RESPONSE([]));
    renderPage('/');
    await waitFor(() => screen.getByLabelText('State filter'));
    // Fresh visit omits the state param entirely → backend excludes closed
    await waitFor(() => expect(lastListParams().state).toBeUndefined());

    fireEvent.click(screen.getByLabelText('State filter'));
    // Every non-closed state is checked; closed is not
    for (const s of ['new', 'triaged', 'in_progress', 'on_hold', 'needs_tuning', 'pending_closure', 'resolved']) {
      expect(screen.getByLabelText(s)).toBeChecked();
    }
    expect(screen.getByLabelText('closed')).not.toBeChecked();
  });

  it('exposes pending_closure as a selectable state', async () => {
    api.get.mockResolvedValue(PAGE_RESPONSE([]));
    renderPage();
    await waitFor(() => screen.getByLabelText('State filter'));
    fireEvent.click(screen.getByLabelText('State filter'));
    expect(screen.getByLabelText('pending_closure')).toBeInTheDocument();
  });

  it('toggling closed on sends an explicit state list including closed', async () => {
    api.get.mockResolvedValue(PAGE_RESPONSE([]));
    renderPage();
    await waitFor(() => screen.getByLabelText('State filter'));
    fireEvent.click(screen.getByLabelText('State filter'));
    fireEvent.click(screen.getByLabelText('closed'));
    await waitFor(() => {
      expect(lastListParams().state).toEqual(expect.stringContaining('closed'));
    });
    // All eight states selected now
    expect(lastListParams().state.split(',')).toHaveLength(8);
  });

  it('deselecting a non-closed state drops it from the state param', async () => {
    api.get.mockResolvedValue(PAGE_RESPONSE([]));
    renderPage();
    await waitFor(() => screen.getByLabelText('State filter'));
    fireEvent.click(screen.getByLabelText('State filter'));
    fireEvent.click(screen.getByLabelText('new')); // uncheck "new"
    await waitFor(() => {
      const state = lastListParams().state;
      expect(state).toBeDefined();
      expect(state.split(',')).not.toContain('new');
      expect(state.split(',')).toContain('triaged');
    });
  });

  it('restoring a saved single-state selection shows only that state checked', async () => {
    api.get.mockResolvedValue(PAGE_RESPONSE([]));
    renderPage('/incidents?state=closed');
    await waitFor(() => screen.getByLabelText('State filter'));
    fireEvent.click(screen.getByLabelText('State filter'));
    expect(screen.getByLabelText('closed')).toBeChecked();
    expect(screen.getByLabelText('new')).not.toBeChecked();
    // The lone remaining state cannot be unchecked
    expect(screen.getByLabelText('closed')).toBeDisabled();
  });

  // ── bulk actions (staff only) ─────────────────────────────────────────────

  it('selecting a checkbox renders the toolbar with correct count', async () => {
    mockUseAuth.mockReturnValue({ user: { id: 1, is_staff: true } });
    api.get.mockResolvedValue(PAGE_RESPONSE());
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => screen.getAllByText('INC-2026-0001'));
    await user.click(screen.getByLabelText('Select INC-2026-0001'));
    expect(screen.getByText('1 selected')).toBeInTheDocument();
    await user.click(screen.getByLabelText('Select INC-2026-0002'));
    expect(screen.getByText('2 selected')).toBeInTheDocument();
  });

  it('deselecting all checkboxes hides the toolbar', async () => {
    mockUseAuth.mockReturnValue({ user: { id: 1, is_staff: true } });
    api.get.mockResolvedValue(PAGE_RESPONSE());
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => screen.getAllByText('INC-2026-0001'));
    await user.click(screen.getByLabelText('Select INC-2026-0001'));
    expect(screen.getByText('1 selected')).toBeInTheDocument();
    await user.click(screen.getByLabelText('Select INC-2026-0001'));
    expect(screen.queryByText('1 selected')).not.toBeInTheDocument();
  });

  it('confirming Close calls POST /api/incidents/bulk/ with correct payload', async () => {
    mockUseAuth.mockReturnValue({ user: { id: 1, is_staff: true } });
    api.get.mockResolvedValue(PAGE_RESPONSE());
    api.post.mockResolvedValue({ data: { succeeded: [1], failed: [] } });
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => screen.getAllByText('INC-2026-0001'));
    await user.click(screen.getByLabelText('Select INC-2026-0001'));
    await user.click(screen.getByText('Close', { selector: 'button' }));
    await user.selectOptions(screen.getByLabelText('Closure reason'), 'false_positive');
    await user.click(screen.getByRole('button', { name: 'Close incidents' }));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith(
      '/api/incidents/bulk/',
      { action: 'close', ids: [1], closure_reason: 'false_positive' }
    ));
  });

  it('confirming Reassign calls POST /api/incidents/bulk/ with correct payload', async () => {
    mockUseAuth.mockReturnValue({ user: { id: 1, is_staff: true } });
    api.get.mockImplementation(url => {
      if (url === '/api/incidents/staff-users/') return Promise.resolve({ data: [{ id: 5, username: 'bob' }] });
      return Promise.resolve(PAGE_RESPONSE());
    });
    api.post.mockResolvedValue({ data: { succeeded: [1], failed: [] } });
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => screen.getAllByText('INC-2026-0001'));
    await user.click(screen.getByLabelText('Select INC-2026-0001'));
    await user.click(screen.getByRole('button', { name: 'Reassign' }));
    await waitFor(() => screen.getByLabelText('Assign to'));
    await user.selectOptions(screen.getByLabelText('Assign to'), '5');
    await user.click(screen.getByRole('button', { name: 'Confirm reassign' }));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith(
      '/api/incidents/bulk/',
      { action: 'reassign', ids: [1], assignee_id: 5 }
    ));
  });

  // ── sortable column headers ───────────────────────────────────────────────

  it('renders sortable column header buttons', async () => {
    api.get.mockResolvedValue(PAGE_RESPONSE([]));
    renderPage();
    await waitFor(() => screen.getByLabelText('Sort by Title'));
    expect(screen.getByLabelText('Sort by Severity')).toBeInTheDocument();
    expect(screen.getByLabelText('Sort by State')).toBeInTheDocument();
    expect(screen.getByLabelText('Sort by Assignee')).toBeInTheDocument();
    expect(screen.getByLabelText('Sort by Created')).toBeInTheDocument();
  });

  it('clicking a sort header re-fetches with sort and order params', async () => {
    api.get.mockResolvedValue(PAGE_RESPONSE([]));
    renderPage();
    await waitFor(() => screen.getByLabelText('Sort by Title'));
    fireEvent.click(screen.getByLabelText('Sort by Title'));
    await waitFor(() =>
      expect(api.get).toHaveBeenCalledWith('/api/incidents/', expect.objectContaining({
        params: expect.objectContaining({ sort: 'title', order: 'asc' }),
      }))
    );
  });

  it('clicking severity sort header uses desc as default direction', async () => {
    api.get.mockResolvedValue(PAGE_RESPONSE([]));
    renderPage();
    await waitFor(() => screen.getByLabelText('Sort by Severity'));
    fireEvent.click(screen.getByLabelText('Sort by Severity'));
    await waitFor(() =>
      expect(api.get).toHaveBeenCalledWith('/api/incidents/', expect.objectContaining({
        params: expect.objectContaining({ sort: 'severity', order: 'desc' }),
      }))
    );
  });

  it('clicking the same sort header again toggles the direction', async () => {
    api.get.mockResolvedValue(PAGE_RESPONSE([]));
    renderPage('/incidents?sort=title&order=asc');
    await waitFor(() => screen.getByLabelText('Sort by Title'));
    fireEvent.click(screen.getByLabelText('Sort by Title'));
    await waitFor(() =>
      expect(api.get).toHaveBeenCalledWith('/api/incidents/', expect.objectContaining({
        params: expect.objectContaining({ sort: 'title', order: 'desc' }),
      }))
    );
  });

  it('shows direction indicator on the active sort column', async () => {
    api.get.mockResolvedValue(PAGE_RESPONSE([]));
    renderPage('/incidents?sort=title&order=asc');
    await waitFor(() => screen.getByLabelText('Sort by Title'));
    expect(screen.getByLabelText('Sort by Title').textContent).toContain('▲');
  });

  it('shows descending indicator when order is desc', async () => {
    api.get.mockResolvedValue(PAGE_RESPONSE([]));
    renderPage('/incidents?sort=created_at&order=desc');
    await waitFor(() => screen.getByLabelText('Sort by Created'));
    expect(screen.getByLabelText('Sort by Created').textContent).toContain('▼');
  });

  it('sort params are preserved alongside existing filter params', async () => {
    api.get.mockResolvedValue(PAGE_RESPONSE([]));
    renderPage('/incidents?severity=high');
    await waitFor(() => screen.getByLabelText('Sort by Title'));
    fireEvent.click(screen.getByLabelText('Sort by Title'));
    await waitFor(() =>
      expect(api.get).toHaveBeenCalledWith('/api/incidents/', expect.objectContaining({
        params: expect.objectContaining({ severity: 'high', sort: 'title', order: 'asc' }),
      }))
    );
  });

});

// ── filter/sort preference storage ───────────────────────────────────────────

describe('IncidentList — preference storage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    mockUseAuth.mockReturnValue({ user: { id: 42, is_staff: false } });
    api.get.mockResolvedValue(PAGE_RESPONSE([]));
  });

  it('restores saved preferences from localStorage on mount when URL has no params', async () => {
    localStorage.setItem('incident_list_prefs_42', JSON.stringify({
      tab: 'unassigned',
      severity: 'high',
      created_within: '24h',
    }));
    renderPage('/');
    await waitFor(() =>
      expect(api.get).toHaveBeenCalledWith('/api/incidents/', expect.objectContaining({
        params: expect.objectContaining({ tab: 'unassigned', severity: 'high', created_within: '24h' }),
      }))
    );
  });

  it('does not override URL params with saved preferences when params are already present', async () => {
    localStorage.setItem('incident_list_prefs_42', JSON.stringify({
      tab: 'unassigned',
      severity: 'critical',
    }));
    renderPage('/incidents?severity=high&tab=my_queue');
    await waitFor(() =>
      expect(api.get).toHaveBeenCalledWith('/api/incidents/', expect.objectContaining({
        params: expect.objectContaining({ severity: 'high', tab: 'my_queue' }),
      }))
    );
    // Should NOT contain the saved severity=critical
    const calls = api.get.mock.calls.filter(c => c[0] === '/api/incidents/');
    const lastParams = calls[calls.length - 1]?.[1]?.params ?? {};
    expect(lastParams.severity).not.toBe('critical');
  });

  it('saves preferences to localStorage when a filter is changed', async () => {
    renderPage();
    await waitFor(() => screen.getByLabelText('Severity filter'));
    fireEvent.change(screen.getByLabelText('Severity filter'), { target: { value: 'critical' } });
    await waitFor(() => {
      const saved = JSON.parse(localStorage.getItem('incident_list_prefs_42') ?? '{}');
      expect(saved.severity).toBe('critical');
    });
  });

  it('saves preferences to localStorage when sort column is clicked', async () => {
    renderPage();
    await waitFor(() => screen.getByLabelText('Sort by Title'));
    fireEvent.click(screen.getByLabelText('Sort by Title'));
    await waitFor(() => {
      const saved = JSON.parse(localStorage.getItem('incident_list_prefs_42') ?? '{}');
      expect(saved.sort).toBe('title');
      expect(saved.order).toBe('asc');
    });
  });

  it('uses user-specific storage key', async () => {
    mockUseAuth.mockReturnValue({ user: { id: 99, is_staff: false } });
    renderPage();
    await waitFor(() => screen.getByLabelText('Severity filter'));
    fireEvent.change(screen.getByLabelText('Severity filter'), { target: { value: 'low' } });
    await waitFor(() => {
      expect(localStorage.getItem('incident_list_prefs_99')).toBeTruthy();
      expect(localStorage.getItem('incident_list_prefs_42')).toBeNull();
    });
  });

  it('defaults to my_queue tab when no saved preferences exist', async () => {
    renderPage('/');
    await waitFor(() =>
      expect(api.get).toHaveBeenCalledWith('/api/incidents/', expect.objectContaining({
        params: expect.objectContaining({ tab: 'my_queue' }),
      }))
    );
  });
});

// ── silent background poll ────────────────────────────────────────────────────
// Use a spy to capture the 30-second setInterval callback so we can fire it
// manually without fake timers (which break waitFor's internal polling).

describe('IncidentList — background poll', () => {
  let pollCb = null;

  beforeEach(() => {
    vi.clearAllMocks();
    pollCb = null;
    vi.spyOn(global, 'setInterval').mockImplementation((cb, delay) => {
      if (delay === 30000) pollCb = cb;
      return 0;
    });
    vi.spyOn(global, 'clearInterval').mockImplementation(() => {});
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('does not show Loading… while poll is in flight', async () => {
    api.get.mockResolvedValue(PAGE_RESPONSE());
    renderPage();
    await waitFor(() => screen.getAllByText('INC-2026-0001'));

    // Stall the next response so the poll hangs in flight
    api.get.mockReturnValueOnce(new Promise(() => {}));
    act(() => { pollCb(); });

    expect(screen.queryAllByText('Loading…')).toHaveLength(0);
    expect(screen.getAllByText('INC-2026-0001').length).toBeGreaterThan(0);
  });

  it('updates rows silently when poll resolves', async () => {
    // Use a default mock so both list calls (initial + default-tab effect) succeed
    api.get.mockResolvedValue(PAGE_RESPONSE([INCIDENTS[0]]));
    renderPage();
    await waitFor(() => screen.getAllByText('INC-2026-0001'));
    expect(screen.queryAllByText('INC-2026-0002')).toHaveLength(0);

    api.get.mockResolvedValueOnce(PAGE_RESPONSE(INCIDENTS));
    await act(async () => { pollCb(); });

    await waitFor(() => screen.getAllByText('INC-2026-0002'));
  });

  it('failed poll does not overwrite loaded data with an error message', async () => {
    api.get.mockResolvedValue(PAGE_RESPONSE());
    renderPage();
    await waitFor(() => screen.getAllByText('INC-2026-0001'));

    api.get.mockRejectedValueOnce({ response: { data: { detail: 'Poll failure.' } } });
    await act(async () => { pollCb(); });

    expect(screen.queryByText('Poll failure.')).not.toBeInTheDocument();
    expect(screen.getAllByText('INC-2026-0001').length).toBeGreaterThan(0);
  });
});
