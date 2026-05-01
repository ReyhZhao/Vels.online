import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import PostCard from './PostCard';

function renderCard(props) {
  return render(
    <MemoryRouter>
      <PostCard {...props} />
    </MemoryRouter>
  );
}

describe('PostCard', () => {
  it('renders the title as a link to the correct slug', () => {
    renderCard({ title: 'Hello World', slug: 'hello-world', content: '' });
    const link = screen.getByRole('link', { name: 'Hello World' });
    expect(link).toBeInTheDocument();
    expect(link).toHaveAttribute('href', '/hello-world');
  });

  it('renders a formatted publish date', () => {
    renderCard({
      title: 'Post',
      slug: 'post',
      publishedAt: '2026-01-15T00:00:00Z',
      content: '',
    });
    expect(screen.getByText(/15 January 2026/i)).toBeInTheDocument();
  });

  it('truncates content longer than 150 characters with an ellipsis', () => {
    const longContent = 'a'.repeat(200);
    renderCard({ title: 'Post', slug: 'post', content: longContent });
    const excerpt = screen.getByText(/a+…/);
    expect(excerpt.textContent.length).toBe(151); // 150 chars + ellipsis
  });

  it('shows full content when it is 150 characters or fewer', () => {
    const shortContent = 'Short excerpt.';
    renderCard({ title: 'Post', slug: 'post', content: shortContent });
    expect(screen.getByText('Short excerpt.')).toBeInTheDocument();
  });

  it('strips markdown syntax from the excerpt', () => {
    renderCard({
      title: 'Post',
      slug: 'post',
      content: '# My Heading\n\n**bold** and _italic_ with `code`.',
    });
    expect(screen.getByText('My Heading bold and italic with code.')).toBeInTheDocument();
  });
});
