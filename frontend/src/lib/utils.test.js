import { describe, it, expect } from 'vitest';
import { stripMarkdown } from './utils';

describe('stripMarkdown', () => {
  it('returns empty string for falsy input', () => {
    expect(stripMarkdown('')).toBe('');
    expect(stripMarkdown(null)).toBe('');
    expect(stripMarkdown(undefined)).toBe('');
  });

  it('strips heading markers', () => {
    expect(stripMarkdown('# H1')).toBe('H1');
    expect(stripMarkdown('## H2')).toBe('H2');
    expect(stripMarkdown('### H3')).toBe('H3');
  });

  it('strips bold and italic markers', () => {
    expect(stripMarkdown('**bold**')).toBe('bold');
    expect(stripMarkdown('__bold__')).toBe('bold');
    expect(stripMarkdown('*italic*')).toBe('italic');
    expect(stripMarkdown('_italic_')).toBe('italic');
  });

  it('strips inline code', () => {
    expect(stripMarkdown('`myFunction()`')).toBe('myFunction()');
  });

  it('strips fenced code blocks', () => {
    expect(stripMarkdown('```\nconst x = 1;\n```')).toBe('');
  });

  it('replaces links with their label', () => {
    expect(stripMarkdown('[Click here](https://example.com)')).toBe('Click here');
  });

  it('removes images entirely', () => {
    expect(stripMarkdown('![alt text](image.png)')).toBe('');
  });

  it('strips blockquote markers', () => {
    expect(stripMarkdown('> A quote')).toBe('A quote');
  });

  it('strips unordered list markers', () => {
    expect(stripMarkdown('- item one\n- item two')).toBe('item one item two');
  });

  it('collapses newlines to spaces', () => {
    expect(stripMarkdown('line one\n\nline two')).toBe('line one line two');
  });

  it('handles a realistic mixed markdown post', () => {
    const input = '# Title\n\nSome **bold** and _italic_ text with `code`.';
    expect(stripMarkdown(input)).toBe('Title Some bold and italic text with code.');
  });
});
