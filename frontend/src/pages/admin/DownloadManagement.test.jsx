import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';

vi.mock('@/lib/axios', () => ({
  default: { get: vi.fn(), post: vi.fn() },
}));

import api from '@/lib/axios';
import DownloadManagement from './DownloadManagement';

const DOWNLOADS = [
  { id: 1, label: 'Wazuh Agent (Linux)', platform: 'linux', category: 'agent', organization_slug: null, has_file: true },
  { id: 2, label: 'Acme Config', platform: 'all', category: 'config', organization_slug: 'acme', has_file: false },
];

const ORGS = [
  { id: 1, name: 'Acme Corp', slug: 'acme', wazuh_group: 'acme' },
];

function renderPage() {
  return render(
    <MemoryRouter>
      <DownloadManagement />
    </MemoryRouter>
  );
}

describe('DownloadManagement', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.get.mockImplementation((url) => {
      if (url.includes('/organizations/')) return Promise.resolve({ data: ORGS });
      if (url.includes('/downloads/')) return Promise.resolve({ data: DOWNLOADS });
      return Promise.resolve({ data: [] });
    });
    api.post.mockResolvedValue({
      data: { id: 3, label: 'New Tool', platform: 'windows', category: 'tool', organization_slug: null, has_file: false },
    });
  });

  it('renders the page heading', async () => {
    renderPage();
    await waitFor(() => expect(screen.getByText('Downloads')).toBeInTheDocument());
  });

  it('lists all downloads', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('Wazuh Agent (Linux)')).toBeInTheDocument();
      expect(screen.getByText('Acme Config')).toBeInTheDocument();
    });
  });

  it('shows platform and category labels', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('Linux')).toBeInTheDocument();
      expect(screen.getByText('Config')).toBeInTheDocument();
    });
  });

  it('shows global for downloads without an org', async () => {
    renderPage();
    await waitFor(() => expect(screen.getByText('global')).toBeInTheDocument());
  });

  it('shows org slug for org-specific downloads', async () => {
    renderPage();
    await waitFor(() => expect(screen.getByText('acme')).toBeInTheDocument());
  });

  it('creates a new download on form submit', async () => {
    const user = userEvent.setup();
    renderPage();

    await waitFor(() => expect(screen.getByLabelText('Label')).toBeInTheDocument());

    await user.type(screen.getByLabelText('Label'), 'New Tool');
    await user.click(screen.getByRole('button', { name: /create/i }));

    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith(
        '/api/security/downloads/',
        expect.objectContaining({ label: 'New Tool' })
      )
    );
  });

  it('adds newly created download to the list', async () => {
    const user = userEvent.setup();
    renderPage();

    await waitFor(() => expect(screen.getByLabelText('Label')).toBeInTheDocument());

    await user.type(screen.getByLabelText('Label'), 'New Tool');
    await user.click(screen.getByRole('button', { name: /create/i }));

    await waitFor(() => expect(screen.getByText('New Tool')).toBeInTheDocument());
  });

  it('fetches downloads and orgs on mount', async () => {
    renderPage();

    await waitFor(() => {
      expect(api.get).toHaveBeenCalledWith('/api/security/downloads/');
      expect(api.get).toHaveBeenCalledWith('/api/security/organizations/');
    });
  });
});
