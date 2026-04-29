import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { vi, describe, it, expect, beforeEach } from 'vitest';
import AdminDashboard from './AdminDashboard';

vi.mock('@/lib/axios', () => ({
  default: { get: vi.fn() },
}));

import api from '@/lib/axios';

function renderDashboard() {
  return render(
    <MemoryRouter>
      <AdminDashboard />
    </MemoryRouter>
  );
}

beforeEach(() => vi.clearAllMocks());

describe('AdminDashboard', () => {
  it('renders correct total, published, and draft counts', async () => {
    api.get.mockResolvedValue({
      data: [
        { slug: 'post-1', status: 'published' },
        { slug: 'post-2', status: 'published' },
        { slug: 'post-3', status: 'draft' },
      ],
    });

    renderDashboard();

    await waitFor(() => {
      expect(screen.getByText('Total Posts')).toBeInTheDocument();
      expect(screen.getByText('Published')).toBeInTheDocument();
      expect(screen.getByText('Drafts')).toBeInTheDocument();
    });

    const values = screen.getAllByRole('paragraph').map((el) => el.textContent);
    expect(values).toContain('3');
    expect(values).toContain('2');
    expect(values).toContain('1');
  });

  it('renders zero counts when there are no posts', async () => {
    api.get.mockResolvedValue({ data: [] });

    renderDashboard();

    await waitFor(() => {
      const values = screen.getAllByRole('paragraph').map((el) => el.textContent);
      expect(values.filter((v) => v === '0').length).toBe(3);
    });
  });

  it('renders a New Post link', () => {
    api.get.mockResolvedValue({ data: [] });
    renderDashboard();
    expect(screen.getByRole('link', { name: /new post/i })).toHaveAttribute('href', '/admin/posts/new');
  });

  it('renders a View all posts link', () => {
    api.get.mockResolvedValue({ data: [] });
    renderDashboard();
    expect(screen.getByRole('link', { name: /view all posts/i })).toHaveAttribute('href', '/admin/posts');
  });
});
