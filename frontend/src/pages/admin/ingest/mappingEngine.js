// Client-side mapping resolver for the Ingest Endpoints Inspector builder. Mirrors the
// backend Field Mapping engine (backend/webhook_ingest/mapping.py) closely enough to give
// an instant, faithful dry-run preview as the operator clicks leaves. Ported from the
// throwaway prototype (frontend/src/prototypes) after the "Inspector" layout was chosen.

// Canonical target fields per resource type (mirror TARGET_FIELDS in mapping.py).
export const TARGET_FIELDS = {
  incident: [
    { key: 'title', label: 'Title', required: true },
    { key: 'description', label: 'Description' },
    { key: 'severity', label: 'Severity', enum: true },
    { key: 'tlp', label: 'TLP', enum: true },
    { key: 'pap', label: 'PAP', enum: true },
  ],
  alert: [
    { key: 'title', label: 'Title', required: true },
    { key: 'description', label: 'Description' },
    { key: 'severity', label: 'Severity', enum: true },
    { key: 'tlp', label: 'TLP', enum: true },
    { key: 'pap', label: 'PAP', enum: true },
  ],
  asset: [
    { key: 'name', label: 'Name', required: true },
    { key: 'ip_address', label: 'IP address' },
    { key: 'role', label: 'Role' },
  ],
};

// ECS entity targets — an Alert needs ≥1 to resolve or the V2 ingest rejects it.
export const ECS_TARGETS = ['host.name', 'source.ip', 'user.name', 'file.hash.sha256', 'process.name'];

export function getByPath(obj, path) {
  if (!path) return undefined;
  return path.split('.').reduce((acc, seg) => {
    if (acc == null) return undefined;
    const key = /^\d+$/.test(seg) ? Number(seg) : seg;
    return acc[key];
  }, obj);
}

export function parseValueMap(text) {
  const out = {};
  (text || '').split(',').forEach(pair => {
    const [k, ...rest] = pair.split('=');
    const key = (k || '').trim();
    const val = rest.join('=').trim();
    if (key && val) out[key] = val;
  });
  return out;
}

export function formatValueMap(obj) {
  return Object.entries(obj || {}).map(([k, v]) => `${k}=${v}`).join(', ');
}

function applyValueMap(value, valueMap) {
  if (value == null || !valueMap) return value;
  const hit = Object.entries(valueMap).find(([k]) => k.toLowerCase() === String(value).toLowerCase());
  return hit ? hit[1] : value;
}

// Resolve one field mapping ({kind:'path'|'constant', path, value, value_map, default})
// against one element. Returns { value, ok }.
export function resolveField(mapping, record) {
  if (!mapping) return { value: undefined, ok: false };
  if (mapping.kind === 'constant') {
    const v = mapping.value;
    return { value: v, ok: v != null && v !== '' };
  }
  const raw = getByPath(record, mapping.path);
  const mapped = applyValueMap(raw, mapping.value_map);
  const value = mapped != null ? mapped : (mapping.default || undefined);
  return { value, ok: value != null && value !== '', raw };
}

// Collection Root → the elements to fan out over. Empty root = whole body is one record.
export function elementsFor(body, collectionRoot) {
  if (body == null) return [];
  if (!collectionRoot) return [body];
  const arr = getByPath(body, collectionRoot);
  if (!Array.isArray(arr)) return [];
  return arr;
}

// Whether a resolved element would materialise (title/name required; alerts also need ≥1 ECS).
export function elementOk(targetType, fields, mappings, ecs, element) {
  const missingRequired = fields.some(f => f.required && !resolveField(mappings[f.key], element).ok);
  if (missingRequired) return false;
  if (targetType === 'alert') {
    const hasEntity = ECS_TARGETS.some(k => resolveField(ecs?.[k], element).ok);
    if (!hasEntity) return false;
  }
  return true;
}

// Build the API field_mappings object from the builder's per-field form state.
export function mappingsToApi(mappings) {
  const out = {};
  Object.entries(mappings || {}).forEach(([key, m]) => {
    if (!m) return;
    if (m.kind === 'constant') {
      if ((m.value || '').toString().trim()) out[key] = { kind: 'constant', value: m.value };
    } else if (m.path || (m.value_map && Object.keys(m.value_map).length) || m.default) {
      out[key] = { kind: 'path', path: m.path || '', value_map: m.value_map || {}, default: m.default || '' };
    }
  });
  return out;
}
