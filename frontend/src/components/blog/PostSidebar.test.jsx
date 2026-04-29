import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { vi, describe, it, expect } from 'vitest';
import PostSidebar from './PostSidebar';

vi.mock('@/lib/axios', () => ({
  default: { get: vi.fn() },
}));

import api from '@/lib/axios';

function renderSidebar(props) {
  return render(
    <MemoryRouter>
      <PostSidebar {...props} />
    </MemoryRouter>
  );
}

describe('PostSidebar', () => {
  it('renders the formatted publish date', async () => {
    api.get.mockResolvedValue({ data: [] });
    renderSidebar({ publishedAt: '2026-01-15T00:00:00Z', content: 'text', currentSlug: 'post-1' });
    await waitFor(() => {
      expect(screen.getByText(/15 January 2026/i)).toBeInTheDocument();
    });
  });

  it('renders the estimated read time', () => {
    api.get.mockResolvedValue({ data: [] });
    const content = 'word '.repeat(200);
    renderSidebar({ publishedAt: '2026-01-15T00:00:00Z', content, currentSlug: 'post-1' });
    expect(screen.getByText('1 min read')).toBeInTheDocument();
  });

  it('renders recent posts excluding the current slug', async () => {
    api.get.mockResolvedValue({
      data: [
        { slug: 'post-1', title: 'Current Post' },
        { slug: 'post-2', title: 'Other Post' },
      ],
    });
    renderSidebar({ publishedAt: '2026-01-15T00:00:00Z', content: 'text', currentSlug: 'post-1' });
    await waitFor(() => {
      expect(screen.getByRole('link', { name: 'Other Post' })).toBeInTheDocument();
      expect(screen.queryByText('Current Post')).not.toBeInTheDocument();
    });
  });

  it('each recent post links to its correct slug', async () => {
    api.get.mockResolvedValue({
      data: [{ slug: 'other-post', title: 'Other Post' }],
    });
    renderSidebar({ publishedAt: '2026-01-15T00:00:00Z', content: 'text', currentSlug: 'post-1' });
    await waitFor(() => {
      expect(screen.getByRole('link', { name: 'Other Post' })).toHaveAttribute('href', '/other-post');
    });
  });
});
