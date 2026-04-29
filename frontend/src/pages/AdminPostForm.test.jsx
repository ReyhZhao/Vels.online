import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import AdminPostForm from './AdminPostForm';

vi.mock('../lib/axios', () => ({
  default: { get: vi.fn(), post: vi.fn(), patch: vi.fn() },
}));

vi.mock('react-router-dom', async (importOriginal) => {
  const actual = await importOriginal();
  return { ...actual, useNavigate: () => vi.fn() };
});

import api from '../lib/axios';

beforeEach(() => vi.clearAllMocks());

describe('AdminPostForm — create', () => {
  it('submits correct payload on create', async () => {
    api.post.mockResolvedValue({ data: { slug: 'new-post' } });

    render(
      <MemoryRouter initialEntries={['/admin/posts/new']}>
        <Routes>
          <Route path="/admin/posts/new" element={<AdminPostForm />} />
        </Routes>
      </MemoryRouter>
    );

    await userEvent.type(screen.getByLabelText('Title'), 'New Post');
    await userEvent.type(screen.getByLabelText('Content'), 'Post content');
    await userEvent.click(screen.getByRole('button', { name: 'Create' }));

    expect(api.post).toHaveBeenCalledWith('/api/posts/', {
      title: 'New Post',
      content: 'Post content',
      status: 'draft',
    });
  });

  it('status field defaults to draft and accepts published', async () => {
    api.post.mockResolvedValue({ data: { slug: 'new-post' } });

    render(
      <MemoryRouter initialEntries={['/admin/posts/new']}>
        <Routes>
          <Route path="/admin/posts/new" element={<AdminPostForm />} />
        </Routes>
      </MemoryRouter>
    );

    const statusField = screen.getByLabelText('Status');
    expect(statusField).toHaveValue('draft');

    await userEvent.selectOptions(statusField, 'published');
    expect(statusField).toHaveValue('published');
  });
});

describe('AdminPostForm — edit', () => {
  it('pre-populates fields from existing post', async () => {
    api.get.mockResolvedValue({
      data: {
        slug: 'existing-post',
        title: 'Existing Post',
        content: 'Old content',
        status: 'published',
      },
    });

    render(
      <MemoryRouter initialEntries={['/admin/posts/existing-post/edit']}>
        <Routes>
          <Route path="/admin/posts/:slug/edit" element={<AdminPostForm />} />
        </Routes>
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByLabelText('Title')).toHaveValue('Existing Post');
      expect(screen.getByLabelText('Content')).toHaveValue('Old content');
      expect(screen.getByLabelText('Status')).toHaveValue('published');
    });
  });

  it('submits PATCH with updated payload on save', async () => {
    api.get.mockResolvedValue({
      data: { slug: 'existing-post', title: 'Old Title', content: 'body', status: 'draft' },
    });
    api.patch.mockResolvedValue({ data: {} });

    render(
      <MemoryRouter initialEntries={['/admin/posts/existing-post/edit']}>
        <Routes>
          <Route path="/admin/posts/:slug/edit" element={<AdminPostForm />} />
        </Routes>
      </MemoryRouter>
    );

    await waitFor(() => screen.getByLabelText('Title'));
    await userEvent.clear(screen.getByLabelText('Title'));
    await userEvent.type(screen.getByLabelText('Title'), 'Updated Title');
    await userEvent.click(screen.getByRole('button', { name: 'Save' }));

    expect(api.patch).toHaveBeenCalledWith('/api/posts/existing-post/', {
      title: 'Updated Title',
      content: 'body',
      status: 'draft',
    });
  });
});
