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

const GLOBAL_DOWNLOAD = { id: 1, label: 'Wazuh Agent (Linux)', platform: 'linux', category: 'agent', organization_slug: null, has_file: true };
const ORG_DOWNLOAD = { id: 2, label: 'Acme Config', platform: 'all', category: 'config', organization_slug: 'acme', has_file: true };
const DOWNLOADS = [GLOBAL_DOWNLOAD, ORG_DOWNLOAD];

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
    api.get.mockImplementation((url) => {
      if (url.includes('/enrollment/')) return Promise.resolve({ data: ENROLLMENT });
      if (url.includes('/downloads/')) return Promise.resolve({ data: DOWNLOADS });
      return Promise.resolve({ data: [] });
    });
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

  // Downloads section

  it('fetches downloads using the selected org slug', async () => {
    renderPage();

    await waitFor(() =>
      expect(api.get).toHaveBeenCalledWith('/api/security/downloads/?org=acme')
    );
  });

  it('renders the downloads section when downloads are returned', async () => {
    renderPage();

    await waitFor(() =>
      expect(screen.getByTestId('downloads-section')).toBeInTheDocument()
    );
  });

  it('renders global and org-specific downloads together', async () => {
    renderPage();

    await waitFor(() => {
      expect(screen.getByText('Wazuh Agent (Linux)')).toBeInTheDocument();
      expect(screen.getByText('Acme Config')).toBeInTheDocument();
    });
  });

  it('groups downloads by category', async () => {
    renderPage();

    await waitFor(() => {
      expect(screen.getByText('Agent')).toBeInTheDocument();
      expect(screen.getByText('Config')).toBeInTheDocument();
    });
  });

  it('download button fetches presigned URL and triggers download', async () => {
    api.get.mockImplementation((url) => {
      if (url.includes('/enrollment/')) return Promise.resolve({ data: ENROLLMENT });
      if (url.includes('/downloads/') && url.includes('/presigned/'))
        return Promise.resolve({ data: { url: 'https://s3.example.com/signed' } });
      if (url.includes('/downloads/')) return Promise.resolve({ data: DOWNLOADS });
      return Promise.resolve({ data: [] });
    });

    const appendSpy = vi.spyOn(document.body, 'appendChild');
    const removeSpy = vi.spyOn(document.body, 'removeChild');

    const user = userEvent.setup();
    renderPage();

    await waitFor(() =>
      expect(screen.getByTestId('download-btn-1')).toBeInTheDocument()
    );

    await user.click(screen.getByTestId('download-btn-1'));

    await waitFor(() =>
      expect(api.get).toHaveBeenCalledWith(`/api/security/downloads/1/presigned/`)
    );

    expect(appendSpy).toHaveBeenCalled();
    expect(removeSpy).toHaveBeenCalled();

    appendSpy.mockRestore();
    removeSpy.mockRestore();
  });

  it('does not render downloads section when list is empty', async () => {
    api.get.mockImplementation((url) => {
      if (url.includes('/enrollment/')) return Promise.resolve({ data: ENROLLMENT });
      if (url.includes('/downloads/')) return Promise.resolve({ data: [] });
      return Promise.resolve({ data: [] });
    });

    renderPage();

    await waitFor(() => expect(screen.getByTestId('install-command')).toBeInTheDocument());
    expect(screen.queryByTestId('downloads-section')).not.toBeInTheDocument();
  });
});
