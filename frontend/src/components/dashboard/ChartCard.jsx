import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Table2, BarChart3 } from 'lucide-react';

/**
 * Card chrome shared by every dashboard chart: title row with an optional
 * "view all" link, plus a chart/table toggle so every value is reachable
 * without hovering (the chart's table-view twin).
 *
 * `table` is { columns: [{key, label, align?}], rows: [{...}] }.
 */
export default function ChartCard({ title, to, toLabel = 'View all', table, actions, children }) {
  const [showTable, setShowTable] = useState(false);

  return (
    <div className="rounded-lg border border-border bg-card">
      <div className="flex items-center justify-between gap-2 px-4 pt-3 pb-1">
        <h3 className="text-sm font-medium text-foreground">{title}</h3>
        <div className="flex items-center gap-1">
          {actions}
          {table && (
            <button
              type="button"
              onClick={() => setShowTable(s => !s)}
              aria-pressed={showTable}
              aria-label={showTable ? `Show ${title} as chart` : `Show ${title} as table`}
              className="rounded p-1 text-muted-foreground hover:text-foreground hover:bg-accent transition-colors"
            >
              {showTable ? <BarChart3 className="h-4 w-4" /> : <Table2 className="h-4 w-4" />}
            </button>
          )}
          {to && (
            <Link to={to} className="text-xs font-medium text-primary hover:underline whitespace-nowrap">
              {toLabel}
            </Link>
          )}
        </div>
      </div>
      <div className="px-4 pb-4 pt-2">
        {showTable && table ? (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-border">
                  {table.columns.map(col => (
                    <th
                      key={col.key}
                      className={`py-1.5 pr-3 font-medium text-muted-foreground ${
                        col.align === 'right' ? 'text-right' : 'text-left'
                      }`}
                    >
                      {col.label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {table.rows.length === 0 ? (
                  <tr>
                    <td colSpan={table.columns.length} className="py-4 text-center text-muted-foreground">
                      No data.
                    </td>
                  </tr>
                ) : (
                  table.rows.map((row, i) => (
                    <tr key={i} className="border-b border-border/50 last:border-0">
                      {table.columns.map(col => (
                        <td
                          key={col.key}
                          className={`py-1.5 pr-3 text-foreground ${
                            col.align === 'right' ? 'text-right tabular-nums' : 'text-left'
                          }`}
                        >
                          {row[col.key]}
                        </td>
                      ))}
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        ) : (
          children
        )}
      </div>
    </div>
  );
}
