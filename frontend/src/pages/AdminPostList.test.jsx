import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import AdminPostList from './AdminPostList';

vi.mock('../lib/axios', () => ({
  default: { get: vi.fn(), delete: vi.fn(), patch: vi.fn() },
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

describe('AdminPostList — bulk actions + sort', () => {
  const POSTS = [
    { slug: 'zed-post', title: 'Zed Post', status: 'draft', published_at: '2026-01-01T00:00:00Z' },
    { slug: 'amber-post', title: 'Amber Post', status: 'published', published_at: '2026-03-01T00:00:00Z' },
  ];

  beforeEach(() => {
    vi.clearAllMocks();
    api.get.mockResolvedValue({ data: POSTS });
    api.patch.mockResolvedValue({});
    api.delete.mockResolvedValue({});
  });

  it('renders sortable Title / Status / Published headers and sorts on click', async () => {
    renderList();
    await waitFor(() => screen.getAllByText('Zed Post'));
    expect(screen.getByLabelText('Sort by Status')).toBeInTheDocument();
    expect(screen.getByLabelText('Sort by Published')).toBeInTheDocument();

    const table = document.querySelector('table');
    let rows = within(table).getAllByRole('row').slice(1);
    expect(rows[0].textContent).toContain('Zed Post'); // unsorted = API order

    await userEvent.click(screen.getByLabelText('Sort by Title'));
    rows = within(table).getAllByRole('row').slice(1);
    expect(rows[0].textContent).toContain('Amber Post'); // title asc
  });

  it('bulk publish PATCHes every selected post to published', async () => {
    renderList();
    await waitFor(() => screen.getByLabelText('Select all'));

    await userEvent.click(screen.getByLabelText('Select all'));
    await userEvent.click(screen.getByRole('button', { name: /^publish$/i }));

    await waitFor(() => expect(api.patch).toHaveBeenCalledWith('/api/posts/zed-post/', { status: 'published' }));
    expect(api.patch).toHaveBeenCalledWith('/api/posts/amber-post/', { status: 'published' });
  });

  it('bulk unpublish PATCHes every selected post to draft', async () => {
    renderList();
    await waitFor(() => screen.getByLabelText('Select all'));

    await userEvent.click(screen.getByLabelText('Select all'));
    await userEvent.click(screen.getByRole('button', { name: /^unpublish$/i }));

    await waitFor(() => expect(api.patch).toHaveBeenCalledWith('/api/posts/zed-post/', { status: 'draft' }));
  });

  it('bulk delete confirms then DELETEs every selected post', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    renderList();
    await waitFor(() => screen.getByLabelText('Select all'));

    await userEvent.click(screen.getByLabelText('Select all'));
    // the bulk toolbar Delete is the only "Delete" with no row context; click the last delete button
    const deletes = screen.getAllByRole('button', { name: /^delete$/i });
    await userEvent.click(deletes[deletes.length - 1]);

    await waitFor(() => expect(api.delete).toHaveBeenCalledWith('/api/posts/zed-post/'));
    expect(api.delete).toHaveBeenCalledWith('/api/posts/amber-post/');
  });
});
