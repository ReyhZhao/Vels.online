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
        { slug: 'draft-post', title: 'Draft Post', status: 'draft' },
        { slug: 'published-post', title: 'Published Post', status: 'published' },
      ],
    });

    renderList();

    await waitFor(() => {
      expect(screen.getByText('Draft Post')).toBeInTheDocument();
      expect(screen.getByText('Published Post')).toBeInTheDocument();
    });
  });

  it('delete triggers confirmation and calls DELETE API', async () => {
    api.get.mockResolvedValue({
      data: [{ slug: 'test-post', title: 'Test Post', status: 'draft' }],
    });
    api.delete.mockResolvedValue({});
    vi.spyOn(window, 'confirm').mockReturnValue(true);

    renderList();

    await waitFor(() => screen.getByText('Test Post'));
    await userEvent.click(screen.getByRole('button', { name: 'Delete' }));

    expect(window.confirm).toHaveBeenCalledWith('Delete this post?');
    expect(api.delete).toHaveBeenCalledWith('/api/posts/test-post/');
  });

  it('does not delete when confirmation is cancelled', async () => {
    api.get.mockResolvedValue({
      data: [{ slug: 'test-post', title: 'Test Post', status: 'draft' }],
    });
    vi.spyOn(window, 'confirm').mockReturnValue(false);

    renderList();

    await waitFor(() => screen.getByText('Test Post'));
    await userEvent.click(screen.getByRole('button', { name: 'Delete' }));

    expect(api.delete).not.toHaveBeenCalled();
  });
});
