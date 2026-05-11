import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';

vi.mock('../lib/axios', () => ({
  default: { post: vi.fn() },
}));

import api from '../lib/axios';
import ReportIssueModal from './ReportIssueModal';

function renderModal(open = true, onClose = vi.fn()) {
  return render(
    <MemoryRouter initialEntries={['/incidents']}>
      <ReportIssueModal open={open} onClose={onClose} />
    </MemoryRouter>
  );
}

describe('ReportIssueModal', () => {
  beforeEach(() => vi.clearAllMocks());

  it('renders nothing when closed', () => {
    const { container } = renderModal(false);
    expect(container).toBeEmptyDOMElement();
  });

  it('renders the form when open', () => {
    renderModal();
    expect(screen.getByText('Report an issue')).toBeInTheDocument();
    expect(screen.getByLabelText('Type')).toBeInTheDocument();
    expect(screen.getByLabelText('Title')).toBeInTheDocument();
    expect(screen.getByLabelText('Description')).toBeInTheDocument();
  });

  it('shows current path as read-only context', () => {
    renderModal();
    expect(screen.getByText('/incidents')).toBeInTheDocument();
  });

  it('submit button is disabled when title or description is empty', () => {
    renderModal();
    expect(screen.getByText('Submit issue')).toBeDisabled();
  });

  it('shows success state with issue URL link after submission', async () => {
    api.post.mockResolvedValue({ data: { issue_url: 'https://github.com/owner/repo/issues/1' } });
    renderModal();
    fireEvent.change(screen.getByLabelText('Title'), { target: { value: 'Bug title' } });
    fireEvent.change(screen.getByLabelText('Description'), { target: { value: 'Some description' } });
    fireEvent.click(screen.getByText('Submit issue'));
    await waitFor(() => screen.getByText('Issue created successfully.'));
    const link = screen.getByRole('link', { name: /github\.com/ });
    expect(link).toHaveAttribute('href', 'https://github.com/owner/repo/issues/1');
  });

  it('shows error inline without closing on failure', async () => {
    api.post.mockRejectedValue({ response: { data: { detail: 'GitHub integration is not configured.' } } });
    const onClose = vi.fn();
    renderModal(true, onClose);
    fireEvent.change(screen.getByLabelText('Title'), { target: { value: 'Bug' } });
    fireEvent.change(screen.getByLabelText('Description'), { target: { value: 'Desc' } });
    fireEvent.click(screen.getByText('Submit issue'));
    await waitFor(() => screen.getByRole('alert'));
    expect(screen.getByRole('alert')).toHaveTextContent('GitHub integration is not configured.');
    expect(onClose).not.toHaveBeenCalled();
  });

  it('posts to /api/feedback/issue/ with correct payload', async () => {
    api.post.mockResolvedValue({ data: { issue_url: 'https://github.com/owner/repo/issues/2' } });
    renderModal();
    fireEvent.change(screen.getByLabelText('Type'), { target: { value: 'feature' } });
    fireEvent.change(screen.getByLabelText('Title'), { target: { value: 'Add dark mode' } });
    fireEvent.change(screen.getByLabelText('Description'), { target: { value: 'Please add dark mode.' } });
    fireEvent.click(screen.getByText('Submit issue'));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith(
      '/api/feedback/issue/',
      expect.objectContaining({ type: 'feature', title: 'Add dark mode', path: '/incidents' })
    ));
  });

  it('calls onClose when Cancel is clicked', () => {
    const onClose = vi.fn();
    renderModal(true, onClose);
    fireEvent.click(screen.getByText('Cancel'));
    expect(onClose).toHaveBeenCalled();
  });

  it('calls onClose when ✕ button is clicked', () => {
    const onClose = vi.fn();
    renderModal(true, onClose);
    fireEvent.click(screen.getByLabelText('Close'));
    expect(onClose).toHaveBeenCalled();
  });
});
