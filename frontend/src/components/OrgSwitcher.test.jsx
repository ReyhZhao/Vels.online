import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';

vi.mock('../lib/axios', () => ({
  default: { get: vi.fn() },
}));

import api from '../lib/axios';
import { AuthContext } from '../context/AuthContext';
import { OrgProvider } from '../context/OrgContext';
import OrgSwitcher from './OrgSwitcher';

const ORGS = [
  { id: 1, name: 'Acme', slug: 'acme', wazuh_group: 'acme' },
  { id: 2, name: 'Contoso', slug: 'contoso', wazuh_group: 'contoso' },
];

function renderSwitcher(orgs, { isAdmin = false, route = '/' } = {}) {
  api.get.mockResolvedValue({ data: orgs });
  return render(
    <MemoryRouter initialEntries={[route]}>
      <AuthContext.Provider value={{ user: { is_staff: isAdmin }, isAuthenticated: true, isLoading: false }}>
        <OrgProvider>
          <OrgSwitcher />
        </OrgProvider>
      </AuthContext.Provider>
    </MemoryRouter>
  );
}

describe('OrgSwitcher', () => {
  beforeEach(() => vi.clearAllMocks());

  it('renders all orgs for an admin user', async () => {
    renderSwitcher(ORGS, { isAdmin: true });

    await waitFor(() => expect(screen.getByRole('combobox')).toBeInTheDocument());

    const options = screen.getAllByRole('option');
    expect(options).toHaveLength(2);
    expect(options[0]).toHaveTextContent('Acme');
    expect(options[1]).toHaveTextContent('Contoso');
  });

  it('renders orgs for a non-admin user with multiple orgs', async () => {
    renderSwitcher(ORGS, { isAdmin: false });

    await waitFor(() => expect(screen.getByRole('combobox')).toBeInTheDocument());

    expect(screen.getAllByRole('option')).toHaveLength(2);
  });

  it('is hidden when a non-admin user has only one org', async () => {
    renderSwitcher([ORGS[0]], { isAdmin: false });

    await waitFor(() => expect(api.get).toHaveBeenCalled());

    expect(screen.queryByRole('combobox')).not.toBeInTheDocument();
  });

  it('is shown when an admin user has only one org', async () => {
    renderSwitcher([ORGS[0]], { isAdmin: true });

    await waitFor(() => expect(screen.getByRole('combobox')).toBeInTheDocument());
  });

  it('offers an "All organisations" option to staff on the dashboard only', async () => {
    renderSwitcher(ORGS, { isAdmin: true, route: '/dashboard' });
    await waitFor(() => expect(screen.getByRole('combobox')).toBeInTheDocument());
    const options = screen.getAllByRole('option');
    expect(options).toHaveLength(3);
    expect(options[0]).toHaveTextContent('All organisations');
    expect(options[0]).toHaveValue('__all__');
  });

  it('does not offer "All organisations" off the dashboard', async () => {
    renderSwitcher(ORGS, { isAdmin: true, route: '/incidents' });
    await waitFor(() => expect(screen.getByRole('combobox')).toBeInTheDocument());
    expect(screen.getAllByRole('option')).toHaveLength(2);
    expect(screen.queryByText('All organisations')).not.toBeInTheDocument();
  });

  it('does not offer "All organisations" to non-staff on the dashboard', async () => {
    renderSwitcher(ORGS, { isAdmin: false, route: '/dashboard' });
    await waitFor(() => expect(screen.getByRole('combobox')).toBeInTheDocument());
    expect(screen.getAllByRole('option')).toHaveLength(2);
  });

  it('selecting a different org updates the selected value', async () => {
    const user = userEvent.setup();
    renderSwitcher(ORGS, { isAdmin: false });

    await waitFor(() => expect(screen.getByRole('combobox')).toBeInTheDocument());
    expect(screen.getByRole('combobox')).toHaveValue('acme');

    await user.selectOptions(screen.getByRole('combobox'), 'contoso');

    expect(screen.getByRole('combobox')).toHaveValue('contoso');
  });
});
