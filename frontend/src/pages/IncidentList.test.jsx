import { render, screen, waitFor, act, fireEvent } from '@testing-library/react';
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
  });

  it('shows loading state while fetching', () => {
    api.get.mockReturnValue(new Promise(() => {}));
    renderPage();
    expect(screen.getByText('Loading…')).toBeInTheDocument();
  });

  it('shows empty state when no incidents', async () => {
    api.get.mockResolvedValue(PAGE_RESPONSE([]));
    renderPage();
    await waitFor(() => expect(screen.getByText('No incidents.')).toBeInTheDocument());
  });

  it('renders incident rows with correct data', async () => {
    api.get.mockResolvedValue(PAGE_RESPONSE());
    renderPage();
    await waitFor(() => screen.getByText('INC-2026-0001'));
    expect(screen.getByText('Suspicious login')).toBeInTheDocument();
    expect(screen.getByText('INC-2026-0002')).toBeInTheDocument();
    expect(screen.getByText('Malware detected')).toBeInTheDocument();
    expect(screen.getAllByText('high').length).toBeGreaterThan(0);
    expect(screen.getAllByText('critical').length).toBeGreaterThan(0);
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

  it('clicking a row opens the slide-over preview', async () => {
    api.get
      .mockResolvedValueOnce(PAGE_RESPONSE())
      .mockResolvedValueOnce({ data: INCIDENTS[0] });
    renderPage();
    await waitFor(() => screen.getByText('INC-2026-0001'));
    fireEvent.click(screen.getByText('Suspicious login'));
    await waitFor(() =>
      expect(api.get).toHaveBeenCalledWith('/api/incidents/INC-2026-0001/')
    );
  });

  it('renders markdown in slide-over description', async () => {
    api.get
      .mockResolvedValueOnce(PAGE_RESPONSE())
      .mockResolvedValueOnce({ data: { ...INCIDENTS[0], description: '**bold text**' } });
    renderPage();
    await waitFor(() => screen.getByText('INC-2026-0001'));
    fireEvent.click(screen.getByText('Suspicious login'));
    await waitFor(() => expect(screen.getByText('bold text')).toBeInTheDocument());
    expect(screen.getByText('bold text').tagName).toBe('STRONG');
  });

  it('does not render description section when description is empty', async () => {
    api.get
      .mockResolvedValueOnce(PAGE_RESPONSE())
      .mockResolvedValueOnce({ data: { ...INCIDENTS[0], description: '' } });
    renderPage();
    await waitFor(() => screen.getByText('INC-2026-0001'));
    fireEvent.click(screen.getByText('Suspicious login'));
    await waitFor(() => expect(api.get).toHaveBeenCalledWith('/api/incidents/INC-2026-0001/'));
    expect(screen.queryByRole('article')).not.toBeInTheDocument();
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

  // ── bulk actions (staff only) ─────────────────────────────────────────────

  it('selecting a checkbox renders the toolbar with correct count', async () => {
    mockUseAuth.mockReturnValue({ user: { id: 1, is_staff: true } });
    api.get.mockResolvedValue(PAGE_RESPONSE());
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => screen.getByText('INC-2026-0001'));
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
    await waitFor(() => screen.getByText('INC-2026-0001'));
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
    await waitFor(() => screen.getByText('INC-2026-0001'));
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
    await waitFor(() => screen.getByText('INC-2026-0001'));
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
    await waitFor(() => screen.getByText('INC-2026-0001'));

    // Stall the next response so the poll hangs in flight
    api.get.mockReturnValueOnce(new Promise(() => {}));
    act(() => { pollCb(); });

    expect(screen.queryByText('Loading…')).not.toBeInTheDocument();
    expect(screen.getByText('INC-2026-0001')).toBeInTheDocument();
  });

  it('updates rows silently when poll resolves', async () => {
    api.get.mockResolvedValueOnce(PAGE_RESPONSE([INCIDENTS[0]]));
    renderPage();
    await waitFor(() => screen.getByText('INC-2026-0001'));
    expect(screen.queryByText('INC-2026-0002')).not.toBeInTheDocument();

    api.get.mockResolvedValueOnce(PAGE_RESPONSE(INCIDENTS));
    await act(async () => { pollCb(); });

    await waitFor(() => screen.getByText('INC-2026-0002'));
  });

  it('failed poll does not overwrite loaded data with an error message', async () => {
    api.get.mockResolvedValue(PAGE_RESPONSE());
    renderPage();
    await waitFor(() => screen.getByText('INC-2026-0001'));

    api.get.mockRejectedValueOnce({ response: { data: { detail: 'Poll failure.' } } });
    await act(async () => { pollCb(); });

    expect(screen.queryByText('Poll failure.')).not.toBeInTheDocument();
    expect(screen.getByText('INC-2026-0001')).toBeInTheDocument();
  });
});
