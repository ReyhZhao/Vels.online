import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import Footer from './Footer';

describe('Footer', () => {
  it('renders the LinkedIn link with the correct href', () => {
    render(<Footer />);
    const link = screen.getByRole('link', { name: 'LinkedIn' });
    expect(link).toBeInTheDocument();
    expect(link).toHaveAttribute('href', 'https://www.linkedin.com/in/eddievels/');
  });

  it('renders a copyright notice with the current year', () => {
    render(<Footer />);
    const year = new Date().getFullYear();
    expect(screen.getByText(new RegExp(String(year)))).toBeInTheDocument();
  });
});
