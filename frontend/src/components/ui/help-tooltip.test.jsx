import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect } from 'vitest';

import { HelpTooltip } from './help-tooltip';

describe('HelpTooltip', () => {
  it('hides the description until the trigger is interacted with', () => {
    render(<HelpTooltip label="State" text="What it means" />);
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument();
  });

  it('exposes an accessible, labelled trigger', () => {
    render(<HelpTooltip label="State" text="What it means" />);
    expect(screen.getByRole('button', { name: 'Help: State' })).toBeInTheDocument();
  });

  it('reveals the description on hover', () => {
    render(<HelpTooltip label="State" text="What it means" />);
    fireEvent.mouseEnter(screen.getByRole('button'));
    expect(screen.getByRole('tooltip')).toHaveTextContent('What it means');
  });

  it('reveals the description on keyboard focus and wires aria-describedby', () => {
    render(<HelpTooltip label="State" text="What it means" />);
    const trigger = screen.getByRole('button');
    fireEvent.focus(trigger);
    const tooltip = screen.getByRole('tooltip');
    expect(trigger).toHaveAttribute('aria-describedby', tooltip.id);
  });

  it('dismisses on blur', () => {
    render(<HelpTooltip label="State" text="What it means" />);
    const trigger = screen.getByRole('button');
    fireEvent.focus(trigger);
    expect(screen.getByRole('tooltip')).toBeInTheDocument();
    fireEvent.blur(trigger);
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument();
  });

  it('dismisses on Escape', () => {
    render(<HelpTooltip label="State" text="What it means" />);
    const trigger = screen.getByRole('button');
    fireEvent.focus(trigger);
    expect(screen.getByRole('tooltip')).toBeInTheDocument();
    fireEvent.keyDown(trigger, { key: 'Escape' });
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument();
  });
});
