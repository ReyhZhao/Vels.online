import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi } from 'vitest';
import SlideOver from './SlideOver';

function renderSlideOver(props = {}) {
  const defaults = { open: true, onClose: vi.fn(), title: 'Test Panel', loading: false };
  return render(
    <SlideOver {...defaults} {...props}>
      <p>Panel content</p>
    </SlideOver>
  );
}

describe('SlideOver', () => {
  it('renders children when open', () => {
    renderSlideOver({ open: true });
    expect(screen.getByText('Panel content')).toBeInTheDocument();
  });

  it('does not render children when closed', () => {
    renderSlideOver({ open: false });
    expect(screen.queryByText('Panel content')).not.toBeInTheDocument();
  });

  it('renders the title', () => {
    renderSlideOver({ open: true });
    expect(screen.getByText('Test Panel')).toBeInTheDocument();
  });

  it('shows loading indicator when loading is true', () => {
    renderSlideOver({ open: true, loading: true });
    expect(screen.getByRole('status')).toBeInTheDocument();
    expect(screen.queryByText('Panel content')).not.toBeInTheDocument();
  });

  it('calls onClose when backdrop is clicked', async () => {
    const onClose = vi.fn();
    const user = userEvent.setup();
    renderSlideOver({ open: true, onClose });

    await user.click(screen.getByTestId('slideover-backdrop'));

    expect(onClose).toHaveBeenCalledOnce();
  });

  it('calls onClose when the close button is clicked', async () => {
    const onClose = vi.fn();
    const user = userEvent.setup();
    renderSlideOver({ open: true, onClose });

    await user.click(screen.getByRole('button', { name: /close/i }));

    expect(onClose).toHaveBeenCalledOnce();
  });

  it('does not call onClose when panel content is clicked', async () => {
    const onClose = vi.fn();
    const user = userEvent.setup();
    renderSlideOver({ open: true, onClose });

    await user.click(screen.getByText('Panel content'));

    expect(onClose).not.toHaveBeenCalled();
  });
});
