import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { vi, describe, it, expect } from 'vitest';
import PostDetail from './PostDetail';

vi.mock('../lib/axios', () => ({
  default: { get: vi.fn() },
}));

import api from '../lib/axios';

const POST = {
  slug: 'hello-world',
  title: 'Hello World',
  content: 'My post content',
  published_at: '2026-01-15T00:00:00Z',
};

function renderPostDetail(slug = 'hello-world') {
  return render(
    <MemoryRouter initialEntries={[`/${slug}`]}>
      <Routes>
        <Route path="/:slug" element={<PostDetail />} />
      </Routes>
    </MemoryRouter>
  );
}

describe('PostDetail', () => {
  it('renders post title and content', async () => {
    api.get.mockImplementation((url) => {
      if (url.includes('/api/posts/hello-world/')) return Promise.resolve({ data: POST });
      return Promise.resolve({ data: [] });
    });

    renderPostDetail();

    await waitFor(() => {
      expect(screen.getByText('Hello World')).toBeInTheDocument();
      expect(screen.getByText('My post content')).toBeInTheDocument();
    });
  });

  it('renders the sidebar with publish date and read time', async () => {
    api.get.mockImplementation((url) => {
      if (url.includes('/api/posts/hello-world/')) return Promise.resolve({ data: POST });
      return Promise.resolve({ data: [] });
    });

    renderPostDetail();

    await waitFor(() => {
      expect(screen.getByText(/15 January 2026/i)).toBeInTheDocument();
      expect(screen.getByText(/min read/i)).toBeInTheDocument();
    });
  });

  it('renders recent posts in the sidebar', async () => {
    api.get.mockImplementation((url) => {
      if (url.includes('/api/posts/hello-world/')) return Promise.resolve({ data: POST });
      return Promise.resolve({
        data: [
          { slug: 'hello-world', title: 'Hello World' },
          { slug: 'other-post', title: 'Other Post' },
        ],
      });
    });

    renderPostDetail();

    await waitFor(() => {
      expect(screen.getByRole('link', { name: 'Other Post' })).toBeInTheDocument();
    });
  });

  it('renders nothing while loading', () => {
    api.get.mockReturnValue(new Promise(() => {}));

    renderPostDetail();

    expect(screen.queryByRole('heading')).not.toBeInTheDocument();
  });
});
