import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

vi.mock('../lib/axios', () => ({
  default: { get: vi.fn(), post: vi.fn(), patch: vi.fn() },
}));

const mockUseAuth = vi.fn(() => ({ user: { id: 1, username: 'alice', is_staff: false }, isAuthenticated: true, isLoading: false }));
vi.mock('../context/AuthContext', () => ({ useAuth: () => mockUseAuth() }));

import api from '../lib/axios';
import IncidentDetail from './IncidentDetail';

const INCIDENT = {
  id: 1,
  display_id: 'INC-2026-0001',
  title: 'Suspicious login attempt',
  description: 'Multiple failed logins from unusual IP.',
  severity: 'high',
  tlp: 'amber',
  pap: 'amber',
  state: 'new',
  closure_reason: null,
  subject: null,
  subject_slug: null,
  subject_name: null,
  org_slug: 'acme',
  source_kind: 'manual',
  source_ref: {},
  assignee: null,
  assignee_username: null,
  active_delegations: [],
  created_by: 1,
  created_by_username: 'alice',
  created_at: '2026-01-15T10:00:00Z',
  updated_at: '2026-01-15T10:00:00Z',
};

const SUBJECTS = [
  { id: 1, name: 'Phishing', slug: 'phishing', description: '', archived: false },
  { id: 2, name: 'Malware', slug: 'malware', description: '', archived: false },
];

const EMPTY_TIMELINE = { count: 0, page: 1, page_size: 50, results: [] };

function mockGet(incident = INCIDENT, subjects = SUBJECTS) {
  api.get.mockImplementation(url => {
    if (url === '/api/subjects/') return Promise.resolve({ data: subjects });
    if (url.endsWith('/tasks/')) return Promise.resolve({ data: [] });
    if (url.endsWith('/comments/')) return Promise.resolve({ data: [] });
    if (url.includes('/timeline/')) return Promise.resolve({ data: EMPTY_TIMELINE });
    if (url.endsWith('/attachments/')) return Promise.resolve({ data: [] });
    return Promise.resolve({ data: incident });
  });
}

function renderPage(id = 'INC-2026-0001') {
  return render(
    <MemoryRouter initialEntries={[`/incidents/${id}`]}>
      <Routes>
        <Route path="/incidents/:displayId" element={<IncidentDetail />} />
      </Routes>
    </MemoryRouter>
  );
}

const STAFF_USERS = [
  { id: 2, username: 'bob' },
  { id: 3, username: 'carol' },
];

