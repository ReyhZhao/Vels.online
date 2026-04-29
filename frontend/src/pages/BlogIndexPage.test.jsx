import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { vi, describe, it, expect } from 'vitest';
import BlogIndexPage from './BlogIndexPage';

vi.mock('../lib/axios', () => ({
  default: { get: vi.fn() },
}));

import api from '../lib/axios';

function renderBlogIndex() {
  return render(
    <MemoryRouter>
      <BlogIndexPage />
    </MemoryRouter>
  );
}

describe('BlogIndexPage', () => {
  it('renders a PostCard for each published post', async () => {
    api.get.mockResolvedValue({
      data: [
        { slug: 'hello-world', title: 'Hello World', published_at: '2026-01-01T00:00:00Z', content: 'Content one' },
        { slug: 'second-post', title: 'Second Post', published_at: '2026-01-02T00:00:00Z', content: 'Content two' },
      ],
    });

    renderBlogIndex();

    await waitFor(() => {
      expect(screen.getByRole('link', { name: 'Hello World' })).toBeInTheDocument();
      expect(screen.getByRole('link', { name: 'Second Post' })).toBeInTheDocument();
    });
  });

  it('each PostCard links to the correct slug', async () => {
    api.get.mockResolvedValue({
      data: [
        { slug: 'my-post', title: 'My Post', published_at: '2026-01-01T00:00:00Z', content: 'Body' },
      ],
    });

    renderBlogIndex();

    await waitFor(() => {
      expect(screen.getByRole('link', { name: 'My Post' })).toHaveAttribute('href', '/my-post');
    });
  });

  it('renders an empty state when no posts are returned', async () => {
    api.get.mockResolvedValue({ data: [] });

    renderBlogIndex();

    await waitFor(() => {
      expect(screen.getByText(/no posts yet/i)).toBeInTheDocument();
    });
  });
});
