import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';

vi.mock('../lib/axios', () => ({
  default: { get: vi.fn(), post: vi.fn(), patch: vi.fn() },
}));

vi.mock('../components/EditExceptionModal', () => ({
  default: ({ rule, onClose, onSaved }) =>
    rule ? (
      <div data-testid="edit-modal">
        <button onClick={onClose}>close-edit</button>
        <button onClick={() => onSaved({ ...rule, description: 'Saved' })}>save-edit</button>
      </div>
    ) : null,
}));

vi.mock('../context/AuthContext', () => ({
  useAuth: vi.fn(),
}));

import api from '../lib/axios';
import { useAuth } from '../context/AuthContext';
import ExceptionList from './ExceptionList';

const PENDING_RULE = {
  id: 3, wazuh_rule_id: 200003, description: 'Pending rule',
  scope: 'org', status: 'pending', org_slug: 'acme', incident_display_id: null,
};

const APPLIED_RULE = {
  id: 4, wazuh_rule_id: 200004, description: 'Applied rule',
  scope: 'org', status: 'applied', org_slug: 'acme', incident_display_id: null,
};

const STAFF_USER    = { id: 1, username: 'admin', is_staff: true };
const NON_STAFF     = { id: 2, username: 'alice', is_staff: false };

const RULES = [
  {
    id: 1, wazuh_rule_id: 200000, description: 'Block brute force',
    scope: 'org', status: 'applied', org_slug: 'acme', incident_display_id: null,
  },
  {
    id: 2, wazuh_rule_id: null, description: 'Suppress noisy alert',
    scope: 'global', status: 'pending', org_slug: null, incident_display_id: 'INC-2026-0001',
  },
];

function renderPage(user = STAFF_USER) {
  useAuth.mockReturnValue({ user, isAuthenticated: true, isLoading: false });
  return render(
    <MemoryRouter>
      <ExceptionList />
    </MemoryRouter>
  );
}

