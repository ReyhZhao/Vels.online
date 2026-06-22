import { useId, useState } from 'react';
import { HelpCircle } from 'lucide-react';

import { cn } from '@/lib/utils';

/**
 * A small, accessible help affordance: a focusable help icon that reveals a
 * short description on hover and on keyboard focus, dismissible on blur/Escape.
 *
 * Accessibility:
 * - The trigger is a real <button> (keyboard reachable, operable).
 * - The popover has role="tooltip" and is wired via aria-describedby so the
 *   description is announced by assistive tech.
 *
 * Layout: the popover is absolutely positioned and width-clamped to the
 * viewport (max-w never exceeds 100vw), wrapping rather than overflowing, so it
 * never introduces page-level horizontal scroll (see
 * docs/agents/frontend-conventions.md).
 */
function HelpTooltip({ label, text, className }) {
  const [open, setOpen] = useState(false);
  const tooltipId = useId();

  const show = () => setOpen(true);
  const hide = () => setOpen(false);

  function handleKeyDown(e) {
    if (e.key === 'Escape' && open) {
      e.stopPropagation();
      hide();
    }
  }

  return (
    <span className={cn('relative inline-flex', className)}>
      <button
        type="button"
        aria-label={label ? `Help: ${label}` : 'Help'}
        aria-describedby={open ? tooltipId : undefined}
        aria-expanded={open}
        onMouseEnter={show}
        onMouseLeave={hide}
        onFocus={show}
        onBlur={hide}
        onClick={() => setOpen(o => !o)}
        onKeyDown={handleKeyDown}
        className="inline-flex items-center justify-center rounded-full text-muted-foreground hover:text-foreground focus:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        <HelpCircle aria-hidden="true" className="h-3.5 w-3.5" />
      </button>
      {open && (
        <span
          role="tooltip"
          id={tooltipId}
          className="absolute left-1/2 top-full z-50 mt-1.5 w-max max-w-[min(16rem,calc(100vw-2rem))] -translate-x-1/2 rounded-md border border-border bg-popover px-3 py-2 text-xs font-normal normal-case tracking-normal text-popover-foreground shadow-lg whitespace-normal break-words"
        >
          {text}
        </span>
      )}
    </span>
  );
}

export { HelpTooltip };
