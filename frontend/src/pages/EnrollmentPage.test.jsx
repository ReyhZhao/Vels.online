import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';

vi.mock('../lib/axios', () => ({
  default: { get: vi.fn() },
}));

import api from '../lib/axios';
import { OrgContext } from '../context/OrgContext';
import EnrollmentPage from './EnrollmentPage';

const SELECTED_ORG = { id: 1, name: 'Acme Corp', slug: 'acme', wazuh_group: 'acme' };

const ENROLLMENT = {
  wazuh_group: 'acme',
  manager_host: 'wazuh.example.com',
  install_command:
    "WAZUH_MANAGER='wazuh.example.com' WAZUH_AGENT_GROUP='acme' apt-get install -y wazuh-agent && systemctl daemon-reload && systemctl enable --now wazuh-agent",
};

function renderPage(selectedOrg = SELECTED_ORG) {
  return render(
    <MemoryRouter>
      <OrgContext.Provider
        value={{
          orgs: [SELECTED_ORG],
          selectedOrg,
          setSelectedOrg: vi.fn(),
          isLoading: false,
        }}
      >
        <EnrollmentPage />
      </OrgContext.Provider>
    </MemoryRouter>
  );
}

describe('EnrollmentPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.get.mockResolvedValue({ data: ENROLLMENT });
  });

  it('renders install command containing the org group name', async () => {
    renderPage();

    await waitFor(() =>
      expect(screen.getByTestId('install-command')).toBeInTheDocument()
    );

    const cmd = screen.getByTestId('install-command').textContent;
    expect(cmd).toContain('acme');
    expect(cmd).toContain('wazuh.example.com');
  });

  it('shows the org name in the description', async () => {
    renderPage();

    await waitFor(() => expect(screen.getByText('Acme Corp')).toBeInTheDocument());
  });

  it('copy button is present', async () => {
    renderPage();

    await waitFor(() =>
      expect(screen.getByRole('button', { name: /copy/i })).toBeInTheDocument()
    );
  });

  it('copy button shows Copied! feedback after click', async () => {
    // jsdom does not implement clipboard API; provide a minimal stub
    navigator.clipboard = { writeText: vi.fn().mockResolvedValue(undefined) };

    const user = userEvent.setup();
    renderPage();

    await waitFor(() => expect(screen.getByRole('button', { name: /copy/i })).toBeInTheDocument());
    await user.click(screen.getByRole('button', { name: /copy/i }));

    await waitFor(() => expect(screen.getByText('Copied!')).toBeInTheDocument());
  });

  it('fetches enrollment data using the selected org slug', async () => {
    renderPage();

    await waitFor(() => expect(api.get).toHaveBeenCalledWith('/api/security/enrollment/?org=acme'));
  });

  it('shows no org message when selectedOrg is null', () => {
    renderPage(null);
    expect(screen.getByText('No organisation assigned.')).toBeInTheDocument();
  });
});