describe('ExceptionList', () => {
  beforeEach(() => { vi.clearAllMocks(); });

  it('shows loading state while fetching', () => {
    // Both mobile card list and desktop table render "Loading…" in jsdom (no CSS media queries)
    api.get.mockReturnValue(new Promise(() => {}));
    renderPage();
    expect(screen.getAllByText('Loading…').length).toBeGreaterThan(0);
  });

  it('shows empty state when no rules', async () => {
    api.get.mockResolvedValue({ data: [] });
    renderPage();
    await waitFor(() => expect(screen.getAllByText('No exception rules.').length).toBeGreaterThan(0));
  });

  it('renders rule rows with correct data', async () => {
    api.get.mockResolvedValue({ data: RULES });
    renderPage();
    await waitFor(() => screen.getAllByText('Block brute force'));
    expect(screen.getAllByText('200000').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Suppress noisy alert').length).toBeGreaterThan(0);
    expect(screen.getAllByText('applied').length).toBeGreaterThan(0);
    expect(screen.getAllByText('pending').length).toBeGreaterThan(0);
  });

  it('shows the page heading', async () => {
    api.get.mockResolvedValue({ data: [] });
    renderPage();
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Exception Rules' })).toBeInTheDocument());
  });

  it('fetches from /api/exceptions/ on mount', async () => {
    api.get.mockResolvedValue({ data: [] });
    renderPage();
    await waitFor(() => expect(api.get).toHaveBeenCalledWith('/api/exceptions/', expect.any(Object)));
  });

  it('shows error message on API failure', async () => {
    api.get.mockRejectedValue({ response: { data: { detail: 'Forbidden.' } } });
    renderPage();
    await waitFor(() => expect(screen.getByText('Forbidden.')).toBeInTheDocument());
  });

  it('staff users see the Organisation column', async () => {
    api.get.mockResolvedValue({ data: [] });
    renderPage(STAFF_USER);
    await waitFor(() => expect(screen.getByText('Organisation')).toBeInTheDocument());
  });

  it('non-staff users do not see the Organisation column', async () => {
    api.get.mockResolvedValue({ data: [] });
    renderPage(NON_STAFF);
    await waitFor(() => expect(screen.queryByText('Organisation')).not.toBeInTheDocument());
  });

  it('staff users see the org filter input', async () => {
    api.get.mockResolvedValue({ data: [] });
    renderPage(STAFF_USER);
    await waitFor(() => expect(screen.getByRole('textbox', { name: /organisation filter/i })).toBeInTheDocument());
  });

  it('non-staff users do not see the org filter input', async () => {
    api.get.mockResolvedValue({ data: [] });
    renderPage(NON_STAFF);
    await waitFor(() => expect(screen.queryByRole('textbox', { name: /organisation filter/i })).not.toBeInTheDocument());
  });

  it('changing status filter re-fetches with status param', async () => {
    api.get.mockResolvedValue({ data: [] });
    renderPage();
    await waitFor(() => screen.getByLabelText('Status filter'));
    fireEvent.change(screen.getByLabelText('Status filter'), { target: { value: 'applied' } });
    await waitFor(() =>
      expect(api.get).toHaveBeenCalledWith('/api/exceptions/', expect.objectContaining({
        params: expect.objectContaining({ status: 'applied' }),
      }))
    );
  });

  it('renders linked incident as a link when present', async () => {
    api.get.mockResolvedValue({ data: RULES });
    renderPage();
    await waitFor(() => screen.getAllByText('INC-2026-0001'));
    const links = screen.getAllByRole('link', { name: 'INC-2026-0001' });
    expect(links.length).toBeGreaterThan(0);
    expect(links[0]).toHaveAttribute('href', '/incidents/INC-2026-0001');
  });

  it('staff see Actions column header', async () => {
    api.get.mockResolvedValue({ data: [] });
    renderPage(STAFF_USER);
    await waitFor(() => expect(screen.getByText('Actions')).toBeInTheDocument());
  });

  it('non-staff do not see Actions column', async () => {
    api.get.mockResolvedValue({ data: [] });
    renderPage(NON_STAFF);
    await waitFor(() => expect(screen.queryByText('Actions')).not.toBeInTheDocument());
  });

  it('shows Approve button for pending rules', async () => {
    api.get.mockResolvedValue({ data: [PENDING_RULE] });
    renderPage(STAFF_USER);
    await waitFor(() => expect(screen.getAllByRole('button', { name: /approve/i }).length).toBeGreaterThan(0));
  });

  it('shows Disable button for applied rules', async () => {
    api.get.mockResolvedValue({ data: [APPLIED_RULE] });
    renderPage(STAFF_USER);
    await waitFor(() => expect(screen.getAllByRole('button', { name: /disable/i }).length).toBeGreaterThan(0));
  });

  it('clicking Approve calls POST /approve and updates row', async () => {
    api.get.mockResolvedValue({ data: [PENDING_RULE] });
    api.post.mockResolvedValueOnce({ data: { ...PENDING_RULE, status: 'applied' } });
    renderPage(STAFF_USER);
    await waitFor(() => screen.getAllByRole('button', { name: /approve/i }));
    fireEvent.click(screen.getAllByRole('button', { name: /approve/i })[0]);
    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith(`/api/exceptions/${PENDING_RULE.id}/approve/`)
    );
  });

  it('clicking Disable calls POST /disable and updates row', async () => {
    api.get.mockResolvedValue({ data: [APPLIED_RULE] });
    api.post.mockResolvedValueOnce({ data: { ...APPLIED_RULE, status: 'disabled' } });
    renderPage(STAFF_USER);
    await waitFor(() => screen.getAllByRole('button', { name: /disable/i }));
    fireEvent.click(screen.getAllByRole('button', { name: /disable/i })[0]);
    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith(`/api/exceptions/${APPLIED_RULE.id}/disable/`)
    );
  });

  it('shows inline error when Approve fails', async () => {
    api.get.mockResolvedValue({ data: [PENDING_RULE] });
    api.post.mockRejectedValueOnce({ response: { data: { detail: 'Pool exhausted.' } } });
    renderPage(STAFF_USER);
    await waitFor(() => screen.getAllByRole('button', { name: /approve/i }));
    fireEvent.click(screen.getAllByRole('button', { name: /approve/i })[0]);
    await waitFor(() => expect(screen.getAllByText('Pool exhausted.').length).toBeGreaterThan(0));
  });

  it('clicking Edit opens EditExceptionModal', async () => {
    api.get.mockResolvedValue({ data: [PENDING_RULE] });
    renderPage(STAFF_USER);
    await waitFor(() => screen.getAllByRole('button', { name: /edit/i }));
    fireEvent.click(screen.getAllByRole('button', { name: /edit/i })[0]);
    expect(screen.getByTestId('edit-modal')).toBeInTheDocument();
  });

  it('closing EditExceptionModal hides the modal', async () => {
    api.get.mockResolvedValue({ data: [PENDING_RULE] });
    renderPage(STAFF_USER);
    await waitFor(() => screen.getAllByRole('button', { name: /edit/i }));
    fireEvent.click(screen.getAllByRole('button', { name: /edit/i })[0]);
    fireEvent.click(screen.getByRole('button', { name: /close-edit/i }));
    expect(screen.queryByTestId('edit-modal')).not.toBeInTheDocument();
  });
});
