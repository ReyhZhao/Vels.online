import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { vi, describe, it, expect } from 'vitest';
import PostDetail from './PostDetail';

vi.mock('../lib/axios', () => ({
  default: { get: vi.fn() },
}));

import api from '../lib/axios';

describe('PostDetail', () => {
  it('renders post title and content', async () => {
    api.get.mockResolvedValue({
      data: { slug: 'hello-world', title: 'Hello World', content: 'My post content' },
    });

    render(
      <MemoryRouter initialEntries={['/hello-world']}>
        <Routes>
          <Route path="/:slug" element={<PostDetail />} />
        </Routes>
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByText('Hello World')).toBeInTheDocument();
      expect(screen.getByText('My post content')).toBeInTheDocument();
    });
  });

  it('renders nothing while loading', () => {
    api.get.mockReturnValue(new Promise(() => {}));

    render(
      <MemoryRouter initialEntries={['/hello-world']}>
        <Routes>
          <Route path="/:slug" element={<PostDetail />} />
        </Routes>
      </MemoryRouter>
    );

    expect(screen.queryByRole('article')).not.toBeInTheDocument();
  });
});
