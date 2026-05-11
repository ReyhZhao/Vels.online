import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';

vi.mock('../lib/axios', () => ({
  default: { get: vi.fn() },
}));

vi.mock('../context/AuthContext', () => ({
  useAuth: vi.fn(),
}));

import api from '../lib/axios';
import { useAuth } from '../context/AuthContext';
import ExceptionList from './ExceptionList';

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
    api.get.mockReturnValue(new Promise(() => {}));
    renderPage();
    expect(screen.getByText('Loading…')).toBeInTheDocument();
  });

  it('shows empty state when no rules', async () => {
    api.get.mockResolvedValue({ data: [] });
    renderPage();
    await waitFor(() => expect(screen.getByText('No exception rules.')).toBeInTheDocument());
  });

  it('renders rule rows with correct data', async () => {
    api.get.mockResolvedValue({ data: RULES });
    renderPage();
    await waitFor(() => screen.getByText('Block brute force'));
    expect(screen.getByText('200000')).toBeInTheDocument();
    expect(screen.getByText('Suppress noisy alert')).toBeInTheDocument();
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
    await waitFor(() => screen.getByText('INC-2026-0001'));
    expect(screen.getByRole('link', { name: 'INC-2026-0001' })).toHaveAttribute('href', '/incidents/INC-2026-0001');
  });
});
