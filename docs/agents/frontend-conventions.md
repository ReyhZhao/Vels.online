# Frontend Conventions

UI rules that engineering skills must follow when building or changing the React
frontend. These are enforced by being read every session — treat them as
requirements, not suggestions.

## List & collection affordances

A **multi-row collection** is any view that renders N rows of the same kind of
thing (a table or a card list of alerts, incidents, rules, assets, etc.).

**Exempt:** detail pages, forms, wizards, dashboards, drawers, and any
single-record view. These do not get filter/sort/search.

### Standalone list routes (e.g. AlertsPage, IncidentList, SearchRulesAdmin)

- **Search** — always. A free-text box wired to the list's `?q=` query.
- **Sort** — always. Sortable columns (or a sort control for card lists).
- **Filter** — required **only when the records have a natural facet** (state,
  severity, type, org). Do not invent meaningless filters for facet-less data.
  See the multi-select state filter in `IncidentList.jsx` for the canonical
  pattern.

### Bulk selection

- **Every standalone list route gets bulk select.** Rows are selectable (a
  per-row checkbox plus a header "select all"), and selecting one or more rows
  surfaces the **relevant bulk actions** for that collection (e.g. bulk delete,
  bulk promote, bulk assign). Offer only actions that make sense for the
  records — do not add a bulk action with no meaning for the data.
- Reference: `frontend/src/pages/AlertsPage.jsx` (`selectedIds` Set, "Select all"
  checkbox, `BulkPromoteModal`, `handleBulkDelete`).

### Row actions: collapse into a kebab past two

- Up to **two** per-row actions may render as inline controls (buttons/icons).
- With **three or more** per-row actions, collapse them into a kebab (`⋮`)
  overflow menu instead of a row of inline buttons. This keeps rows narrow and
  reinforces the no-horizontal-scroll invariant.
- Reference: the rule actions menu in
  `frontend/src/pages/admin/SearchRulesAdmin.jsx` (`menuOpen` toggle,
  click-outside close, `aria-expanded`).

### Embedded collections (a list inside an exempt page)

The collection wins over its container: a multi-row list embedded in a detail
page (e.g. `LinkedIncidents`, `IncidentTimeline`, an attachments list) still
gets affordances, **scaled to context** — at minimum search and/or sort once the
list can realistically grow long. A short, bounded sub-list (a handful of fixed
rows) may stay plain.

## Responsiveness

- **No page-level horizontal scroll, ever.** The body and nav must never shift
  sideways on any viewport. This is a hard invariant.
- **Wide tables stack into cards on mobile.** Below the `sm` breakpoint (640px,
  Tailwind default), a data table reflows so each row becomes a card with
  stacked `label: value` pairs. Do not rely on a horizontally-scrolling table
  container as the mobile strategy.

### Canonical implementation

`frontend/src/pages/IncidentList.jsx` is the reference. It renders both layouts
and toggles them on breakpoint:

```jsx
{/* Mobile card list */}
<div className="sm:hidden space-y-2"> ... </div>

{/* Desktop table */}
<div className="hidden sm:block ..."><table> ... </table></div>
```

When adding a new list, copy this shape rather than introducing a new responsive
strategy.
