import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import MarkdownToolbar from './MarkdownToolbar';

vi.stubGlobal('requestAnimationFrame', cb => { cb(); return 0; });

function makeRef(value = '', selStart = 0, selEnd = 0) {
  return {
    current: {
      selectionStart: selStart,
      selectionEnd:   selEnd,
      focus:          vi.fn(),
      setSelectionRange: vi.fn(),
    },
  };
}

describe('MarkdownToolbar', () => {
  it('renders Bold, Italic, Code, and Link buttons', () => {
    render(<MarkdownToolbar textareaRef={{ current: null }} value="" onChange={() => {}} />);
    expect(screen.getByRole('button', { name: 'Bold' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Italic' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Code' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Link' })).toBeInTheDocument();
  });

  it('Bold wraps selection with **', () => {
    const onChange = vi.fn();
    const ref = makeRef('hello world', 0, 5);
    render(<MarkdownToolbar textareaRef={ref} value="hello world" onChange={onChange} />);
    fireEvent.click(screen.getByRole('button', { name: 'Bold' }));
    expect(onChange).toHaveBeenCalledWith('**hello** world');
  });

  it('Italic wraps selection with *', () => {
    const onChange = vi.fn();
    const ref = makeRef('hello world', 6, 11);
    render(<MarkdownToolbar textareaRef={ref} value="hello world" onChange={onChange} />);
    fireEvent.click(screen.getByRole('button', { name: 'Italic' }));
    expect(onChange).toHaveBeenCalledWith('hello *world*');
  });

  it('Code wraps selection with backticks', () => {
    const onChange = vi.fn();
    const ref = makeRef('run foo now', 4, 7);
    render(<MarkdownToolbar textareaRef={ref} value="run foo now" onChange={onChange} />);
    fireEvent.click(screen.getByRole('button', { name: 'Code' }));
    expect(onChange).toHaveBeenCalledWith('run `foo` now');
  });

  it('Link inserts [selected](url) when text is selected', () => {
    const onChange = vi.fn();
    const ref = makeRef('click here', 6, 10);
    render(<MarkdownToolbar textareaRef={ref} value="click here" onChange={onChange} />);
    fireEvent.click(screen.getByRole('button', { name: 'Link' }));
    expect(onChange).toHaveBeenCalledWith('click [here](url)');
  });

  it('Link inserts [link text](url) when nothing is selected', () => {
    const onChange = vi.fn();
    const ref = makeRef('', 0, 0);
    render(<MarkdownToolbar textareaRef={ref} value="" onChange={onChange} />);
    fireEvent.click(screen.getByRole('button', { name: 'Link' }));
    expect(onChange).toHaveBeenCalledWith('[link text](url)');
  });

  it('does nothing when ref is null', () => {
    const onChange = vi.fn();
    render(<MarkdownToolbar textareaRef={{ current: null }} value="hello" onChange={onChange} />);
    fireEvent.click(screen.getByRole('button', { name: 'Bold' }));
    expect(onChange).not.toHaveBeenCalled();
  });

  it('restores focus after applying a tool', () => {
    const onChange = vi.fn();
    const ref = makeRef('hello', 0, 5);
    render(<MarkdownToolbar textareaRef={ref} value="hello" onChange={onChange} />);
    fireEvent.click(screen.getByRole('button', { name: 'Bold' }));
    expect(ref.current.focus).toHaveBeenCalled();
    expect(ref.current.setSelectionRange).toHaveBeenCalled();
  });
});
