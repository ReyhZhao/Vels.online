import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import MarkdownRenderer from './MarkdownRenderer';

describe('MarkdownRenderer', () => {
  it('renders plain text content', () => {
    render(<MarkdownRenderer content="Hello world" />);
    expect(screen.getByText('Hello world')).toBeInTheDocument();
  });

  it('renders **bold** syntax as a strong element', () => {
    render(<MarkdownRenderer content="**bold text**" />);
    const el = screen.getByText('bold text');
    expect(el.tagName).toBe('STRONG');
  });

  it('renders # heading syntax as an h1 element', () => {
    render(<MarkdownRenderer content="# My Heading" />);
    expect(screen.getByRole('heading', { level: 1, name: 'My Heading' })).toBeInTheDocument();
  });

  it('renders backtick syntax as an inline code element', () => {
    render(<MarkdownRenderer content="`myCode()`" />);
    const el = screen.getByText('myCode()');
    expect(el.tagName).toBe('CODE');
  });
});
