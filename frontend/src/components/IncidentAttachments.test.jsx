import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('../lib/axios', () => ({
  default: { get: vi.fn(), post: vi.fn(), delete: vi.fn() },
}));

const mockUseAuth = vi.fn(() => ({ user: { id: 1, username: 'alice', is_staff: false } }));
vi.mock('../context/AuthContext', () => ({ useAuth: () => mockUseAuth() }));

import api from '../lib/axios';
import IncidentAttachments from './IncidentAttachments';

const PUBLIC_ATTACHMENT = {
  id: 1, filename: 'report.pdf', size_bytes: 2048,
  content_type: 'application/pdf', sha256: '', is_internal: false,
  uploader: 1, uploader_username: 'alice',
  created_at: new Date().toISOString(), confirmed_at: new Date().toISOString(),
};

const INTERNAL_ATTACHMENT = {
  id: 2, filename: 'secret.pdf', size_bytes: 512,
  content_type: 'application/pdf', sha256: '', is_internal: true,
  uploader: 1, uploader_username: 'alice',
  created_at: new Date().toISOString(), confirmed_at: new Date().toISOString(),
};

describe('IncidentAttachments', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuth.mockReturnValue({ user: { id: 1, username: 'alice', is_staff: false } });
  });

  it('shows loading state', () => {
    api.get.mockReturnValue(new Promise(() => {}));
    render(<IncidentAttachments incidentId="1" />);
    expect(screen.getByText('Loading attachments…')).toBeInTheDocument();
  });

  it('shows empty state when no attachments', async () => {
    api.get.mockResolvedValue({ data: [] });
    render(<IncidentAttachments incidentId="1" />);
    await waitFor(() => screen.getByText('No attachments yet.'));
  });

  it('renders attachment filename and size', async () => {
    api.get.mockResolvedValue({ data: [PUBLIC_ATTACHMENT] });
    render(<IncidentAttachments incidentId="1" />);
    await waitFor(() => screen.getByText('report.pdf'));
    expect(screen.getByText(/2\.0 KB/)).toBeInTheDocument();
  });

  it('marks internal attachments with badge', async () => {
    mockUseAuth.mockReturnValue({ user: { id: 1, username: 'alice', is_staff: true } });
    api.get.mockResolvedValue({ data: [INTERNAL_ATTACHMENT] });
    render(<IncidentAttachments incidentId="1" />);
    await waitFor(() => screen.getByText('secret.pdf'));
    expect(screen.getByText('internal')).toBeInTheDocument();
  });

  async function openRowMenu(user, filename = 'report.pdf') {
    await waitFor(() => screen.getByText(filename));
    await user.click(screen.getByRole('button', { name: `Actions for ${filename}` }));
  }

  it('shows Download action in the row menu', async () => {
    api.get.mockResolvedValue({ data: [PUBLIC_ATTACHMENT] });
    const user = userEvent.setup();
    render(<IncidentAttachments incidentId="1" />);
    await openRowMenu(user);
    expect(screen.getByRole('menuitem', { name: /Download/ })).toBeInTheDocument();
  });

  it('offers Preview for a previewable attachment', async () => {
    api.get.mockResolvedValue({ data: [PUBLIC_ATTACHMENT] });
    const user = userEvent.setup();
    render(<IncidentAttachments incidentId="1" />);
    await openRowMenu(user);
    expect(screen.getByRole('menuitem', { name: /Preview/ })).toBeInTheDocument();
  });

  it('does not offer Preview for a non-viewable attachment', async () => {
    api.get.mockResolvedValue({ data: [{ ...PUBLIC_ATTACHMENT, filename: 'bundle.zip', content_type: 'application/zip' }] });
    const user = userEvent.setup();
    render(<IncidentAttachments incidentId="1" />);
    await openRowMenu(user, 'bundle.zip');
    expect(screen.queryByRole('menuitem', { name: /Preview/ })).not.toBeInTheDocument();
    expect(screen.getByRole('menuitem', { name: /Download/ })).toBeInTheDocument();
  });

  it('opens the preview modal and requests the preview endpoint', async () => {
    api.get.mockImplementation((url) => {
      if (url === '/api/incidents/1/attachments/') return Promise.resolve({ data: [PUBLIC_ATTACHMENT] });
      if (url.endsWith('/preview/')) return Promise.resolve({ data: { kind: 'pdf', url: 'https://s3.example.com/inline', content_type: 'application/pdf' } });
      return Promise.resolve({ data: {} });
    });
    const user = userEvent.setup();
    render(<IncidentAttachments incidentId="1" />);
    await openRowMenu(user);
    await user.click(screen.getByRole('menuitem', { name: /Preview/ }));
    await waitFor(() => expect(api.get).toHaveBeenCalledWith('/api/incidents/1/attachments/1/preview/'));
    expect(await screen.findByRole('dialog', { name: /Preview of report.pdf/ })).toBeInTheDocument();
  });

  it('does not offer Delete for non-staff', async () => {
    api.get.mockResolvedValue({ data: [PUBLIC_ATTACHMENT] });
    const user = userEvent.setup();
    render(<IncidentAttachments incidentId="1" />);
    await openRowMenu(user);
    expect(screen.queryByRole('menuitem', { name: /Delete/ })).not.toBeInTheDocument();
  });

  it('offers Delete for staff', async () => {
    mockUseAuth.mockReturnValue({ user: { id: 1, username: 'alice', is_staff: true } });
    api.get.mockResolvedValue({ data: [PUBLIC_ATTACHMENT] });
    const user = userEvent.setup();
    render(<IncidentAttachments incidentId="1" />);
    await openRowMenu(user);
    expect(screen.getByRole('menuitem', { name: /Delete/ })).toBeInTheDocument();
  });

  it('calls download API and opens URL when Download clicked', async () => {
    api.get.mockResolvedValueOnce({ data: [PUBLIC_ATTACHMENT] });
    api.get.mockResolvedValueOnce({ data: { url: 'https://s3.example.com/get' } });
    const openSpy = vi.spyOn(window, 'open').mockImplementation(() => null);
    const user = userEvent.setup();
    render(<IncidentAttachments incidentId="1" />);
    await openRowMenu(user);
    await user.click(screen.getByRole('menuitem', { name: /Download/ }));
    await waitFor(() => expect(api.get).toHaveBeenCalledWith('/api/incidents/1/attachments/1/download/'));
    expect(openSpy).toHaveBeenCalledWith('https://s3.example.com/get', '_blank', 'noopener,noreferrer');
    openSpy.mockRestore();
  });

  it('calls delete API and removes attachment from list when confirmed', async () => {
    mockUseAuth.mockReturnValue({ user: { id: 1, username: 'alice', is_staff: true } });
    api.get.mockResolvedValue({ data: [PUBLIC_ATTACHMENT] });
    api.delete.mockResolvedValue({});
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    const user = userEvent.setup();
    render(<IncidentAttachments incidentId="1" />);
    await openRowMenu(user);
    await user.click(screen.getByRole('menuitem', { name: /Delete/ }));
    await waitFor(() => expect(api.delete).toHaveBeenCalledWith('/api/incidents/1/attachments/1/'));
    expect(screen.queryByText('report.pdf')).not.toBeInTheDocument();
  });

  it('does not call delete API when confirm is cancelled', async () => {
    mockUseAuth.mockReturnValue({ user: { id: 1, username: 'alice', is_staff: true } });
    api.get.mockResolvedValue({ data: [PUBLIC_ATTACHMENT] });
    vi.spyOn(window, 'confirm').mockReturnValue(false);
    const user = userEvent.setup();
    render(<IncidentAttachments incidentId="1" />);
    await openRowMenu(user);
    await user.click(screen.getByRole('menuitem', { name: /Delete/ }));
    expect(api.delete).not.toHaveBeenCalled();
  });

  it('shows upload error on upload failure', async () => {
    api.get.mockResolvedValue({ data: [] });
    api.post.mockRejectedValue(new Error('Network error'));
    const user = userEvent.setup();
    render(<IncidentAttachments incidentId="1" />);
    await waitFor(() => screen.getByText('No attachments yet.'));
    const input = screen.getByLabelText('Upload file');
    const file = new File(['content'], 'test.pdf', { type: 'application/pdf' });
    await user.upload(input, file);
    await waitFor(() => screen.getByText('Upload failed. Please try again.'));
  });
});
