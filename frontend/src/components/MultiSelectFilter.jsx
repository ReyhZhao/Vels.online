import { useState, useEffect, useRef } from 'react';

// Order-independent set equality over two value arrays.
function sameSet(a, b) {
  if (a.length !== b.length) return false;
  const setB = new Set(b);
  return a.every(v => setB.has(v));
}

/**
 * Generic multi-select filter: a trigger button showing a summary, opening a
 * dropdown of checkboxes with "Select all" / "Reset" affordances. The canonical
 * facet-filter pattern for standalone list routes (see frontend-conventions.md).
 *
 * The component owns all interaction logic and hands the parent the FULL next
 * selection (canonically ordered by `options`) via `onChange`; the parent only
 * decides how to serialise it (e.g. to a URL param).
 *
 * Props:
 *  - options      Array of values, in canonical/display order.
 *  - selected     Currently-selected values.
 *  - onChange     (nextValues) => void. Receives the full array, options-ordered.
 *  - resetTo      Selection that "Reset" restores (a baseline array, or []).
 *  - lockLast     When true, never allow the selection to reach empty.
 *  - summarize    (selected) => string shown on the trigger button.
 *  - renderOption (value) => node rendered next to each checkbox.
 *  - optionLabel  (value) => string used as each checkbox's aria-label.
 *  - ariaLabel    aria-label for the trigger button.
 *  - groupLabel   aria-label for the dropdown group.
 */
export default function MultiSelectFilter({
  options,
  selected,
  onChange,
  resetTo = [],
  lockLast = false,
  summarize,
  renderOption,
  optionLabel = v => v,
  ariaLabel,
  groupLabel,
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    if (!open) return;
    function handleClickOutside(e) {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false);
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [open]);

  const selectedSet = new Set(selected);

  function toggle(value) {
    const next = new Set(selected);
    if (next.has(value)) {
      if (lockLast && next.size === 1) return; // keep at least one selected
      next.delete(value);
    } else {
      next.add(value);
    }
    onChange(options.filter(o => next.has(o)));
  }

  const allSelected = selected.length === options.length;
  const atResetTarget = sameSet(selected, resetTo);

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        aria-label={ariaLabel}
        aria-haspopup="true"
        aria-expanded={open}
        onClick={() => setOpen(o => !o)}
        className="flex items-center gap-2 rounded-md border border-border bg-background px-2 py-1.5 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
      >
        <span>{summarize(selected)}</span>
        <span aria-hidden="true" className="text-muted-foreground">▾</span>
      </button>
      {open && (
        <div
          role="group"
          aria-label={groupLabel}
          className="absolute z-50 mt-1 min-w-[12rem] rounded-md border border-border bg-card py-1 shadow-lg"
        >
          <div className="flex items-center gap-3 border-b border-border px-3 py-1.5">
            <button
              type="button"
              onClick={() => onChange([...options])}
              disabled={allSelected}
              className="text-xs font-medium text-primary hover:underline disabled:cursor-not-allowed disabled:text-muted-foreground disabled:no-underline"
            >
              Select all
            </button>
            <button
              type="button"
              onClick={() => onChange([...resetTo])}
              disabled={atResetTarget}
              className="text-xs font-medium text-muted-foreground hover:text-foreground hover:underline disabled:cursor-not-allowed disabled:opacity-50 disabled:no-underline"
            >
              Reset
            </button>
          </div>
          {options.map(value => {
            const checked = selectedSet.has(value);
            // With lockLast, the sole remaining checked item can't be cleared —
            // an empty selection has no sensible meaning for that facet.
            const lockThis = lockLast && checked && selected.length === 1;
            return (
              <label
                key={value}
                className={`flex items-center gap-2 px-3 py-1.5 text-sm hover:bg-accent ${lockThis ? 'cursor-not-allowed opacity-60' : 'cursor-pointer'}`}
              >
                <input
                  type="checkbox"
                  aria-label={optionLabel(value)}
                  checked={checked}
                  disabled={lockThis}
                  onChange={() => toggle(value)}
                  className="rounded border-border"
                />
                {renderOption(value)}
              </label>
            );
          })}
        </div>
      )}
    </div>
  );
}