describe('IncidentDetail', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuth.mockReturnValue({ user: { id: 1, username: 'alice', is_staff: false }, isAuthenticated: true, isLoading: false });
  });

  it('shows loading state while fetching', () => {
    api.get.mockReturnValue(new Promise(() => {}));
    renderPage();
    expect(screen.getByText('Loading…')).toBeInTheDocument();
  });

  it('renders incident header', async () => {
    mockGet();
    renderPage();
    await waitFor(() => screen.getByText('INC-2026-0001'));
    expect(screen.getByText('Suspicious login attempt')).toBeInTheDocument();
  });

  it('renders severity, TLP, and PAP as editable selects', async () => {
    mockGet();
    renderPage();
    await waitFor(() => screen.getByLabelText('Severity'));
    expect(screen.getByLabelText('Severity')).toHaveValue('high');
    expect(screen.getByLabelText('TLP')).toHaveValue('amber');
    expect(screen.getByLabelText('PAP')).toHaveValue('amber');
  });

  it('renders description', async () => {
    mockGet();
    renderPage();
    await waitFor(() => screen.getByText('Multiple failed logins from unusual IP.'));
  });

  it('shows not found message on 404', async () => {
    api.get.mockRejectedValue({ response: { status: 404 } });
    renderPage();
    await waitFor(() => screen.getByText('Incident not found.'));
  });

  it('shows back link to incidents list', async () => {
    mockGet();
    renderPage();
    await waitFor(() => screen.getByText('← Incidents'));
  });

  it('fetches the correct incident by display id', async () => {
    mockGet();
    renderPage('INC-2026-0042');
    await waitFor(() => expect(api.get).toHaveBeenCalledWith('/api/incidents/INC-2026-0042/'));
  });

  // ── state transition controls ─────────────────────────────────────────────

  it('shows legal next-state actions for new incident', async () => {
    mockGet();
    renderPage();
    await waitFor(() => screen.getByText('Triage'));
    expect(screen.getByText('Start work')).toBeInTheDocument();
  });

  it('shows reopen action for closed incident', async () => {
    mockGet({ ...INCIDENT, state: 'closed', closure_reason: 'resolved' });
    renderPage();
    await waitFor(() => screen.getByText('Reopen'));
  });

  it('calls transition API when action button clicked', async () => {
    mockGet();
    api.post.mockResolvedValue({ data: { ...INCIDENT, state: 'triaged' } });
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => screen.getByText('Triage'));
    await user.click(screen.getByRole('button', { name: 'Triage' }));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith(
      '/api/incidents/INC-2026-0001/transition/',
      { state: 'triaged' }
    ));
  });

  it('shows closure reason dialog when Close is clicked', async () => {
    mockGet({ ...INCIDENT, state: 'in_progress' });
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => screen.getByText('Close'));
    await user.click(screen.getByRole('button', { name: 'Close' }));
    expect(screen.getByRole('heading', { name: 'Close incident' })).toBeInTheDocument();
    expect(screen.getByLabelText('Closure reason')).toBeInTheDocument();
  });

  it('submits closure reason when closing', async () => {
    mockGet({ ...INCIDENT, state: 'in_progress' });
    api.post.mockResolvedValue({ data: { ...INCIDENT, state: 'closed', closure_reason: 'resolved' } });
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => screen.getByText('Close'));
    await user.click(screen.getByRole('button', { name: 'Close' }));
    await user.selectOptions(screen.getByLabelText('Closure reason'), 'resolved');
    await user.click(screen.getByRole('button', { name: 'Close incident' }));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith(
      '/api/incidents/INC-2026-0001/transition/',
      { state: 'closed', closure_reason: 'resolved' }
    ));
  });

  it('cancels closure dialog without calling API', async () => {
    mockGet({ ...INCIDENT, state: 'in_progress' });
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => screen.getByText('Close'));
    await user.click(screen.getByRole('button', { name: 'Close' }));
    await user.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(api.post).not.toHaveBeenCalled();
    expect(screen.queryByText('Close incident')).not.toBeInTheDocument();
  });

  it('shows transition error on failure', async () => {
    mockGet();
    api.post.mockRejectedValue({ response: { data: { detail: 'Invalid transition.' } } });
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => screen.getByText('Triage'));
    await user.click(screen.getByRole('button', { name: 'Triage' }));
    await waitFor(() => screen.getByText('Invalid transition.'));
  });

  // ── subject dropdown ──────────────────────────────────────────────────────

  it('renders subject dropdown', async () => {
    mockGet();
    renderPage();
    await waitFor(() => screen.getByLabelText('Subject'));
    expect(screen.getByLabelText('Subject')).not.toBeDisabled();
  });

  it('subject dropdown is disabled when state is past triage', async () => {
    mockGet({ ...INCIDENT, state: 'in_progress' });
    renderPage();
    await waitFor(() => screen.getByLabelText('Subject'));
    expect(screen.getByLabelText('Subject')).toBeDisabled();
  });

  it('subject dropdown lists active subjects', async () => {
    mockGet();
    renderPage();
    await waitFor(() => screen.getByLabelText('Subject'));
    expect(screen.getByRole('option', { name: 'Phishing' })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: 'Malware' })).toBeInTheDocument();
  });

  it('calls patch when subject is selected', async () => {
    mockGet();
    api.patch.mockResolvedValue({ data: { ...INCIDENT, subject: 1, subject_slug: 'phishing', subject_name: 'Phishing' } });
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => screen.getByLabelText('Subject'));
    await user.selectOptions(screen.getByLabelText('Subject'), '1');
    await waitFor(() => expect(api.patch).toHaveBeenCalledWith('/api/incidents/INC-2026-0001/', { subject: 1 }));
  });

  // ── transfer ──────────────────────────────────────────────────────────────

  it('does not show Transfer button for non-staff users', async () => {
    mockGet();
    renderPage();
    await waitFor(() => screen.getByText('INC-2026-0001'));
    expect(screen.queryByRole('button', { name: 'Transfer' })).not.toBeInTheDocument();
  });

  it('shows Transfer button for staff users', async () => {
    mockUseAuth.mockReturnValue({ user: { id: 1, username: 'alice', is_staff: true }, isAuthenticated: true, isLoading: false });
    mockGet();
    renderPage();
    await waitFor(() => screen.getByRole('button', { name: 'Transfer' }));
  });

  it('opens transfer dialog with staff users when Transfer is clicked', async () => {
    mockUseAuth.mockReturnValue({ user: { id: 1, username: 'alice', is_staff: true }, isAuthenticated: true, isLoading: false });
    mockGet();
    api.get.mockImplementation(url => {
      if (url === '/api/incidents/staff-users/') return Promise.resolve({ data: STAFF_USERS });
      if (url === '/api/subjects/') return Promise.resolve({ data: SUBJECTS });
      if (url.endsWith('/tasks/')) return Promise.resolve({ data: [] });
      if (url.endsWith('/comments/')) return Promise.resolve({ data: [] });
      if (url.includes('/timeline/')) return Promise.resolve({ data: EMPTY_TIMELINE });
      if (url.endsWith('/attachments/')) return Promise.resolve({ data: [] });
      return Promise.resolve({ data: INCIDENT });
    });
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => screen.getByRole('button', { name: 'Transfer' }));
    await user.click(screen.getByRole('button', { name: 'Transfer' }));
    await waitFor(() => screen.getByRole('heading', { name: 'Transfer incident' }));
    expect(screen.getByRole('option', { name: 'bob' })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: 'carol' })).toBeInTheDocument();
  });

  it('calls transfer API with selected user and updates incident', async () => {
    mockUseAuth.mockReturnValue({ user: { id: 1, username: 'alice', is_staff: true }, isAuthenticated: true, isLoading: false });
    const TRANSFERRED = { ...INCIDENT, assignee: 2, assignee_username: 'bob' };
    api.get.mockImplementation(url => {
      if (url === '/api/incidents/staff-users/') return Promise.resolve({ data: STAFF_USERS });
      if (url === '/api/subjects/') return Promise.resolve({ data: SUBJECTS });
      if (url.endsWith('/tasks/')) return Promise.resolve({ data: [] });
      if (url.endsWith('/comments/')) return Promise.resolve({ data: [] });
      if (url.includes('/timeline/')) return Promise.resolve({ data: EMPTY_TIMELINE });
      if (url.endsWith('/attachments/')) return Promise.resolve({ data: [] });
      return Promise.resolve({ data: INCIDENT });
    });
    api.post.mockResolvedValue({ data: TRANSFERRED });
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => screen.getByRole('button', { name: 'Transfer' }));
    await user.click(screen.getByRole('button', { name: 'Transfer' }));
    await waitFor(() => screen.getByRole('heading', { name: 'Transfer incident' }));
    await user.selectOptions(screen.getByLabelText('New assignee'), '2');
    await user.click(screen.getByRole('button', { name: 'Confirm transfer' }));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/api/incidents/INC-2026-0001/transfer/', { assignee_id: 2 }));
  });

  it('cancels transfer dialog without calling API', async () => {
    mockUseAuth.mockReturnValue({ user: { id: 1, username: 'alice', is_staff: true }, isAuthenticated: true, isLoading: false });
    api.get.mockImplementation(url => {
      if (url === '/api/incidents/staff-users/') return Promise.resolve({ data: STAFF_USERS });
      if (url === '/api/subjects/') return Promise.resolve({ data: SUBJECTS });
      if (url.endsWith('/tasks/')) return Promise.resolve({ data: [] });
      if (url.endsWith('/comments/')) return Promise.resolve({ data: [] });
      if (url.includes('/timeline/')) return Promise.resolve({ data: EMPTY_TIMELINE });
      if (url.endsWith('/attachments/')) return Promise.resolve({ data: [] });
      return Promise.resolve({ data: INCIDENT });
    });
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => screen.getByRole('button', { name: 'Transfer' }));
    await user.click(screen.getByRole('button', { name: 'Transfer' }));
    await waitFor(() => screen.getByRole('heading', { name: 'Transfer incident' }));
    await user.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(api.post).not.toHaveBeenCalled();
    expect(screen.queryByRole('heading', { name: 'Transfer incident' })).not.toBeInTheDocument();
  });

  // ── tabs ──────────────────────────────────────────────────────────────────

  it('renders Timeline, Attachments, and Tasks tab buttons', async () => {
    mockGet();
    renderPage();
    await waitFor(() => screen.getByText('INC-2026-0001'));
    expect(screen.getByRole('button', { name: 'Timeline' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Attachments' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Tasks' })).toBeInTheDocument();
  });

  it('shows Timeline content by default', async () => {
    mockGet();
    renderPage();
    await waitFor(() => screen.getByRole('button', { name: 'Timeline' }));
    // Timeline tab is active; attachments and tasks are not rendered
    expect(screen.queryByRole('button', { name: 'Tasks' })).toBeInTheDocument();
    // The timeline tab button should carry the active style (primary text)
    const timelineBtn = screen.getByRole('button', { name: 'Timeline' });
    expect(timelineBtn.className).toMatch(/text-primary/);
  });

  it('switching to Tasks tab does not navigate', async () => {
    mockGet();
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => screen.getByRole('button', { name: 'Tasks' }));
    await user.click(screen.getByRole('button', { name: 'Tasks' }));
    // Still on the same page — title still visible
    expect(screen.getByText('Suspicious login attempt')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Tasks' }).className).toMatch(/text-primary/);
  });

  // ── inline badge editing ──────────────────────────────────────────────────

  it('PATCHes incident when severity is changed', async () => {
    mockGet();
    api.patch.mockResolvedValue({ data: { ...INCIDENT, severity: 'critical' } });
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => screen.getByLabelText('Severity'));
    await user.selectOptions(screen.getByLabelText('Severity'), 'critical');
    await waitFor(() => expect(api.patch).toHaveBeenCalledWith(
      '/api/incidents/INC-2026-0001/',
      { severity: 'critical' }
    ));
  });

  it('PATCHes incident when TLP is changed', async () => {
    mockGet();
    api.patch.mockResolvedValue({ data: { ...INCIDENT, tlp: 'green' } });
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => screen.getByLabelText('TLP'));
    await user.selectOptions(screen.getByLabelText('TLP'), 'green');
    await waitFor(() => expect(api.patch).toHaveBeenCalledWith(
      '/api/incidents/INC-2026-0001/',
      { tlp: 'green' }
    ));
  });

  it('PATCHes incident when PAP is changed', async () => {
    mockGet();
    api.patch.mockResolvedValue({ data: { ...INCIDENT, pap: 'red' } });
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => screen.getByLabelText('PAP'));
    await user.selectOptions(screen.getByLabelText('PAP'), 'red');
    await waitFor(() => expect(api.patch).toHaveBeenCalledWith(
      '/api/incidents/INC-2026-0001/',
      { pap: 'red' }
    ));
  });

  it('shows inline error when badge PATCH fails', async () => {
    mockGet();
    api.patch.mockRejectedValue({ response: { data: { detail: 'Permission denied.' } } });
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => screen.getByLabelText('Severity'));
    await user.selectOptions(screen.getByLabelText('Severity'), 'critical');
    await waitFor(() => screen.getByText('Permission denied.'));
  });

  // ── description / comments split ─────────────────────────────────────────

  it('renders description in the split layout', async () => {
    mockGet();
    renderPage();
    await waitFor(() => screen.getByText('Multiple failed logins from unusual IP.'));
  });
});
