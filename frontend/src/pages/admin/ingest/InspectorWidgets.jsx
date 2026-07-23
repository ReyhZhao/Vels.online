// Presentational widgets for the Ingest Endpoints Inspector builder — a clickable JSON
// tree, a status badge, and the live dry-run record preview. Ported from the accepted
// prototype (frontend/src/prototypes/ingestUi.jsx), theme-native (dark tokens).
import { ECS_TARGETS, elementsFor, elementOk, resolveField } from './mappingEngine';

const STATUS_STYLES = {
  pending: 'bg-amber-400/15 text-amber-300 border-amber-400/30',
  created: 'bg-emerald-400/15 text-emerald-300 border-emerald-400/30',
  failed: 'bg-red-400/15 text-red-300 border-red-400/30',
  partial: 'bg-orange-400/15 text-orange-300 border-orange-400/30',
  capturing: 'bg-amber-400/15 text-amber-300 border-amber-400/30',
  active: 'bg-emerald-400/15 text-emerald-300 border-emerald-400/30',
  paused: 'bg-muted text-muted-foreground border-border',
};

export function StatusBadge({ status }) {
  return (
    <span className={`inline-flex items-center rounded-md border px-2 py-0.5 text-[11px] font-semibold capitalize ${STATUS_STYLES[status] || STATUS_STYLES.paused}`}>
      {status}
    </span>
  );
}

function valueColor(v) {
  if (typeof v === 'number') return 'text-sky-400';
  if (typeof v === 'boolean') return 'text-purple-400';
  if (v === null) return 'text-muted-foreground';
  return 'text-emerald-400';
}

// Clickable JSON tree. onPick(path) fires when a leaf is clicked; activePath highlights it.
export function JsonTree({ data, onPick, activePath, prefix = '' }) {
  if (data == null || typeof data !== 'object') return null;
  const entries = Array.isArray(data)
    ? data.map((v, i) => [String(i), v])
    : Object.entries(data);

  return (
    <ul className="ml-3 border-l border-border pl-2">
      {entries.map(([k, v]) => {
        const path = prefix ? `${prefix}.${k}` : k;
        const isLeaf = v == null || typeof v !== 'object';
        const active = activePath === path;
        return (
          <li key={path} className="py-0.5 font-mono text-xs leading-relaxed">
            {isLeaf ? (
              <button
                type="button"
                onClick={() => onPick?.(path)}
                aria-label={`Pick ${path}`}
                className={`group inline-flex max-w-full items-baseline gap-1.5 rounded px-1 text-left hover:bg-primary/20 ${active ? 'bg-primary/25 ring-1 ring-primary/60' : ''}`}
              >
                <span className="text-muted-foreground">{k}:</span>
                <span className={`truncate ${valueColor(v)}`}>{JSON.stringify(v)}</span>
              </button>
            ) : (
              <div>
                <span className="text-foreground/80">{k}</span>
                <span className="text-muted-foreground/60"> {Array.isArray(v) ? `[${v.length}]` : '{…}'}</span>
                <JsonTree data={v} onPick={onPick} activePath={activePath} prefix={path} />
              </div>
            )}
          </li>
        );
      })}
    </ul>
  );
}

// Live dry-run: run the current mapping over every fanned-out element and show the record(s)
// that would be created, pass/fail per element.
export function RecordPreview({ body, collectionRoot, targetType, fields, mappings, ecs }) {
  const elements = elementsFor(body, collectionRoot);
  if (!elements.length) {
    return (
      <div className="rounded-md border border-dashed border-red-400/40 bg-red-400/10 p-3 text-xs text-red-300">
        Collection Root <code>{collectionRoot || '(none)'}</code> did not resolve to an array — nothing to preview.
      </div>
    );
  }
  return (
    <div className="space-y-2" aria-label="Dry-run preview">
      {elements.map((el, i) => {
        const ok = elementOk(targetType, fields, mappings, ecs, el);
        const ecsResolved = targetType === 'alert'
          ? ECS_TARGETS.map(k => ({ k, r: resolveField(ecs?.[k], el) })).filter(x => x.r.ok)
          : [];
        return (
          <div key={i} className={`rounded-md border p-3 text-xs ${ok ? 'border-emerald-400/30 bg-emerald-400/[0.07]' : 'border-red-400/30 bg-red-400/[0.07]'}`}>
            <div className="mb-1.5 flex items-center justify-between">
              <span className="font-semibold text-muted-foreground">{collectionRoot ? `element [${i}]` : 'record'}</span>
              <StatusBadge status={ok ? 'created' : 'failed'} />
            </div>
            <dl className="grid grid-cols-[7rem_1fr] gap-x-3 gap-y-1">
              {fields.map(f => {
                const r = resolveField(mappings[f.key], el);
                return (
                  <div key={f.key} className="contents">
                    <dt className="text-muted-foreground">{f.label}{f.required && <span className="text-red-400">*</span>}</dt>
                    <dd className={r.ok ? 'text-foreground' : 'text-red-400'}>
                      {r.ok ? String(r.value) : <span className="italic">— unresolved —</span>}
                    </dd>
                  </div>
                );
              })}
              {targetType === 'alert' && (
                <div className="contents">
                  <dt className="text-muted-foreground">entities</dt>
                  <dd>
                    {ecsResolved.length ? (
                      <span className="flex flex-wrap gap-1">
                        {ecsResolved.map(x => (
                          <span key={x.k} className="rounded bg-indigo-400/20 px-1.5 py-0.5 font-mono text-[10px] text-indigo-200">
                            {x.k}={String(x.r.value)}
                          </span>
                        ))}
                      </span>
                    ) : (
                      <span className="text-red-300">no ECS entity resolved → rejected</span>
                    )}
                  </dd>
                </div>
              )}
            </dl>
          </div>
        );
      })}
    </div>
  );
}
