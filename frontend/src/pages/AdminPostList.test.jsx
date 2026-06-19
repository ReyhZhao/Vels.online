import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import AdminPostList from './AdminPostList';

vi.mock('../lib/axios', () => ({
  default: { get: vi.fn(), delete: vi.fn() },
}));

import api from '../lib/axios';

function renderList() {
  return render(
    <MemoryRouter>
      <AdminPostList />
    </MemoryRouter>
  );
}

beforeEach(() => vi.clearAllMocks());

describe('AdminPostList', () => {
  it('renders all posts including drafts', async () => {
    api.get.mockResolvedValue({
      data: [
        { slug: 'draft-post', title: 'Draft Post', status: 'draft', published_at: null },
        { slug: 'published-post', title: 'Published Post', status: 'published', published_at: '2026-01-01T00:00:00Z' },
      ],
    });

    renderList();

    // Both mobile card list and desktop table render titles in jsdom (no CSS media queries)
    await waitFor(() => {
      expect(screen.getAllByText('Draft Post').length).toBeGreaterThan(0);
      expect(screen.getAllByText('Published Post').length).toBeGreaterThan(0);
    });
  });

  it('renders a status badge for each post', async () => {
    api.get.mockResolvedValue({
      data: [
        { slug: 'draft-post', title: 'Draft Post', status: 'draft', published_at: null },
        { slug: 'published-post', title: 'Published Post', status: 'published', published_at: '2026-01-01T00:00:00Z' },
      ],
    });

    renderList();

    await waitFor(() => {
      expect(screen.getAllByText('draft').length).toBeGreaterThan(0);
      expect(screen.getAllByText('published').length).toBeGreaterThan(0);
    });
  });

  it('renders an edit link pointing to the correct route', async () => {
    api.get.mockResolvedValue({
      data: [{ slug: 'my-post', title: 'My Post', status: 'draft', published_at: null }],
    });

    renderList();

    await waitFor(() => {
      const editLinks = screen.getAllByRole('link', { name: /edit/i });
      expect(editLinks.length).toBeGreaterThan(0);
      expect(editLinks[0]).toHaveAttribute('href', '/admin/posts/my-post/edit');
    });
  });

  it('delete triggers confirmation and calls DELETE API', async () => {
    api.get.mockResolvedValue({
      data: [{ slug: 'test-post', title: 'Test Post', status: 'draft', published_at: null }],
    });
    api.delete.mockResolvedValue({});
    vi.spyOn(window, 'confirm').mockReturnValue(true);

    renderList();

    await waitFor(() => screen.getAllByText('Test Post'));
    await userEvent.click(screen.getAllByRole('button', { name: /delete/i })[0]);

    expect(window.confirm).toHaveBeenCalledWith('Delete this post?');
    expect(api.delete).toHaveBeenCalledWith('/api/posts/test-post/');
  });

  it('removes the row after a successful delete', async () => {
    api.get
      .mockResolvedValueOnce({ data: [{ slug: 'test-post', title: 'Test Post', status: 'draft', published_at: null }] })
      .mockResolvedValueOnce({ data: [] });
    api.delete.mockResolvedValue({});
    vi.spyOn(window, 'confirm').mockReturnValue(true);

    renderList();

    await waitFor(() => screen.getAllByText('Test Post'));
    await userEvent.click(screen.getAllByRole('button', { name: /delete/i })[0]);

    await waitFor(() => {
      expect(screen.queryByText('Test Post')).not.toBeInTheDocument();
    });
  });

  it('does not delete when confirmation is cancelled', async () => {
    api.get.mockResolvedValue({
      data: [{ slug: 'test-post', title: 'Test Post', status: 'draft', published_at: null }],
    });
    vi.spyOn(window, 'confirm').mockReturnValue(false);

    renderList();

    await waitFor(() => screen.getAllByText('Test Post'));
    await userEvent.click(screen.getAllByRole('button', { name: /delete/i })[0]);

    expect(api.delete).not.toHaveBeenCalled();
  });
});
