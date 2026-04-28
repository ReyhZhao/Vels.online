import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { vi, describe, it, expect } from 'vitest';
import PostList from './PostList';

vi.mock('../lib/axios', () => ({
  default: { get: vi.fn() },
}));

import api from '../lib/axios';

describe('PostList', () => {
  it('renders published post titles', async () => {
    api.get.mockResolvedValue({
      data: [
        { slug: 'hello-world', title: 'Hello World' },
        { slug: 'second-post', title: 'Second Post' },
      ],
    });

    render(
      <MemoryRouter>
        <PostList />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByText('Hello World')).toBeInTheDocument();
      expect(screen.getByText('Second Post')).toBeInTheDocument();
    });
  });

  it('renders an empty list when there are no posts', async () => {
    api.get.mockResolvedValue({ data: [] });

    render(
      <MemoryRouter>
        <PostList />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByRole('list')).toBeEmptyDOMElement();
    });
  });
});
